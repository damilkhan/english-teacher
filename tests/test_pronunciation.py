# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PRONUNCIATION.PY — сверка произношения (без модели, сети, звука)
# =========================================================
#   python tests\test_pronunciation.py
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

import config  # noqa: E402
import pronunciation as pr  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


REF = "Open the door with this key."


def test_normalize():
    print("\n[1] Нормализация: регистр, пунктуация, сокращения, числа")
    check("регистр и точка убраны",
          pr.normalize_words("Open the door.") == ["open", "door"],
          pr.normalize_words("Open the door."))
    check("артикли выброшены (the, a, an)",
          pr.normalize_words("the a an cat") == ["cat"],
          pr.normalize_words("the a an cat"))
    check("запинки выброшены",
          pr.normalize_words("um I think uh") == ["i", "think"],
          pr.normalize_words("um I think uh"))
    check("сокращения раскрыты",
          pr.normalize_words("I'm here, don't go") == ["i", "am", "here", "do", "not", "go"],
          pr.normalize_words("I'm here, don't go"))
    check("'gonna' → going to",
          pr.normalize_words("I'm gonna go") == ["i", "am", "going", "to", "go"],
          pr.normalize_words("I'm gonna go"))
    check("числа словами (2 → two)",
          pr.normalize_words("I have 2 cats") == ["i", "have", "two", "cats"],
          pr.normalize_words("I have 2 cats"))
    check("21 → twenty one",
          pr.normalize_words("21") == ["twenty", "one"], pr.normalize_words("21"))
    check("апостроф-«ёлочка» тоже раскрывается",
          pr.normalize_words("I\u2019m fine") == ["i", "am", "fine"],
          pr.normalize_words("I\u2019m fine"))
    check("пустое → []", pr.normalize_words("") == [] and pr.normalize_words(None) == [])
    check("кириллица определяется", pr.has_cyrillic("привет") and not pr.has_cyrillic("hello"))


def test_good():
    print("\n[2] Сказал правильно → ✅ Похоже")
    r = pr.compare(REF, "open the door with this key")
    check("вердикт good", r.verdict == pr.GOOD, (r.verdict, r.score))
    check("сообщение «✅ Похоже!»", r.message == "✅ Похоже!", r.message)
    check("сходство 1.0", abs(r.score - 1.0) < 1e-6, r.score)
    check("нет замечаний", r.mistakes() == [], r.mistakes())
    r2 = pr.compare(REF, "Open the door with this key!")
    check("регистр и ! не мешают", r2.verdict == pr.GOOD, r2.verdict)
    r3 = pr.compare(REF, "open door with this key")
    check("потерянный артикль не ошибка", r3.verdict == pr.GOOD, (r3.verdict, r3.score))


def test_almost():
    print("\n[3] Одно слово не так → 🟡 Почти с разбором")
    r = pr.compare(REF, "open the door with this keys")
    check("вердикт almost", r.verdict == pr.ALMOST, (r.verdict, r.score))
    check("в сообщении есть «keys» и «key»",
          "keys" in r.message and "key" in r.message, r.message)
    check("одна ошибка в разборе", len(r.mistakes()) == 1, r.mistakes())
    check("формат «сказал вместо»", "вместо" in r.message, r.message)


def test_off_and_unrelated():
    print("\n[4] «Попробуй ещё» и «сказал своё» (молчим)")
    r = pr.compare(REF, "open the doors with this keys")
    check("две ошибки → почти/попробуй ещё",
          r.verdict in (pr.ALMOST, pr.OFF) and r.show, (r.verdict, r.score))
    r2 = pr.compare(REF, "i want to go home now")
    check("чужая фраза → unrelated (молчим)",
          r2.verdict == pr.UNRELATED and not r2.show, (r2.verdict, r2.score))
    check("у unrelated пустое сообщение", r2.message == "", r2.message)
    r3 = pr.compare(REF, "привет, как дела")
    check("русская речь → unrelated", r3.verdict == pr.UNRELATED, r3.verdict)
    r4 = pr.compare(REF, "")
    check("пустое услышанное → unrelated", r4.verdict == pr.UNRELATED)
    r5 = pr.compare("", "open the door")
    check("нет эталона → unrelated", r5.verdict == pr.UNRELATED)


