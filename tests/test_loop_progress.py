# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LOOP_PROGRESS.PY — работа над ошибками: процент и порог (§80)
# =========================================================
#   python tests/test_loop_progress.py
#
# Идея ученика 15.11.2026: вместо экзамена — петля «работа над ошибками».
# В списке уроков напротив неё прогресс-бар с процентом (красный → зелёный)
# и меткой порога. Здесь проверяется ТОЛЬКО счёт: без базы, без окна.
#   1) какие правила берём в сессию (пробелы, самые частые, не больше 3);
#   2) процент одного правила (серия из 3 → 100 %);
#   3) процент точки и прохождение порога 80 %;
#   4) «пробелов нет» → 100 %, точка пройдена (а не ноль);
#   5) цвет бара: красный → жёлтый → зелёный, выше порога не темнеет.
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

import loop_progress as lp


FAILED = []


def check(name, ok, detail=""):
    mark = "\u2705" if ok else "\u274c"
    print("  " + mark + " " + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def make_rows(rule, n, wrong="wrong", correct="correct"):
    return [{"rule": rule, "wrong": wrong + str(i), "correct": correct + str(i)}
            for i in range(n)]


ROWS = (make_rows("word_choice", 9) + make_rows("verb_form", 5)
        + make_rows("article", 4) + make_rows("past_simple", 3)
        + make_rows("plural", 1))


def test_session_rules():
    print("\n[1] Какие правила берём")
    got = [b["rule"] for b in lp.session_rules(ROWS)]
    check("самые частые первыми", got == ["word_choice", "verb_form", "article"], got)
    check("не больше трёх", len(got) == 3, got)
    all_rules = [b["rule"] for b in lp.session_rules(ROWS, limit=0)]
    check("limit=0 — все пробелы", "past_simple" in all_rules, all_rules)
    check("не-пробел (plural 1 раз) не берём", "plural" not in all_rules, all_rules)
    check("пусто -> пусто", lp.session_rules([]) == [])


def test_rule_percent():
    print("\n[2] Процент одного правила")
    check("нет серии -> 0", lp.rule_percent("article", {}) == 0)
    check("1 из 3 -> 33", lp.rule_percent("article", {"article": {"streak": 1}}) == 33)
    check("2 из 3 -> 67", lp.rule_percent("article", {"article": {"streak": 2}}) == 67)
    check("3 из 3 -> 100", lp.rule_percent("article", {"article": {"streak": 3}}) == 100)
    check("усвоено -> 100",
          lp.rule_percent("article", {"article": {"streak": 0,
                                                  "mastered_at": "2026-11-15"}}) == 100)
    check("серия больше нормы не ломает",
          lp.rule_percent("article", {"article": {"streak": 9}}) == 100)
    check("чужое правило не влияет",
          lp.rule_percent("article", {"verb_form": {"streak": 3}}) == 0)


def test_progress():
    print("\n[3] Процент точки")
    empty = lp.progress(rows=ROWS, state={})
    check("ничего не усвоено -> 0", empty["percent"] == 0, empty)
    check("порог не пройден", empty["pass"] is False, empty)
    check("три правила в отчёте", len(empty["rules"]) == 3, empty["rules"])
    check("порог в ответе", empty["pass_percent"] == lp.PASS_PERCENT, empty)

    half = lp.progress(rows=ROWS, state={"word_choice": {"streak": 3},
                                         "verb_form": {"streak": 3}})
    check("2 из 3 усвоено -> 67", half["percent"] == 67, half)
    check("67 < 80 — не пройдено", half["pass"] is False, half)

    done = lp.progress(rows=ROWS, state={"word_choice": {"streak": 3},
                                         "verb_form": {"streak": 3},
                                         "article": {"streak": 3}})
    check("всё усвоено -> 100", done["percent"] == 100, done)
    check("100 >= 80 — пройдено", done["pass"] is True, done)

    near = lp.progress(rows=ROWS, state={"word_choice": {"streak": 3},
                                         "verb_form": {"streak": 3},
                                         "article": {"streak": 2}})
    check("3+3+2 -> 89 — пройдено", near["percent"] == 89 and near["pass"], near)

    weak = lp.progress(rows=ROWS, state={"word_choice": {"streak": 3},
                                         "verb_form": {"streak": 2},
                                         "article": {"streak": 1}})
    check("3+2+1 -> 67 — не пройдено",
          weak["percent"] == 67 and not weak["pass"], weak)


def test_no_gaps():
    print("\n[4] Пробелов нет")
    none = lp.progress(rows=make_rows("plural", 1), state={})
    check("100 %, а не 0", none["percent"] == 100, none)
    check("точка пройдена", none["pass"] is True, none)
    check("флаг «нечего отрабатывать»", none["has_rules"] is False, none)
    check("список правил пуст", none["rules"] == [], none["rules"])


def test_color():
    print("\n[5] Цвет бара")
    red, yellow, green = lp.color(0), lp.color(40), lp.color(100)
    check("0 % — красный", red[0] > 200 and red[1] < 120, red)
    check("середина порога — жёлтый", yellow[0] > 200 and yellow[1] > 150, yellow)
    check("100 % — зелёный", green[1] > 150 and green[2] > 60, green)
    check("выше порога не меняется",
          lp.color(100) == lp.color(90), (lp.color(90), lp.color(100)))
    check("цвет — hex", lp.to_hex((239, 68, 68)) == "#EF4444", lp.to_hex((239, 68, 68)))
    check("мусор в цвете не ломает", lp.to_hex(None) == "#000000", lp.to_hex(None))


def main():
    test_session_rules()
    test_rule_percent()
    test_progress()
    test_no_gaps()
    test_color()
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
