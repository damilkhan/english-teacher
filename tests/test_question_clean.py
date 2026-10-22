# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_QUESTION_CLEAN.PY — варианты не дублируются в вопросе
# =========================================================
#   python tests\test_question_clean.py     (окно, звук и модель не нужны)
#
# Регрессия (найдена учеником 22.10.2026, вопрос 6, сложность B1): в тексте
# вопроса оказался весь список вариантов — «... this afternoon? | A) ... |
# B) ... | C) ... | D) ...» — и панель показала их ДВАЖДЫ: в тексте и в
# четырёх кнопках.
#
# Причина: модель возвращает JSON, где в поле "question" вместе с вопросом
# лежит перечисление вариантов (она копирует приём «список через |» из
# подсказки «не повторяй эти вопросы»). Парсер брал поле как есть.
#
# Проверяем:
#   1) случай со скриншота: текст вопроса очищен, варианты — только в options;
#   2) префиксы «A)» внутри options снимаются;
#   3) обычные вопросы НЕ портятся (резервный банк целиком + живые фразы);
#   4) полный проход через _generate_question: наружу уходит чистый вопрос;
#   5) список «не повторяй» больше не склеивается вертикальной чертой;
#   6) промпт прямо запрещает варианты внутри поля question.
# =========================================================

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import level_test                                              # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


# ровно то, что пришло с живого теста (вопрос со скриншота)
SCREENSHOT_RAW = (
    '{"question": "What should we do if the rain keeps pouring down and we '
    "can't go outside this afternoon? | A) We will look up the forecast and "
    "then decide to hang out inside. | B) We are looking up the forecast and "
    "decided to hang out inside. | C) We look up the forecast and will decide "
    "to hang out inside. | D) We looked up the forecast and decided to hang "
    'out inside.", "options": ['
    '"We will look up the forecast and then decide to hang out inside.", '
    '"We looked up the forecast and decided to hang out inside.", '
    '"We look up the forecast and will decide to hang out inside.", '
    '"We are looking up the forecast and decided to hang out inside."], '
    '"correct": 0}'
)

EXPECTED_QUESTION = ("What should we do if the rain keeps pouring down and we "
                     "can't go outside this afternoon?")


def options_leaked(question, options):
    """Какие варианты всё ещё встречаются в тексте вопроса."""
    low = " ".join(question.split()).lower()
    return [i for i, opt in enumerate(options)
            if opt.strip() and " ".join(opt.split()).lower() in low]


# =========================================================
# 1. Случай со скриншота
# =========================================================
def test_screenshot_case():
    print("\n[1] Случай со скриншота: варианты внутри вопроса")
    q = level_test._parse_question(SCREENSHOT_RAW, 3, "weather and seasons")
    check("вопрос разобран", q is not None, q)
    if q is None:
        return
    print("     вопрос наружу: %r" % q["question"])
    check("в тексте вопроса нет вариантов", not options_leaked(q["question"], q["options"]),
          options_leaked(q["question"], q["options"]))
    check("в тексте нет маркеров «A)»…«D)»",
          not re.search(r"[\(\[]?[A-D][\)\].:]", q["question"]), q["question"])
    check("в тексте нет вертикальной черты", "|" not in q["question"], q["question"])
    check("текст вопроса совпадает с ожидаемым", q["question"] == EXPECTED_QUESTION,
          q["question"])
    check("вариантов по-прежнему 4", len(q["options"]) == 4, len(q["options"]))
    check("правильный ответ не потерян", q["correct"] == 0, q["correct"])


