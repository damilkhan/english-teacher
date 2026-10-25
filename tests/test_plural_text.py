# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PLURAL_TEXT.PY — русские числительные («1 слово», «2 слова»)
# =========================================================
#   python tests\test_plural_text.py   (Tk и микрофон НЕ нужны)
#
# Повод (найдено учеником 25.10.2026): бот писал «Давай повторим 1 слов» —
# число подставляли в готовый шаблон, не склоняя слово.
#
# Проверяем:
#   1) 1 слово / 2 слова / 5 слов — основные формы;
#   2) ловушки 11–14 (11 слов, а не «11 слово») и 21/22 (21 слово, 22 слова);
#   3) ноль и большие числа;
#   4) мусор на входе не падает;
#   5) готовые наборы (WORDS, QUESTIONS) и plural_ru по умолчанию (урок);
#   6) в интерфейсе НЕ осталось шаблонов вида «%d слов» (число без склонения);
#   7) сообщение повторения собирается правильно для 1, 2 и 5 слов.
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

import ru_text                                              # noqa: E402
import vocabulary                                           # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    if ok:
        print("  ✅ %s" % name)
    else:
        print("  ❌ %s  →  %s" % (name, detail))
        FAILED.append(name)


def test_basic_forms():
    """[1] Основные формы."""
    print("\n[1] 1 слово / 2 слова / 5 слов")
    check("1 → слово", ru_text.words(1) == "1 слово", ru_text.words(1))
    check("2 → слова", ru_text.words(2) == "2 слова", ru_text.words(2))
    check("5 → слов", ru_text.words(5) == "5 слов", ru_text.words(5))
    check("3 → слова", ru_text.words(3) == "3 слова", ru_text.words(3))
    check("4 → слова", ru_text.words(4) == "4 слова", ru_text.words(4))


def test_traps():
    """[2] Ловушки 11–14 и 21/22."""
    print("\n[2] 11–14, 21, 22")
    check("11 → слов", ru_text.words(11) == "11 слов", ru_text.words(11))
    check("12 → слов", ru_text.words(12) == "12 слов", ru_text.words(12))
    check("14 → слов", ru_text.words(14) == "14 слов", ru_text.words(14))
    check("21 → слово", ru_text.words(21) == "21 слово", ru_text.words(21))
    check("22 → слова", ru_text.words(22) == "22 слова", ru_text.words(22))
    check("111 → слов", ru_text.words(111) == "111 слов", ru_text.words(111))
    check("101 → слово", ru_text.words(101) == "101 слово", ru_text.words(101))


def test_zero_and_big():
    """[3] Ноль и большие числа."""
    print("\n[3] ноль и большие числа")
    check("0 → слов", ru_text.words(0) == "0 слов", ru_text.words(0))
    check("1000 → слов", ru_text.words(1000) == "1000 слов", ru_text.words(1000))


def test_broken_input():
    """[4] Мусор на входе не падает."""
    print("\n[4] мусор на входе")
    for bad in (None, "бла", "", [], 3.7):
        try:
            value = ru_text.words(bad)
            ok = isinstance(value, str) and value
        except Exception as exc:                       # noqa: BLE001
            ok = False
            value = "исключение: %s" % exc
        check("вход %r не падает" % (bad,), ok, value)
    check("3.7 → «3 слова» (округление вниз)",
          ru_text.words(3.7) == "3 слова", ru_text.words(3.7))


def test_ready_sets():
    """[5] Готовые наборы форм и plural_ru по умолчанию."""
    print("\n[5] наборы форм")
    check("WORDS — тройка про слова", ru_text.WORDS == ("слово", "слова", "слов"),
          ru_text.WORDS)
    check("QUESTIONS — 10 вопросов",
          ru_text.questions(10) == "10 вопросов", ru_text.questions(10))
    check("QUESTIONS — 1 вопрос",
          ru_text.questions(1) == "1 вопрос", ru_text.questions(1))
    check("plural_ru по умолчанию — урок",
          ru_text.plural_ru(1) == "урок" and ru_text.plural_ru(2) == "урока"
          and ru_text.plural_ru(5) == "уроков",
          (ru_text.plural_ru(1), ru_text.plural_ru(2), ru_text.plural_ru(5)))


def test_no_raw_plural_in_ui():
    """[6] В интерфейсе нет шаблонов «%d слов» без склонения."""
    print("\n[6] сырых шаблонов в ui/ не осталось")
    bad = []
    for folder in ("ui", "controllers"):
        for name in sorted(os.listdir(os.path.join(ROOT, folder))):
            if not name.endswith(".py"):
                continue
            path = os.path.join(ROOT, folder, name)
            text = open(path, encoding="utf-8").read()
            for needle in ('"%d слов', "'%d слов", '"%d вопрос', "'%d вопрос"):
                if needle in text:
                    bad.append("%s: %s" % (path, needle))
    check("ни одного «%d слов»/«%d вопрос»", not bad, bad)


def test_review_message():
    """[7] Сообщение повторения для 1, 2 и 5 слов."""
    print("\n[7] сообщение «Давай повторим …»")
    cases = [(1, "1 слово"), (2, "2 слова"), (5, "5 слов"), (11, "11 слов")]
    for count, expected in cases:
        text = "📚 Давай повторим %s." % ru_text.words(count)
        check("слов %d → «%s»" % (count, expected), expected in text, text)
    # «1 слово» содержит подстроку «1 слов», поэтому ищем форму с точкой
    one_text = "📚 Давай повторим %s." % ru_text.words(1)
    check("нет «1 слов.»", "1 слов." not in one_text, one_text)
    check("а есть «1 слово.»", one_text.endswith("1 слово."), one_text)
    check("счёт слов берётся из словаря",
          len(vocabulary.due_cards([], today=None)) == 0)


def main():
    print("=" * 60)
    print("ТЕСТ: русские числительные («1 слово», «2 слова», «5 слов»)")
    print("=" * 60)
    test_basic_forms()
    test_traps()
    test_zero_and_big()
    test_broken_input()
    test_ready_sets()
    test_no_raw_plural_in_ui()
    test_review_message()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
