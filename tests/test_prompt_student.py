# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PROMPT_STUDENT.PY — личность ученика и «канал размышлений»
# =========================================================
#   python tests\test_prompt_student.py
#
# Проверяем два дефекта из переписки с Джейн:
#   1) Джейн обращалась к ученику в ЖЕНСКОМ роде (род ученика угадывался);
#   2) ответ «протекал» блоком размышлений <|channel>thought … и не отвечал
#      на вопрос (ученику показывалась внутренняя «кухня» модели).
#
# Тесты:
#   [1] личность ученика влияет ТОЛЬКО при передаче student (обратная совместимость);
#   [2] пол → грамматические формы (male/female/other), имя подставляется;
#   [3] clean_response вырезает канал размышлений (и старые случаи целы);
#   [4] интеграция: ChatController передаёт имя/пол в промпт.
# =========================================================

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import prompt_builder          # noqa: E402
import profile_store           # noqa: E402
import user_manager            # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


BASE_PROFILE = {"mistakes": {}, "strengths": [], "topics_passed": [], "total_lessons": 0}


# =========================================================
# 1. Обратная совместимость
# =========================================================
def test_backward_compat():
    print("\n[1] Без student промпт не меняется")
    for mode in ("lesson", "free"):
        for lang in ("ru", "en"):
            plain = prompt_builder.build_system_prompt(mode, BASE_PROFILE, lang)
            none = prompt_builder.build_system_prompt(mode, BASE_PROFILE, lang, student=None)
            empty = prompt_builder.build_system_prompt(mode, BASE_PROFILE, lang, student={})
            check(f"mode={mode} lang={lang}: student=None совпадает",
                  plain == none, "разная длина")
            check(f"mode={mode} lang={lang}: student={{}} совпадает",
                  plain == empty, "разная длина")
    check("student=None: в промпте нет блока STUDENT",
          "STUDENT:" not in prompt_builder.build_system_prompt("lesson", BASE_PROFILE, "ru"))


# =========================================================
# 2. Род и имя
# =========================================================
def test_gender_forms():
    print("\n[2] Пол ученика → грамматические формы")
    m = prompt_builder.build_system_prompt("lesson", BASE_PROFILE, "ru",
                                           student={"name": "Дамиль", "gender": "male"})
    check("имя ученика в промпте", "Дамиль" in m)
    check("male → MASCULINE формы", "MASCULINE forms about the student" in m)
    check("запрет женских форм о ученике", "NEVER use feminine forms about the student" in m)

    f = prompt_builder.build_system_prompt("lesson", BASE_PROFILE, "ru",
                                           student={"name": "Аня", "gender": "female"})
    check("female → FEMININE формы о ученике", "FEMININE forms about the student" in f)

    o = prompt_builder.build_system_prompt("lesson", BASE_PROFILE, "ru",
                                           student={"name": "Сэм", "gender": "other"})
    check("other → нейтральные формы", "gender-neutral phrasing" in o)

    n = prompt_builder.build_system_prompt("lesson", BASE_PROFILE, "ru",
                                           student={"name": "Дамиль"})
    check("только имя (без пола) → нейтральные формы", "Дамиль" in n and "gender-neutral" in n)

    # блок ученика добавляется В КОНЕЦ: базовый промпт остаётся префиксом
    plain = prompt_builder.build_system_prompt("lesson", BASE_PROFILE, "ru")
    check("базовый промпт — префикс промпта с учеником", m.startswith(plain))

    # порядок с другими опциональными блоками (уровень + слабые темы)
    rich = dict(BASE_PROFILE, weak_topics=[{"topic": "travel", "correct": 0, "total": 2}])
    full = prompt_builder.build_system_prompt("lesson", rich, "ru", level="B1",
                                              student={"name": "Д", "gender": "male"})
    check("уровень, слабые темы и ученик уживаются",
          "STUDENT ENGLISH LEVEL: B1" in full and "WEAK TOPICS" in full
          and "STUDENT: Д" in full)