# =========================================================
# 2. Префиксы внутри options
# =========================================================
def test_option_prefixes():
    print("\n[2] Маркеры «A)» внутри самих вариантов")
    raw = ('{"question": "Choose the correct sentence:", "options": ['
           '"A) She is a teacher.", "B) She are a teacher.", '
           '"C) She am a teacher.", "D) She be a teacher."], "correct": 0}')
    q = level_test._parse_question(raw, 2, "work and study")
    check("вопрос разобран", q is not None, q)
    if q is None:
        return
    for i, opt in enumerate(q["options"]):
        print("     %d) %r" % (i, opt))
    check("префиксы убраны у всех вариантов",
          not any(re.match(r"^\s*[\(\[]?[A-D][\)\].:]", o) for o in q["options"]),
          q["options"])
    check("варианты не потеряли текст",
          q["options"][0] == "She is a teacher.", q["options"][0])

    # одиночный маркер (не у всех) — варианты не трогаем
    raw2 = ('{"question": "Pick one:", "options": '
            '["A) is", "are", "am", "be"], "correct": 0}')
    q2 = level_test._parse_question(raw2, 1, "work and study")
    check("одиночный маркер не режет варианты",
          q2 is not None and len(q2["options"]) == 4,
          q2 and q2["options"])


# =========================================================
# 3. Обычные вопросы не портятся
# =========================================================
def test_bank_untouched():
    print("\n[3] Резервный банк проходит чистку без потерь")
    broken = []
    total = 0
    for difficulty, pool in level_test._QUESTION_BANK.items():
        for item in pool:
            total += 1
            cleaned = level_test._strip_inline_options(item["question"],
                                                       item["options"])
            if cleaned != item["question"]:
                broken.append((item["question"], cleaned))
            prefixed = level_test._strip_option_prefixes(item["options"])
            if prefixed != list(item["options"]):
                broken.append((item["question"], prefixed))
    print("     вопросов в банке: %d" % total)
    check("ни один вопрос банка не изменён", not broken, broken[:3])

    live = [
        ("What does the word 'went' mean here?", ["go", "went", "gone", "going"]),
        ("Choose the best option: is or are?", ["is", "are", "be", "am"]),
        ("Is there any milk in the fridge?", ["is", "are", "some", "any"]),
        ("The film was ___ than I expected.", ["better", "good", "best", "well"]),
        ("What's the time?", ["three", "three o'clock", "at three", "third"]),
    ]
    changed = [(text, level_test._strip_inline_options(text, opts))
               for text, opts in live
               if level_test._strip_inline_options(text, opts) != text]
    check("живые формулировки не обрезаны", not changed, changed)


# =========================================================
# 4. Полный проход: наружу чистый вопрос
# =========================================================
class FakeClient:
    """Клиент, который всегда отвечает «грязным» вопросом со скриншота."""

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def complete(self, messages, max_tokens=None, temperature=None, timeout=None):
        self.prompts.append(messages[-1]["content"])
        return True, self.payload


def test_end_to_end():
    print("\n[4] Полный проход через _generate_question")
    client = FakeClient(SCREENSHOT_RAW)
    level_test.set_client(client)
    try:
        question = level_test._generate_question(3, "weather and seasons", set())
    finally:
        level_test.set_client(None)

    check("вопрос собран", bool(question), question)
    if not question:
        return
    check("наружу ушёл чистый вопрос",
          question["question"] == EXPECTED_QUESTION, question["question"])
    check("вариантов 4", len(question["options"]) == 4, question["options"])
    check("источник — модель, а не банк", question.get("source") == "model",
          question.get("source"))

    prompt = client.prompts[0] if client.prompts else ""
    print("\n[6] Промпт прямо запрещает варианты в поле question")
    check("промпт запрещает варианты внутри question",
          "only the question sentence" in prompt.lower()
          and "never put the" in prompt, prompt[:0])
    check("промпт запрещает маркеры «A)»", '\\"A)\\"' in prompt or 'A)"' in prompt,
          prompt[-260:])
    check("промпт запрещает вертикальную черту", "pipe character" in prompt,
          prompt[-160:])

    print("\n[5] Список «не повторяй» без вертикальной черты")
    avoid = level_test._avoid_block(["Question one?", "Question two?"])
    check("вертикальной черты нет", "|" not in avoid, avoid)
    check("оба вопроса в списке", "Question one?" in avoid and "Question two?" in avoid,
          avoid)


