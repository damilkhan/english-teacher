# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_DRILL.PY — первое задание = дрилл по ПРОШЛОЙ ошибке (§55)
# =========================================================
#   python tests\test_lesson_drill.py
#
# Что проверяем:
#   1) lesson.start_drill: фаза «drill», материал и ожидаемый повтор;
#   2) зачёт по ТЕКСТУ (без модели): верный повтор засчитан, ошибка — нет;
#   3) после зачёта дрилл закрыт: фаза ask, материал стёрт;
#   4) экзамен и аудирование дрилл НЕ получают;
#   5) промпт урока знает про дрилл и не теряет ветку закрытия урока;
#   6) окно: метод есть, вызывается на старте урока, фаза учтена;
#   7) флаг config.LESSON_MISTAKE_DRILL выключает дрилл.
# =========================================================

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                     # noqa: E402
import gaps                       # noqa: E402
import lesson                     # noqa: E402
import lesson as lesson_mod       # noqa: E402
import prompt_builder             # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def new_session(**kwargs):
    """Обычный урок-говорение с заданиями (без Tk)."""
    kwargs.setdefault("lesson_type", "speaking")
    kwargs.setdefault("reply_target", 12)
    return lesson.LessonSession("city/1.1", block_number=1, **kwargs)


WRONG = "go to lay down"
RIGHT = "go to lie down"


def test_start_drill():
    print("\n[1] start_drill: фаза и материал")
    session = new_session()
    check("у урока есть задания", session.has_tasks, session.tasks_total)
    check("дрилл принят", session.start_drill(WRONG, RIGHT) is True)
    check("фаза = drill", session.task_phase == lesson_mod.TASK_DRILL,
          session.task_phase)
    check("ждём верный повтор", session.repeat_expected == [RIGHT],
          session.repeat_expected)
    check("запомнено, что ученик сказал", session.drill_wrong == WRONG,
          session.drill_wrong)
    payload = session.task_prompt()
    check("в промпте есть материал дрилла", payload.get("drill_wrong") == WRONG,
          payload)
    check("номер задания остаётся первым", payload.get("task_index") == 1, payload)
    check("пустая пара не принимается", new_session().start_drill("", "") is False)


def test_credit_by_text():
    print("\n[2] Зачёт по тексту: без модели")
    session = new_session()
    session.start_drill(WRONG, RIGHT)
    check("сказал правильно в предложении",
          session.says_fix("I always go to lie down after dinner") is True)
    check("повторил с ошибкой — не зачёт",
          session.says_fix("go to lay down") is False)
    check("пустая реплика — не зачёт", session.says_fix("") is False)
    check("во время дрилла фаза не меняется",
          session.task_phase == lesson_mod.TASK_DRILL, session.task_phase)


def test_credit_closes_drill():
    print("\n[3] Зачёт закрывает дрилл")
    session = new_session()
    session.start_drill(WRONG, RIGHT)
    state = session.credit_task(RIGHT)
    check("задание засчитано", state.get("tasks_done") == 1, state)
    check("фаза вернулась к обычной", session.task_phase == lesson_mod.TASK_ASK,
          session.task_phase)
    cleared = session.drill_wrong == "" and session.repeat_expected == []
    check("материал дрилла стёрт", cleared,
          (session.drill_wrong, session.repeat_expected))
    check("в промпте дрилла больше нет",
          "drill_wrong" not in session.task_prompt(), session.task_prompt())
    check("старый повтор не засчитывается второй раз",
          session.says_fix(RIGHT) is False)
    again = new_session()
    again.start_drill(WRONG, RIGHT)
    for _ in range(lesson_mod.MAX_TASK_ATTEMPTS):
        again.note_task_attempt()
    again.credit_task("", marked=True)
    check("после предела — засчитано с подсказкой",
          again.tasks_done == 1 and again.tasks_marked == 1,
          (again.tasks_done, again.tasks_marked))


def test_no_drill_where_no_tasks():
    print("\n[4] Экзамен и аудирование дрилл не получают")
    exam = lesson.LessonSession("city/1.4", block_number=1, lesson_type="check")
    check("у экзамена заданий нет", not exam.has_tasks, exam.tasks_total)
    check("экзамен дрилл не берёт", exam.start_drill(WRONG, RIGHT) is False)
    listen = lesson.LessonSession("city/1.1", block_number=1, lesson_type="listening")
    check("аудирование дрилл не берёт", listen.start_drill(WRONG, RIGHT) is False)


