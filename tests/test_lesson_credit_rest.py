# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_CREDIT_REST.PY — «Заданий: 2 из 3» больше нет
# =========================================================
#   python tests\test_lesson_credit_rest.py
#
# ЖИВОЙ БАГ (26.10.2026, скриншот ученика). Урок закрылся по страховочному
# пределу реплик, когда сдано было 2 задания из 3. В итоге:
#   📋 Заданий: 2 из 3
#   🎉 Урок 1.1 пройден!     ← противоречие: недоделан, а засчитан
# Причина: should_finish закрывает урок и по пределу реплик, а
# _on_lesson_finished засчитывал урок БЕЗУСЛОВНО (для экзамена проверка была,
# для заданий — нет).
#
# Решение ученика (вариант Б, 26.10.2026): урок закрылся — недоделанные
# задания засчитываем С ПОМЕТКОЙ «с подсказкой». Тогда в итоге честные
# «3 из 3 (с подсказкой: 1)», цифры сходятся и прогресс не теряется.
#
# Вторая дырка, закрытая тут же: ответ не по заданию (answer_state=unclear —
# болтовня, «hello», разбор не удался) в фазе «первый ответ» вообще ничего не
# делал: ни зачёта, ни просьбы повторить, ни счёта попыток. Задание висело до
# предела реплик.
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

import lesson                 # noqa: E402
import lesson_summary         # noqa: E402

SOURCE = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def method_body(name):
    start = SOURCE.find("    def %s(" % name)
    if start < 0:
        return ""
    rest = SOURCE[start:]
    end = rest.find("\n    def ", 1)
    return rest if end < 0 else rest[:end]


def session_with(done, lesson_type="speaking"):
    s = lesson.LessonSession("1.1", lesson_type=lesson_type)
    s.tasks_done = done
    return s


print("1) Сценарий со скриншота: 2 из 3 → добрали одно с пометкой")
s = session_with(2)
s.replies = s.hard_reply_limit
added = s.credit_rest(marked=True)
check("добрано ровно 1", added == 1, added)
check("сдано 3", s.tasks_done == 3, s.tasks_done)
check("с пометкой 1", s.tasks_marked == 1, s.tasks_marked)
check("урок закрыт", s.finished is True, s.finished)
check("фаза DONE", s.task_phase == lesson.TASK_DONE, s.task_phase)
check("все задания сданы", s.all_tasks_done is True)

print("2) Итог и похвала больше не противоречат друг другу")
text = lesson_summary.summary_text(s)
praise = lesson_summary.praise_text(s)
check("итог: «Заданий: 3 из 3»", "3 из 3" in text, text)
check("итог: «с подсказкой: 1»", "с подсказкой: 1" in text, text)
check("нет «2 из 3»", "2 из 3" not in text, text)
check("похвала про 3 задачи", "3 tasks" in praise, praise)

print("3) Всё сдано — добирать нечего")
s = session_with(0)
for i in range(3):
    s.credit_task("phrase %d" % i)
check("добрано 0", s.credit_rest(marked=True) == 0)
check("пометок нет", s.tasks_marked == 0, s.tasks_marked)

print("4) Ничего не сдано — добираем все три")
s = session_with(0)
check("добрано 3", s.credit_rest(marked=True) == 3)
check("пометок 3", s.tasks_marked == 3, s.tasks_marked)
check("сдано 3", s.tasks_done == 3, s.tasks_done)

print("5) Экзамен и аудирование — заданий нет, добирать нечего")
for kind in ("check", "listening"):
    s = session_with(0, kind)
    check("%s: добрано 0" % kind, s.credit_rest(marked=True) == 0, kind)

print("6) Закрытый урок повторно ничего не добирает")
s = session_with(1)
s.finish()
check("добрано 0", s.credit_rest(marked=True) == 0)
check("сдано осталось 1", s.tasks_done == 1, s.tasks_done)

print("7) Добор идёт БЕЗ пометки, если попросили marked=False")
s = session_with(2)
s.credit_rest(marked=False)
check("сдано 3", s.tasks_done == 3, s.tasks_done)
check("пометок 0", s.tasks_marked == 0, s.tasks_marked)

print("8) Связки в коде на месте")
check("lesson.credit_rest есть", hasattr(lesson.LessonSession, "credit_rest"))
body = method_body("_on_response")
check("_on_response добирает остаток", "_credit_rest_tasks(session)" in body, body[:200])
check("добор ДО закрытия урока",
      body.find("_credit_rest_tasks(session)") < body.find("self.lesson.finish()")
      or body.find("_credit_rest_tasks(session)") < body.find("credit_finished()"),
      (body.find("_credit_rest_tasks(session)"),
       body.find("self.lesson.finish()")))
check("итог показан, даже если добор закрыл сессию",
      "credit_finished()" in body, body[:200])

print("9) Ответ НЕ по заданию считается попыткой (unclear)")
task_body = method_body("_task_from_analysis")
check("unclear доходит до счёта попыток",
      "note_task_attempt()" in task_body, task_body[-400:])
check("после лимита попыток — зачёт с пометкой",
      "marked=True" in task_body, task_body[-400:])
tail = task_body.find("# Ответ НЕ ПО ЗАДАНИЮ")
check("ветка «не по заданию» идёт ПОСЛЕ просьбы повторить",
      tail > 0 and task_body.find("expect_repeat(corrections)") < tail,
      (task_body.find("expect_repeat(corrections)"), tail))

print("10) unclear три раза подряд → задание сдано с пометкой")
s = session_with(0)
s.replies = 3
for i in range(lesson.MAX_TASK_ATTEMPTS):
    s.note_task_attempt()
check("попыток набралось", s.task_attempts == lesson.MAX_TASK_ATTEMPTS, s.task_attempts)
s.credit_task("hello", marked=True)
check("сдано 1 (с пометкой)", s.tasks_done == 1 and s.tasks_marked == 1,
      (s.tasks_done, s.tasks_marked))

print()
if FAILED:
    print("❌ ПРОВАЛЕНО: %d" % len(FAILED))
    for name in FAILED:
        print("   - " + name)
    sys.exit(1)
print("✅ ВСЁ ПРОЙДЕНО")