# =========================================================
# 5. Чистка устойчива к мусору
# =========================================================
def test_edge_cases():
    print("\n[7] Мусорные варианты не ломают разбор")
    cases = {
        "A)…без разделителя в конце": (
            '{"question": "Pick the right form:", "options": '
            '["is", "are", "am", "be"], "correct": 0}', None),
        "question с точкой в конце и маркерами": (
            '{"question": "Which is right? A) is B) are C) am D) be", '
            '"options": ["is", "are", "am", "be"], "correct": 0}',
            "Which is right?"),
        "пустой question после чистки": (
            '{"question": "A) is | B) are | C) am | D) be", "options": '
            '["is", "are", "am", "be"], "correct": 0}', "REJECT"),
        "question не строка": (
            '{"question": 42, "options": ["is", "are", "am", "be"], "correct": 0}',
            "REJECT"),
        "options не 4": (
            '{"question": "Pick one:", "options": ["is", "are"], "correct": 0}',
            "REJECT"),
    }
    for name, (raw, expected) in cases.items():
        q = level_test._parse_question(raw, 2, "work and study")
        if expected == "REJECT":
            check("%s → вопрос отклонён" % name, q is None, q)
        elif expected:
            check("%s → %r" % (name, expected),
                  q is not None and q["question"] == expected,
                  q and q["question"])
        else:
            check("%s → разобран" % name, q is not None, q)


class FakeController:
    """Контроллер-заглушка: отдаёт заранее известный вопрос."""

    def __init__(self, question):
        self.question = question
        self.cancelled = False

    def start(self, user_id, on_question=None, on_error=None):
        if on_question:
            on_question(self.question)

    def answer(self, user_id, index, on_feedback=None, on_question=None,
               on_result=None, on_error=None):
        return False

    def cancel(self, user_id):
        self.cancelled = True


def test_live_panel():
    print("\n[8] Живое окно теста: что видит ученик")
    import time

    import customtkinter as ctk
    import theme
    from ui.panels.level_test_panel import LevelTestPanel

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("700x700+40+40")
    theme.resolve_fonts(root)

    # тот же «грязный» ответ модели, но уже разобранный парсером
    parsed = level_test._parse_question(SCREENSHOT_RAW, 3, "weather and seasons")
    public = {
        "question": parsed["question"],
        "options": list(parsed["options"]),
        "difficulty": parsed["difficulty"],
        "difficulty_label": "B1",
        "index": 6,
        "total_max": 15,
        "finished": False,
        "result": None,
    }
    controller = FakeController(public)
    panel = None
    try:
        panel = LevelTestPanel(root, theme.DARK, controller, 1, ready_probe=None)
        for _ in range(60):
            root.update()
            time.sleep(0.02)

        shown = panel.question_lbl.cget("text")
        buttons = [btn.cget("text") for btn in panel.option_buttons]
        print("     в поле вопроса: %r" % shown)
        for i, text in enumerate(buttons):
            print("     кнопка %d: %r" % (i, text))

        check("в поле вопроса нет вариантов", not options_leaked(shown, buttons),
              options_leaked(shown, buttons))
        check("в поле вопроса нет маркеров «A)»…«D)»",
              not re.search(r"[\(\[]?[A-D][\)\].:]", shown), shown)
        check("варианты видны ровно в 4 кнопках",
              len([b for b in buttons if b.strip()]) == 4, buttons)
        check("текст в поле вопроса — только сам вопрос",
              shown.strip() == EXPECTED_QUESTION, shown)
    finally:
        try:
            if panel is not None:
                panel.destroy()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass


def main():
    print("=" * 62)
    print("ТЕСТ УРОВНЯ: варианты не должны дублироваться в тексте")
    print("=" * 62)
    test_screenshot_case()
    test_option_prefixes()
    test_bank_untouched()
    test_end_to_end()
    test_edge_cases()
    test_live_panel()

    print("\n" + "=" * 62)
    if FAILED:
        print("ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("   • " + name)
        return 1
    print("ВСЁ ЗЕЛЁНОЕ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
