# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_TRANSLATE_TASK.PY — уроки-«выявление пробелов» (§82)
# =========================================================
#   python tests/test_translate_task.py
#
# Решение ученика 15.11.2026: до работы над ошибками уроки — это перевод
# РУССКОЙ фразы, а не ответ официанту (там реплика-вопрос засчитывалась за
# ответ и шаг шёл дальше). Проверяется:
#   1) файл фраз читается, кэш по mtime, битые строки не ломают;
#   2) pick() идёт по кругу, нет урока — None;
#   3) сверка ответа: OK (код), NO (пусто/по-русски), MAYBE (решает модель);
#   4) у каждой фразы есть эталон, правило и объяснение.
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

import gaps
import translate_task as T

FAILED = []


def check(name, ok, detail=""):
    mark = "\u2705" if ok else "\u274c"
    print("  " + mark + " " + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def test_load():
    print("\n[1] Материал")
    all_tasks = T.load()
    check("есть уроки", bool(all_tasks), all_tasks.keys())
    total = sum(len(v) for v in all_tasks.values())
    check("в пилоте 18 фраз", total == 18, total)
    check("city/5.1 есть", T.has("city/5.1"))
    check("незнакомый урок — пусто", not T.has("city/9.9"))
    check("для незнакомого урока []", T.phrases_for("city/9.9") == [])
    check("уроки отсортированы", T.covered_lessons() == sorted(T.covered_lessons()),
          T.covered_lessons())


def test_pick():
    print("\n[2] Какая фраза на какое задание")
    first = T.pick("city/5.1", 0)
    check("первая фраза", first and first["ru"].startswith("Ты когда-нибудь был"), first)
    six = len(T.phrases_for("city/5.1"))
    check("номер по кругу", T.pick("city/5.1", six)["ru"] == first["ru"],
          T.pick("city/5.1", six)["ru"])
    check("мусор в номере — первая", T.pick("city/5.1", "abc")["ru"] == first["ru"])
    check("нет урока — None", T.pick("city/9.9", 0) is None)


def test_check():
    print("\n[3] Сверка перевода")
    ref = "Have you ever been to New York?"
    check("точь-в-точь — ok", T.check(ref, ref) == T.OK)
    check("строчные буквы — ok",
          T.check("have you ever been to new york", ref) == T.OK)
    check("пусто — no", T.check("", ref) == T.NO)
    check("по-русски — no", T.check("что это значит?", ref) == T.NO)
    check("другими словами — может быть",
          T.check("Have you ever visited New York?", ref) == T.MAYBE)
    check("не перевод, а ответ — может быть (решит модель)",
          T.check("Yes, I have been to New York.", ref) == T.MAYBE)
    check("пустой эталон — no", T.check("something", "") == T.NO)


def test_fields():
    print("\n[4] Обязательные поля фраз")
    bad = []
    for lesson_id, items in T.load().items():
        for row in items:
            if not row["ru"]:
                bad.append(lesson_id + ":ru")
            if not row["en"]:
                bad.append(lesson_id + ":en")
            if not row["why"]:
                bad.append(lesson_id + ":why")
            if row["rule"] not in gaps.RULES:
                bad.append(lesson_id + ":rule=" + str(row["rule"]))
    check("эталон, объяснение и правило из закрытого списка — у всех",
          not bad, bad)
    rules = {row["rule"] for items in T.load().values() for row in items}
    check("правила из списка Аналитика", rules <= set(gaps.RULES), rules)


def main():
    test_load()
    test_pick()
    test_check()
    test_fields()
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