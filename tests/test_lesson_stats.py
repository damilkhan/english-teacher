# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_STATS.PY — счётчики занятия (без экрана)
# =========================================================
#   python tests\test_lesson_stats.py
#
# ЗАЧЕМ. В конце занятия ученик видит итог: балл, ошибки, подсказки.
# Значит их надо СЧИТАТЬ по ходу. Решения ученика (23.10.2026):
#   * подсказка идёт в счёт ТОЛЬКО если ученик произнёс её вслух;
#   * ошибки — сумма разбора Аналитика за занятие;
#   * по ходу занятия ничего не показываем (только в итоге);
#   * обычные занятия НЕ наказывают за подсказки (штраф — только экзамен).
#
# Проверяем:
#   1) LessonSession: счётчики копятся, вне занятия не растут, есть в state();
#   2) app._note_hint / app._note_mistakes трогают сессию только когда она идёт;
#   3) обычный урок подсказками НЕ наказывается (балла тут нет вообще).
# Модель, микрофон и сеть не нужны.
# =========================================================

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import lesson                                                    # noqa: E402
from ui.app import EnglishTeacherApp                             # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def fake_app(session):
    """Приложение с одной сессией занятия (без Tk)."""
    ctrl = types.SimpleNamespace(current=lambda: session)
    return types.SimpleNamespace(lesson=ctrl)


def main():
    # ---------- 1. Сессия считает ----------
    print("[1] LessonSession: подсказки и ошибки")
    s = lesson.LessonSession("1.1", "desert/1", lesson_type=lesson.SPEAKING)
    check("новая сессия: подсказок 0", s.hints == 0, s.hints)
    check("новая сессия: ошибок 0", s.mistakes == 0, s.mistakes)

    s.use_hint()
    s.use_hint()
    check("две подсказки посчитаны", s.hints == 2, s.hints)

    s.add_mistakes(3)
    s.add_mistakes(1)
    check("ошибки суммируются", s.mistakes == 4, s.mistakes)
    check("отрицательное не отнимает", s.add_mistakes(-5) == 4, s.mistakes)
    check("мусор вместо числа не падает", s.add_mistakes("abc") == 4, s.mistakes)

    snap = s.state()
    check("в снимке есть hints", snap.get("hints") == 2, snap.get("hints"))
    check("в снимке есть mistakes", snap.get("mistakes") == 4, snap.get("mistakes"))

    # реплики и счётчики не путаются между собой
    s.register_reply()
    s.register_reply()
    check("реплики считаются отдельно", s.replies == 2, s.replies)
    check("подсказки от реплик не изменились", s.hints == 2, s.hints)

    # ---------- 2. После конца занятия счётчики стоят ----------
    print("\n[2] Занятие кончилось — счётчики не растут")
    s.finish()
    s.use_hint()
    s.add_mistakes(2)
    check("подсказка после конца не считается", s.hints == 2, s.hints)
    check("ошибки после конца не считаются", s.mistakes == 4, s.mistakes)

    print("\n[2b] Прерванное занятие тоже не считает")
    s2 = lesson.LessonSession("1.2", lesson_type=lesson.SPEAKING)
    s2.abort()
    s2.use_hint()
    s2.add_mistakes(1)
    check("прерванный урок не копит подсказки", s2.hints == 0, s2.hints)
    check("прерванный урок не копит ошибки", s2.mistakes == 0, s2.mistakes)

    # ---------- 3. Мостик из приложения ----------
    print("\n[3] app._note_hint / app._note_mistakes")
    live = lesson.LessonSession("1.1", lesson_type=lesson.SPEAKING)
    app = fake_app(live)
    EnglishTeacherApp._note_hint(app)
    EnglishTeacherApp._note_hint(app)
    EnglishTeacherApp._note_mistakes(app, 2)
    check("подсказки дошли до сессии", live.hints == 2, live.hints)
    check("ошибки дошли до сессии", live.mistakes == 2, live.mistakes)

    app = fake_app(None)
    EnglishTeacherApp._note_hint(app)      # не должно упасть
    EnglishTeacherApp._note_mistakes(app, 3)
    check("без занятия ничего не падает", True)

    closed = lesson.LessonSession("1.3", lesson_type=lesson.SPEAKING)
    closed.finish()
    app = fake_app(closed)
    EnglishTeacherApp._note_hint(app)
    EnglishTeacherApp._note_mistakes(app, 1)
    check("закрытое занятие не меняется",
          closed.hints == 0 and closed.mistakes == 0, (closed.hints, closed.mistakes))

    # ---------- 4. Обычный урок НЕ наказывает ----------
    print("\n[4] Обычный урок: подсказки балл не трогают")
    normal = lesson.LessonSession("1.4", lesson_type=lesson.SPEAKING)
    normal.use_hint()
    normal.use_hint()
    normal.use_hint()
    check("у обычной сессии нет поля score", not hasattr(normal, "score"),
          getattr(normal, "score", None))
    check("и нет проходного балла", not hasattr(normal, "passed"),
          getattr(normal, "passed", None))

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
