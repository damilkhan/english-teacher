# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_SCENE_HOTWORDS.PY — подсказки распознаванию в сцене (§83)
# =========================================================
#   python tests/test_scene_hotwords.py
#
# Живой урок 15.11.2026 (city/2.1): ученик говорил «give me a bill, please»,
# а записывалось «give me a beer, please» — 6 попыток подряд. Причина:
# подсказки распознаванию для слота anything содержали «beer» и НЕ содержали
# «bill». Проверяется:
#   1) bill/check/pay есть в подсказках ЛЮБОГО слота сцены;
#   2) предметы слота не вытеснены универсальными словами;
#   3) «recommend» добавляется, только если слот его поддерживает;
#   4) мусора нет (дубли, пустые, короткие слова).
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

import scene_reactions as R

FAILED = []


def check(name, ok, detail=""):
    mark = "\u2705" if ok else "\u274c"
    print("  " + mark + " " + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


SLOTS = ("anything", "side", "main", "starter", "drink", "payment", "people",
         "table", "menu", "ready", "thanks", "food_ok", "bread", "dessert",
         "goodbye")


def test_bill_always():
    print("\n[1] Счёт в подсказках любого слота")
    bad = []
    for slot in SLOTS:
        words = [w.lower() for w in R.slot_hotwords(slot)]
        if not words:
            continue
        if "bill" not in words:
            bad.append(slot)
    check("во всех слотах сцены есть bill", not bad, bad)
    words = [w.lower() for w in R.slot_hotwords("anything")]
    check("beer остался (это настоящее блюдо)", "beer" in words, words)
    check("предметы идут раньше служебных слов",
          words.index("beer") < words.index("bill"), words)


def test_items_kept():
    print("\n[2] Предметы слота не вытеснены")
    main_words = [w.lower() for w in R.slot_hotwords("main")]
    check("у main есть steak и seafood",
          "steak" in main_words and "seafood" in main_words, main_words)
    side = [w.lower() for w in R.slot_hotwords("side")]
    check("у side есть soup и salad", "soup" in side and "salad" in side, side)
    payment = [w.lower() for w in R.slot_hotwords("payment")]
    check("у payment есть by card и in cash",
          "by card" in payment and "in cash" in payment, payment)


def test_recommend_only_where_supported():
    print("\n[3] recommend — только где слот его понимает")
    drink = [w.lower() for w in R.slot_hotwords("drink")]
    payment = [w.lower() for w in R.slot_hotwords("payment")]
    check("в drink есть recommend", "recommend" in drink, drink)
    check("в payment нет recommend", "recommend" not in payment, payment)


def test_clean():
    print("\n[4] Мусора нет")
    bad = []
    for slot in SLOTS:
        words = R.slot_hotwords(slot)
        low = [w.lower() for w in words]
        if len(low) != len(set(low)):
            bad.append(slot + ":дубли")
        for word in words:
            if len(word) < 3:
                bad.append(slot + ":короткое " + word)
            if not word.strip():
                bad.append(slot + ":пустое")
    check("без дублей, пустых и коротких слов", not bad, bad[:8])
    check("незнакомый слот — пусто", R.slot_hotwords("нет-такого") == [])


def main():
    test_bill_always()
    test_items_kept()
    test_recommend_only_where_supported()
    test_clean()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("  - " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())