# =========================================================
# 3. clean_response: канал размышлений
# =========================================================
def test_clean_thought():
    print("\n[3] clean_response: канал размышлений вырезан")
    raw = ('<|channel>thought\n'
           'The user asked a question in Russian: "Ты знаешь как меня зовут?"\n'
           'I should acknowledge that I dont know the name yet.\n\n'
           'Plan:\n1. Acknowledge.\n2. State that I dont know.\n3.')
    out = prompt_builder.clean_response(raw)
    check("монолог размышлений не показан", "thought" not in out.lower() and "Plan" not in out, repr(out))

    raw2 = '<|channel>thought\nдолго думаю...\n<channel|> Тебя зовут Дамиль! 😊'
    out2 = prompt_builder.clean_response(raw2)
    check("ответ после <channel|> сохранён", out2.strip() == "Тебя зовут Дамиль! 😊", repr(out2))

    # старые случаи (из smoke_test) должны оставаться прежними
    legacy = [
        ("Привет!<end_of_turn>", "Привет!"),
        ("<|thought|>размышляю\nОтвет", "Ответ"),
        ("Текст <|channel|> ещё", "Текст  ещё"),
        ("ГотовоRU", "Готово"),
        ("  пробелы  ", "пробелы"),
        ("", ""),
        (None, ""),
    ]
    for raw_case, expected in legacy:
        got = prompt_builder.clean_response(raw_case)
        check("наследие clean_response(%r)" % (raw_case,), got == expected,
              "получено %r, ждали %r" % (got, expected))


# =========================================================
# 4. Интеграция: ChatController передаёт личность
# =========================================================
def test_controller_identity():
    print("\n[4] ChatController передаёт имя/пол в промпт")
    from controllers.chat_controller import ChatController

    class CaptureLLM:
        def __init__(self):
            self.prompts = []

        def complete(self, prompt, **kwargs):
            self.prompts.append(prompt)
            return True, "Привет! Как дела?"

    real_dir, real_last = user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE
    tmp = tempfile.mkdtemp(prefix="et_identity_")
    try:
        user_manager.PROFILES_DIR = tmp
        user_manager.LAST_USER_FILE = os.path.join(tmp, "last_user.txt")
        profile_store.set_active_user(None)
        uid = user_manager.create_user("Дамиль", "male", 30, "B1", "", "🙂")["id"]

        llm = CaptureLLM()
        chat = ChatController(llm=llm, dispatch=lambda fn: fn(), mode="lesson",
                              lang="ru", user_id=uid)
        chat.on_message = lambda *a: None
        chat.on_status = lambda *a: None
        chat.on_busy = lambda *a: None
        chat.on_response = lambda *a: None
        chat.send("привет")
        deadline = time.time() + 5
        while chat.busy and time.time() < deadline:
            time.sleep(0.02)

        prompt = llm.prompts[0] if llm.prompts else ""
        check("в промпт попало имя ученика", "Дамиль" in prompt)
        check("в промпт попал род (MASCULINE)", "MASCULINE forms about the student" in prompt)
    finally:
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE = real_dir, real_last
        profile_store.set_active_user(None)


def test_mistake_line():
    print("\n[5] Недавние ошибки: wrong→correct, а не ответ Джейн")
    structured = dict(BASE_PROFILE, mistakes={
        "grammar": [{"jane_response": "Извините, я не могу ответить на это.",
                     "wrong": "go", "correct": "went", "note": "tense"}],
        "vocabulary": []})
    p = prompt_builder.build_system_prompt("lesson", structured, "ru")
    check("в промпте 'go → went'", "go → went" in p, p)
    check("фолбэк Джейн НЕ попал как ошибка", "Извините, я не могу ответить" not in p)

    legacy = dict(BASE_PROFILE, mistakes={
        "grammar": [{"jane_response": "You should use Past Simple here"}],
        "vocabulary": []})
    p2 = prompt_builder.build_system_prompt("lesson", legacy, "ru")
    check("старая запись (jane_response) читается как раньше",
          "You should use Past Simple here" in p2)


def main():
    print("=" * 60)
    print("Проверка личности ученика и «канала размышлений»")
    print("=" * 60)

    test_backward_compat()
    test_gender_forms()
    test_clean_thought()
    test_controller_identity()
    test_mistake_line()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
