# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PHRASES.PY — библиотека смысловых пар (шаг 2, §55)
# =========================================================
#   python tests\test_phrases.py
#
# Что проверяем:
#   1) файл data/phrase_pairs_a2.json: 42 правила, по 6 фраз, поля на месте;
#   2) фразы эталона не повторяются, файл в LF;
#   3) pick: 3 фразы подряд, второе окно — ДРУГИЕ три, вместе все 6;
#   4) контраст: у пары lie/lay в одной тройке обе стороны (решение 68);
#   5) rule_for_words: база ошибок (word_choice) находит свою пару;
#   6) чужая пара и мусор — None, а не догадка (ученик: точность);
#   7) библиотека кэшируется, describe отдаёт строку «о чём пара».
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

import phrases                    # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def test_file():
    print("\n[1] файл библиотеки")
    lib = phrases.library()
    check("правил 42", len(lib) == 42, len(lib))
    bad = []
    for rule_id, item in lib.items():
        if len(item.get("phrases") or []) != 6:
            bad.append(rule_id + " фраз %d" % len(item.get("phrases") or []))
        if not item.get("pair"):
            bad.append(rule_id + " без pair")
        if len(item.get("words") or []) != 2:
            bad.append(rule_id + " words %r" % (item.get("words"),))
    check("у каждого правила pair, words и 6 фраз", not bad, bad[:5])
    ids = phrases.rule_ids()
    check("id начинаются с уровня", all(i.startswith("a2.") for i in ids),
          [i for i in ids if not i.startswith("a2.")][:3])
    check("lay_lie на месте", "a2.lay_lie" in lib)


def test_phrases():
    print("\n[2] фразы и схема")
    seen = {}
    problems = []
    total = 0
    for rule_id in phrases.rule_ids():
        for i, ph in enumerate(phrases.all_phrases(rule_id)):
            total += 1
            for field in ("ru", "en", "why", "hint2"):
                if not ph.get(field):
                    problems.append("%s[%d] пустое %s" % (rule_id, i, field))
            if not ph["hint2"].startswith("Начни:"):
                problems.append("%s[%d] hint2 без «Начни:»" % (rule_id, i))
            key = ph["en"].lower()
            if key in seen:
                problems.append("дубль %r" % ph["en"])
            seen[key] = rule_id
    check("фраз 252", total == 252, total)
    check("все поля заполнены, hint2 с «Начни:»", not problems, problems[:5])
    raw = open(phrases.path_for("a2"), "rb").read()
    check("файл в LF", b"\r\n" not in raw)


def test_pick():
    print("\n[3] pick — тройка фраз")
    first = phrases.pick("a2.lay_lie", 0)
    second = phrases.pick("a2.lay_lie", 1)
    check("первое окно — 3 фразы", len(first) == 3, len(first))
    check("второе окно — 3 фразы", len(second) == 3, len(second))
    check("окна не пересекаются",
          not set(p["en"] for p in first) & set(p["en"] for p in second))
    check("вместе — все 6", len(first + second) == 6)
    check("окно по кругу не падает", len(phrases.pick("a2.lay_lie", 2)) == 3)
    check("чужое правило — пусто", phrases.pick("a2.no_such") == [])


def test_contrast():
    print("\n[4] контраст пары в одной тройке")
    trio = phrases.pick("a2.lay_lie", 0)
    text = " ".join(p["en"] for p in trio).lower()
    check("в тройке есть lie", "lie" in text)
    check("в тройке есть lay", "lay" in text)
    check("подсказка — ситуация, а не перевод",
          all(len(p["ru"]) > 20 for p in trio))


def test_rule_for_words():
    print("\n[5] связь с базой ошибок")
    check("go to lay down -> go to lie down",
          phrases.rule_for_words("go to lay down", "go to lie down") == "a2.lay_lie",
          phrases.rule_for_words("go to lay down", "go to lie down"))
    check("lay -> lie", phrases.rule_for_words("lay", "lie") == "a2.lay_lie")
    check("lay down -> lie down",
          phrases.rule_for_words("lay down", "lie down") == "a2.lay_lie")


def test_no_guess():
    print("\n[6] не гадаем")
    check("eaten -> ate — не пара библиотеки",
          phrases.rule_for_words("eaten", "ate") is None,
          phrases.rule_for_words("eaten", "ate"))
    check("it's name -> its name — не пара библиотеки",
          phrases.rule_for_words("it's name", "its name") is None)
    check("пустое — None", phrases.rule_for_words("", "") is None)
    check("одинаковые тексты — None", phrases.rule_for_words("lie", "lie") is None)


def test_misc():
    print("\n[7] мелочи")
    check("кэш работает", phrases.library() is phrases.library())
    check("rule() чужого id — None", phrases.rule("a2.nope") is None)
    check("describe не пустой", "lie" in phrases.describe("a2.lay_lie"),
          phrases.describe("a2.lay_lie"))
    check("файла нет — пусто, без падения",
          phrases.library("zz", refresh=True) == {})


def main():
    test_file()
    test_phrases()
    test_pick()
    test_contrast()
    test_rule_for_words()
    test_no_guess()
    test_misc()
    print("\n" + ("ВСЁ ПРОЙДЕНО" if not FAILED else "ПРОВАЛЕНО: %d" % len(FAILED)))
    for name in FAILED:
        print("  - " + name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
