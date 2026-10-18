# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_TRANSLATE.PY — подсказка перевода RU → EN
# =========================================================
#   python tests\test_translate.py   (окно НЕ создаётся)
#
# Проверяем:
#   1) определение русского текста;
#   2) фразник: частые фразы — мгновенно и без модели;
#   3) кэш: повтор не ходит в модель;
#   4) английский текст не переводится;
#   5) ошибки модели не ломают работу (ok=False + причина);
#   6) чистка ответа модели (кавычки, «Here is:», пояснения);
#   7) блок «только по-английски» в промпте — необязательный.
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import translate                                              # noqa: E402
import prompt_builder                                         # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeLLM:
    """Модель-заглушка: помнит, сколько раз её звали."""

    def __init__(self, answer="I am fine.", ok=True):
        self.answer = answer
        self.ok = ok
        self.calls = 0

    def complete(self, messages, max_tokens=None, temperature=None,
                 stop=None, timeout=None):
        self.calls += 1
        if not self.ok:
            return False, "boom"
        return True, self.answer


class DeadLLM:
    def complete(self, *a, **k):
        raise RuntimeError("нет соединения")


def main():
    print("=" * 60)
    print("Проверка подсказки перевода (translate.py)")
    print("=" * 60)

    # ---------- 1. Определение русского ----------
    print("\n[1] Определение русского текста")
    check("русский → есть кириллица", translate.has_cyrillic("Привет, как дела"))
    check("английский → нет", not translate.has_cyrillic("Hello, how are you"))
    check("смешанный → есть", translate.has_cyrillic("Hello, Дамиль"))
    check("цифры/знаки → нет", not translate.has_cyrillic("123 !?"))
    check("пусто → нет", not translate.has_cyrillic(""))

    # ---------- 2. Фразник ----------
    print("\n[2] Частые фразы — без модели")
    llm = FakeLLM()
    tr = translate.Translator(llm)
    ok, out = tr.translate("спасибо")
    check("«спасибо» переведено", ok and out == "Thank you!", out)
    check("модель НЕ вызывалась", llm.calls == 0, llm.calls)
    ok, out = tr.translate("Спасибо!")
    check("с восклицанием — тот же результат", out == "Thank you!", out)
    check("модель всё ещё не вызывалась", llm.calls == 0, llm.calls)
    ok, out = tr.translate("  ПРИВЕТ  ")
    check("регистр и пробелы не мешают", out == "Hi!", out)

    # ---------- 3. Кэш ----------
    print("\n[3] Кэш: повтор не ходит в модель")
    llm = FakeLLM("Мы пошли домой.")
    llm.answer = "We went home."
    tr = translate.Translator(llm)
    ok1, out1 = tr.translate("Мы пошли домой.")
    calls_after_first = llm.calls
    ok2, out2 = tr.translate("Мы пошли домой.")
    check("первый раз — модель вызвана", calls_after_first == 1, calls_after_first)
    check("второй раз — из кэша", llm.calls == 1, llm.calls)
    check("результат тот же", out1 == out2 == "We went home.", (out1, out2))

    # ---------- 4. Английский не трогаем ----------
    print("\n[4] Английский текст не переводится")
    llm = FakeLLM("НЕПРАВИЛЬНО")
    tr = translate.Translator(llm)
    ok, out = tr.translate("I like tea.")
    check("вернулся как есть", out == "I like tea.", out)
    check("модель не звали", llm.calls == 0, llm.calls)

    # ---------- 5. Ошибки ----------
    print("\n[5] Ошибки не ломают работу")
    tr = translate.Translator(FakeLLM(ok=False))
    ok, out = tr.translate("Новая фраза, которой нет в словаре.")
    check("ok=False при сбое модели", ok is False, ok)
    check("причина возвращается текстом", bool(out), out)

    tr = translate.Translator(DeadLLM())
    ok, out = tr.translate("Ещё одна фраза без словаря.")
    check("исключение модели поймано", ok is False, ok)

    tr = translate.Translator(None)
    ok, out = tr.translate("Фраза без модели вовсе.")
    check("нет модели → понятная причина", ok is False and "модел" in out.lower(), out)

    # ---------- 6. Чистка ответа ----------
    print("\n[6] Чистка ответа модели")
    cases = [
        ('"I am ready."', "I am ready."),
        ("Here is: I am ready.", "I am ready."),
        ("Translation: I am ready.", "I am ready."),
        ("I am ready.\nПотому что так говорят.", "I am ready."),
        ("I don't know.", "I don't know."),
    ]
    for raw, expected in cases:
        got = translate._clean_answer(raw)
        check("чистка %r" % raw[:28], got == expected, got)
    check("пояснение с кириллицей отбрасывается",
          translate._clean_answer("Это значит: я готов.") == "",
          translate._clean_answer("Это значит: я готов."))

    # ---------- 7. Промпт «только по-английски» ----------
    print("\n[7] Блок «только по-английски»")
    base = {"mistakes": {}, "strengths": [], "topics_passed": [], "total_lessons": 0}
    p_on = prompt_builder.build_system_prompt("lesson", base, "en", english_only=True)
    p_off = prompt_builder.build_system_prompt("lesson", base, "en")
    check("с флагом блок есть", "ALWAYS ANSWER IN ENGLISH" in p_on)
    check("без флага блока нет", "ALWAYS ANSWER IN ENGLISH" not in p_off)
    check("промпт без флага не изменился",
          len(p_off) < len(p_on), (len(p_off), len(p_on)))

    # ---------- 7b. Одно слово → до трёх значений ----------
    print("\n[7b] Словарный режим: слово с примерами")
    check("одно слово распознано", translate.is_single_word("ключ"))
    check("два слова — не слово", not translate.is_single_word("как дела"))
    check("со знаком вопроса — слово", translate.is_single_word("ключ?"))
    check("пусто — не слово", not translate.is_single_word(""))
    check("английское слово — тоже слово", translate.is_single_word("key"))

    class WordLLM:
        def __init__(self, answer):
            self.answer = answer
            self.calls = 0

        def complete(self, messages, max_tokens=None, temperature=None,
                     stop=None, timeout=None):
            self.calls += 1
            return True, self.answer

    answer = ("key — Open the door with this key.\n"
              "wrench — He fixed the car with a wrench.\n"
              "1. clef — The clef is on the staff.")
    llm = WordLLM(answer)
    tr = translate.Translator(llm)
    ok, lines = tr.translate_word("ключ")
    check("слово переведено", ok is True, ok)
    check("не больше трёх значений", len(lines) <= 3, len(lines))
    check("нумерация убрана", not lines[-1].startswith("1."), lines[-1])
    check("примеры на месте", "door" in lines[0].lower(), lines[0])
    check("модель вызвана один раз", llm.calls == 1, llm.calls)

    ok2, lines2 = tr.translate_word("ключ")
    check("повтор слова — из кэша", llm.calls == 1, llm.calls)
    check("результат тот же", lines2 == lines, lines2)

    # кириллица в ответе = пояснение, а не перевод
    clean = translate._clean_word_lines("key — дверной ключ\nwrench — гаечный")
    check("строки с кириллицей отброшены", clean == [], clean)

    tr = translate.Translator(None)
    ok, lines = tr.translate_word("слово")
    check("нет модели → понятная причина", ok is False and lines, lines)

    # фразник работает и для слов
    llm2 = WordLLM("НЕ ДОЛЖНО ВЫЗВАТЬСЯ")
    tr2 = translate.Translator(llm2)
    ok, out = tr2.translate("спасибо")
    check("частые фразы идут мимо модели", llm2.calls == 0, llm2.calls)
    # ---------- 8. Безопасность ----------
    print("\n[8] Безопасные значения")
    tr = translate.Translator(FakeLLM())
    check("пустая фраза → False", tr.translate("")[0] is False)
    check("пробелы → False", tr.translate("   ")[0] is False)
    check("None → False", tr.translate(None)[0] is False)
    tr = translate.Translator(FakeLLM(), cache_limit=2)
    tr.translate("Фраза один.")
    tr.translate("Фраза два.")
    tr.translate("Фраза три.")
    check("кэш ограничен", len(tr._cache) <= 2, len(tr._cache))

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