def test_prompt():
    print("\n[5] Промпт урока")
    session = new_session()
    session.start_drill(WRONG, RIGHT)
    block = prompt_builder._task_cycle_block(session.task_prompt())
    check("блок непустой", bool(block.strip()), block)
    check("сказано, что это дрилл", "REPEAT DRILL" in block, block[:200])
    check("материал в промпте", WRONG in block, block[:200])
    check("запрет давать другое задание", "Do NOT give any other task" in block)
    check("номер задания в промпте", "Task 1 of 3" in block, block[:120])
    closing = prompt_builder._task_cycle_block(
        {"tasks_total": 3, "task_index": 3, "task_phase": "ask", "lesson_closing": True})
    check("ветка закрытия урока цела", "the lesson ends now" in closing, closing)
    fix = prompt_builder._task_cycle_block(
        {"tasks_total": 3, "task_index": 1, "task_phase": "fix",
         "repeat_expected": "I went home"})
    check("ветка повтора после ошибки цела", "just wait for the repeat" in fix, fix)
    ask = prompt_builder._task_cycle_block(
        {"tasks_total": 3, "task_index": 1, "task_phase": "ask"})
    check("обычная фаза без правил непустая", bool(ask.strip()), ask)


def test_window():
    print("\n[6] Окно: метод, вызов, фаза")
    with open(os.path.join(ROOT, "ui", "app.py"), "r", encoding="utf-8") as fh:
        source = fh.read()
    check("метод _start_mistake_drill есть", "def _start_mistake_drill(" in source)
    start = source.find("def _begin_lesson(")
    body = source[start:] if start >= 0 else ""
    cut = re.search(r"\n    def ", body[1:])
    if cut:
        body = body[:cut.start() + 1]
    check("вызывается на старте урока", "_start_mistake_drill(session)" in body)
    check("фаза дрилла учтена в разборе",
          "lesson_mod.TASK_DRILL" in source)
    check("экзамен отсеян", "is_check_lesson(session.lesson_type)" in source)
    check("флаг в config есть", hasattr(config, "LESSON_MISTAKE_DRILL"),
          getattr(config, "LESSON_MISTAKE_DRILL", "нет"))


def test_flag_and_picker():
    print("\n[7] Флаг выключает дрилл, выбор пары не из воздуха")
    from ui.app import EnglishTeacherApp

    class FakeApp:
        current_user = {"id": 1}

    real_top = gaps.top_pair
    keep_flag = getattr(config, "LESSON_MISTAKE_DRILL", True)
    try:
        gaps.top_pair = lambda user_id=None, **kw: {
            "rule": "word_choice", "label": "не то слово", "wrong": WRONG,
            "correct": RIGHT, "count": 7}
        session = new_session()
        check("дрилл поставлен из пары",
              EnglishTeacherApp._start_mistake_drill(FakeApp(), session) is True)
        check("фаза drill", session.task_phase == lesson_mod.TASK_DRILL,
              session.task_phase)
        config.LESSON_MISTAKE_DRILL = False
        off = new_session()
        check("флаг выключает дрилл",
              EnglishTeacherApp._start_mistake_drill(FakeApp(), off) is False)
        check("урок остаётся обычным", off.task_phase == lesson_mod.TASK_ASK,
              off.task_phase)
        config.LESSON_MISTAKE_DRILL = True
        gaps.top_pair = lambda user_id=None, **kw: None
        empty = new_session()
        check("нет пробела — нет дрилла",
              EnglishTeacherApp._start_mistake_drill(FakeApp(), empty) is False)
        exam = lesson.LessonSession("city/1.4", block_number=1, lesson_type="check")
        check("экзамену дрилл не ставится",
              EnglishTeacherApp._start_mistake_drill(FakeApp(), exam) is False)
    finally:
        gaps.top_pair = real_top
        config.LESSON_MISTAKE_DRILL = keep_flag


def main():
    test_start_drill()
    test_credit_by_text()
    test_credit_closes_drill()
    test_no_drill_where_no_tasks()
    test_prompt()
    test_window()
    test_flag_and_picker()
    print("\n" + ("ВСЁ ПРОЙДЕНО" if not FAILED else "ПРОВАЛЕНО: %d" % len(FAILED)))
    for name in FAILED:
        print("  - " + name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