def test_close_word():
    print("\n[5] Похожие слова: think/sink — «почти», cat/dog — мимо")
    check("think ≈ sink (0.6)", abs(pr._word_similarity("think", "sink") - 0.6) < 1e-9,
          pr._word_similarity("think", "sink"))
    check("то же слово → 1.0", pr._word_similarity("key", "key") == 1.0)
    check("cat ≠ dog (< 0.3)", pr._word_similarity("cat", "dog") < 0.3,
          pr._word_similarity("cat", "dog"))


def test_thresholds_from_config():
    print("\n[6] Пороги берутся из config.py (строже/мягче без правки кода)")
    heard = "open the door with this keys"
    old = (config.PRON_GOOD, config.PRON_ALMOST, config.PRON_RELATED)
    try:
        config.PRON_GOOD, config.PRON_ALMOST = 0.82, 0.50
        мягко = pr.compare(REF, heard).verdict
        config.PRON_GOOD, config.PRON_ALMOST = 0.99, 0.95
        строго = pr.compare(REF, heard).verdict
        check("строгие пороги меняют вердикт", мягко != строго, (мягко, строго))
        check("при строгих порогах это уже не «похоже»", строго != pr.GOOD, строго)
    finally:
        config.PRON_GOOD, config.PRON_ALMOST, config.PRON_RELATED = old
    check("значения по умолчанию в config есть",
          hasattr(config, "PRON_GOOD") and hasattr(config, "PRON_ALMOST")
          and hasattr(config, "PRON_MEMORY_SECONDS") and hasattr(config, "PRON_CHECK_ENABLED"))


def test_reference_from_hint():
    print("\n[7] Эталон из подсказки переводчика")
    check("фраза берётся целиком",
          pr.reference_from_hint("Open the door with this key.") ==
          "Open the door with this key.")
    word = "key \u2014 Open the door with this key."
    check("для слова эталон — пример после «—»",
          pr.reference_from_hint(word, single=True) == "Open the door with this key.",
          pr.reference_from_hint(word, single=True))
    check("слово без примера — само слово",
          pr.reference_from_hint("key", single=True) == "key")
    check("пусто → пусто", pr.reference_from_hint("") == "" and pr.reference_from_hint(None) == "")


def test_extra_words():
    print("\n[8] Лишние слова и пропуски объясняются словами")
    r = pr.compare("Good morning", "good morning everyone")
    check("лишнее слово показано", "лишнее" in r.message, r.message)
    r2 = pr.compare("Thank you very much", "thank you")
    check("пропуск показан", "пропустил" in r2.message, r2.message)
    check("вердикт не «похоже»", r2.verdict != pr.GOOD, (r2.verdict, r2.score))


def test_speed():
    print("\n[9] Скорость: сверка не тормозит диалог")
    import time
    text = ("Hi! I'm so glad you're here today. We're going to talk about food "
            "and breakfast, and then we will practise the present perfect.")
    t0 = time.perf_counter()
    for _ in range(100):
        pr.compare(text, text[:-10] + " keys")
    ms = (time.perf_counter() - t0) * 1000 / 100
    check("одна сверка быстрее 5 мс (%.2f мс)" % ms, ms < 5.0, ms)


def main():
    print("=" * 60)
    print("Проверка pronunciation.py (сверка произношения)")
    print("=" * 60)
    test_normalize()
    test_good()
    test_almost()
    test_off_and_unrelated()
    test_close_word()
    test_thresholds_from_config()
    test_reference_from_hint()
    test_extra_words()
    test_speed()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
