# -*- coding: utf-8 -*-
# =========================================================
# TEST_ANALYST_JUNK.PY — в базу пробелов не идёт мусор
# =========================================================
#   python tests\test_analyst_junk.py
#
# Живой экзамен city/2.4 (09.11.2026) записал в базу:
#   «ich ee den kähnets, fuhr -> I ate Kenneth Ford» — мусор распознавания;
#   «ago -> »                                      — пустая правка;
#   «hamburger -> a cold drink or a hot drink»     — заметка «Did not answer
#                                                    the specific question».
# Такие пары не про язык: следующее занятие начиналось дриллом по ним.
#
# Проверяем:
#   1) мусор отсекается (пустая сторона, не-английский текст, «не по теме»);
#   2) НАСТОЯЩИЕ ошибки остаются;
#   3) отсев работает и на живых данных из profiles/stats_1.db (если он есть).
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from roles import analyst                                    # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def cleaned(items):
    """Что осталось после нормализации."""
    return analyst._clean_errors(items)


def pairs(items):
    return [(i["wrong"], i["correct"]) for i in cleaned(items)]


def main():
    print("=" * 60)
    print("База пробелов: мусор не записывается")
    print("=" * 60)

    print("\n[1] Пустая сторона пары — не ошибка")
    got = pairs([{"wrong": "ago", "correct": "", "type": "grammar"}])
    check("пустое «правильно» отсечено", got == [], got)
    got = pairs([{"wrong": "", "correct": "a bag", "type": "grammar"}])
    check("пустое «было» отсечено", got == [], got)

    print("\n[2] Не-английский мусор — не ошибка")
    got = pairs([{"wrong": "ich ee den kähnets, fuhr",
                  "correct": "I ate Kenneth Ford", "type": "grammar"}])
    check("немецкий бред отсечён", got == [], got)
    got = pairs([{"wrong": "einen gen-d-food",
                  "correct": "any other good food",
                  "note": "Mixed German/English, needs full English phrase",
                  "type": "grammar"}])
    check("второй немецкий бред отсечён", got == [], got)
    got = pairs([{"wrong": "вилка", "correct": "fork", "type": "vocabulary"}])
    check("кириллица в «было» отсечена", got == [], got)

    print("\n[3] «Ответил не на вопрос» — не пробел в языке")
    got = pairs([{"wrong": "hamburger",
                  "correct": "a cold drink or a hot drink",
                  "note": "Did not answer the specific question about drink type.",
                  "type": "grammar"}])
    check("не по теме отсечено", got == [], got)
    got = pairs([{"wrong": "yes", "correct": "no",
                  "note": "Off topic for this question.",
                  "type": "grammar"}])
    check("«off topic» отсечено", got == [], got)

    print("\n[4] НАСТОЯЩИЕ ошибки остаются")
    keep = [
        ("your menu of restaurant", "your restaurant menu"),
        ("like order", "like ordering"),
        ("i'm looking a jacket", "I'm looking for a jacket"),
        ("interesting", "interested"),
        ("in the wild nature", "in the wild"),
    ]
    got = pairs([{"wrong": w, "correct": c, "type": "grammar"} for w, c in keep])
    check("все настоящие правки на месте", got == keep, got)

    print("\n[5] Живая база: мусор сегодняшнего дня больше не проходит")
    try:
        import stats_store
        rows = stats_store.rows(None) or []
    except Exception as exc:                              # noqa: BLE001
        rows = []
        print("     (база недоступна: %s)" % exc)
    today = [r for r in rows if str(r.get("date") or "").startswith("2026-11-09")]
    bad = [r for r in today if analyst.is_junk_pair(r.get("wrong"), r.get("correct"))]
    good = [r for r in today if not analyst.is_junk_pair(r.get("wrong"),
                                                         r.get("correct"))]
    print("     записей за 09.11: %d, отсеется: %d" % (len(today), len(bad)))
    check("мусорные пары найдены и отсечены", len(bad) >= 2,
          [(r.get("wrong"), r.get("correct")) for r in bad])
    check("настоящих ошибок больше, чем мусора",
          len(good) > len(bad), (len(good), len(bad)))
    for row in bad:
        print("     отсеяно: %r -> %r" % (row.get("wrong"), row.get("correct")))

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
