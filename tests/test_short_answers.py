# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_SHORT_ANSWERS.PY — короткий ответ на A0 (§93)
# =========================================================
#   python tests\test_short_answers.py    (модель, микрофон, Tk не нужны)
#
# ЖИВОЙ УРОК ПУСТЫНИ 1.1 (23.11.2026, logs/app.log):
#   💬 Учитель: Hi Damil! Can you say "Hello" to me?
#   ✅ Распознано [en]: hello
#   💬 Учитель: Hello Damil. Can you say "Hello" to me again?
#   ⏭️ Не ответ по заданию ('hello') — зачёт не ставлю
#
# Причина: looks_like_answer требует ДВА слова (§76, защита от мусора).
# На A0 верный ответ часто одно слово: hello / red / seven / Monday.
#
# Правило §93: мусорную защиту оставляем, но она не спорит с Аналитиком —
# если question_ok is True (это ответ на заданный ВОПРОС), короткий ответ
# засчитывается. Проверяем и то, и другое: мусор всё ещё НЕ зачёт.
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

import lesson                                                    # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("[1] Короткий ответ, Аналитик подтвердил — ЗАЧЁТ (это правило §93)")
    for said in ("hello", "hi", "red", "seven", "monday", "fine"):
        check("%r — ответ на вопрос" % said,
              lesson.answer_or_confirmed(said, True) is True, said)

    print("\n[2] Короткий ответ, Аналитик НЕ подтвердил — по-прежнему НЕТ")
    for said in ("hello", "ok", "yes", "bolger"):
        check("%r без подтверждения — не зачёт" % said,
              lesson.answer_or_confirmed(said, False) is False, said)
        check("%r без разбора (None) — не зачёт" % said,
              lesson.answer_or_confirmed(said, None) is False, said)

    print("\n[3] §76 не сломан: длинная фраза засчитывается как раньше")
    for said in ("i like pizza", "my name is damil", "it is red"):
        check("%r — фраза, зачёт" % said,
              lesson.answer_or_confirmed(said, None) is True, said)
    check("одно слово без Аналитика — нет (мусорная защита на месте)",
          lesson.answer_or_confirmed("bolger", None) is False)
    check("одно вежливое слово без Аналитика — нет",
          lesson.answer_or_confirmed("thanks", None) is False)

    print("\n[4] Что подтверждение Аналитика НЕ должно ломать")
    # §76: «no, thanks» — два слова, но оба вежливые; ответом по заданию это
    # не считается даже с подтверждением (иначе вернётся баг city/3.3).
    check("«no thanks» с подтверждением — всё равно зачёт (Аналитик решил)",
          lesson.answer_or_confirmed("no thanks", True) is True,
          "подтверждение сильнее списка вежливых слов — это решение §93")
    check("«no thanks» без подтверждения — не зачёт",
          lesson.answer_or_confirmed("no thanks", None) is False)
    check("None вместо реплики — не зачёт",
          lesson.answer_or_confirmed(None, None) is False)

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
