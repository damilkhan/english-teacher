# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_TASKS.PY — задание сдаётся ВЕРНЫМ ответом (§36)
# =========================================================
#   python tests\test_lesson_tasks.py
#
# ЗАЧЕМ. До 26.10.2026 урок считал РЕПЛИКИ: любое сообщение ученика
# приближало конец урока, даже если он говорил не то. Решение ученика:
#
#   бот дал задание -> ученик ответил (с ошибкой) -> бот исправил и попросил
#   повторить -> ученик повторил -> ТОЛЬКО ТЕПЕРЬ задание засчитано, и бот
#   сразу даёт следующее (можно в той же реплике).
#
# Кто решает «сдано» (решение ученика 26.10.2026):
#   В) текстовая проверка повтора (difflib/вхождение) — мгновенно, до ответа
#      учителя, поэтому он успевает дать следующее задание в той же реплике;
#   Б) поле answer_state от Аналитика — для синонимов, второго вызова НЕТ;
#   3 неудачных повтора -> задание засчитывается С ПОМЕТКОЙ «с подсказкой»;
#   (А) метку от модели НЕ берём: модель плохо считает сама (§30).
#
# Проверяем:
#   1) lesson.py: кто считается заданиями, а кто репликами;
#   2) says_fix — быстрый путь (без модели);
#   3) сессию: зачёт, переход к следующему, защита от двойного зачёта;
#   4) промпт: блок заданий появляется и говорит нужную фазу;
#   5) Аналитик: answer_state разбирается и не даёт бесплатных зачётов;
#   6) ui/app.py: порядок «зачёт ДО ответа учителя», итог ждёт речи (§32).
# Окно, модель и микрофон не нужны.
# =========================================================

import os
import re
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

import config
import lesson                                                    # noqa: E402
import lesson_summary                                            # noqa: E402
import prompt_builder                                            # noqa: E402
import controllers.lesson_controller as lesson_controller        # noqa: E402
import roles.analyst as analyst_mod                              # noqa: E402
from ui.app import EnglishTeacherApp                             # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  OK   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


print("[1] Кто считается заданиями, а кто репликами")

check("в уроке говорения 3 задания",
      lesson.LessonSession("1.1", lesson_type="speaking").tasks_total == lesson.TASKS_PER_LESSON,
      lesson.TASKS_PER_LESSON)
check("урок текста тоже с заданиями", lesson.tasks_for("chat") == lesson.TASKS_PER_LESSON)
check("экзамен — по репликам (10 вопросов)", lesson.tasks_for("check") == 0)
check("аудирование — по репликам", lesson.tasks_for("listening") == 0)
check("экзамену задания не мешают: счётчик реплик прежний",
      lesson.LessonSession("1.4", lesson_type="check").progress_text() == "0/10")

print("[2] says_fix: повтор исправления без модели (вариант В)")

check("слово внутри фразы — повтор",
      lesson.says_fix("I went to the park", ["went"]) is True)
check("другая форма глагола — НЕ повтор",
      lesson.says_fix("I go to the park", ["went"]) is False)
check("регистр и точка не мешают",
      lesson.says_fix("i WENT to the park.", ["went"]) is True)
check("целая фраза с небольшим расхождением — повтор",
      lesson.says_fix("I am going to visit my grandmother",
                      ["I am going to visit my grandma"]) is True)
check("две правки — нужны ОБЕ",
      lesson.says_fix("I went to the park", ["went", "park"]) is True
      and lesson.says_fix("I went home", ["went", "park"]) is False)
check("пустой список правок — НЕ повтор (иначе зачёт бесплатный)",
      lesson.says_fix("anything at all", []) is False)
check("пустая реплика — НЕ повтор", lesson.says_fix("", ["went"]) is False)
check("мусор на входе не роняет",
      lesson.says_fix(None, None) is False and lesson.says_fix(123, ["123"]) is True)

print("[3] Сессия: зачёт задания и переход к следующему")

s = lesson.LessonSession("1.1", lesson_type="speaking", reply_target=12)
check("старт: 0 заданий, фаза ask",
      s.tasks_done == 0 and s.task_phase == lesson.TASK_ASK, s.task_phase)
check("полоса: «Задание 1/3»", s.progress_text() == "Задание 1/3", s.progress_text())
s.register_reply()
check("реплика сама по себе задание НЕ сдаёт", s.tasks_done == 0, s.tasks_done)
s.expect_repeat(["went"])
check("после ошибки ждём повтор", s.task_phase == lesson.TASK_FIX, s.task_phase)
check("что повторять — запомнили", s.repeat_expected == ["went"], s.repeat_expected)
check("повтор верный", s.says_fix("I went to school") is True)
st = s.credit_task("I went to school")
check("задание сдано", st["tasks_done"] == 1, st["tasks_done"])
check("фаза снова ask", st["task_phase"] == lesson.TASK_ASK, st["task_phase"])
check("полоса стала «Задание 2/3»", s.progress_text() == "Задание 2/3",
      s.progress_text())
check("список повтора очищен", s.repeat_expected == [], s.repeat_expected)
check("урок НЕ закончен", s.is_active is True and s.should_finish is False)

print("[4] Защита от двойного зачёта (В и Б приходят на один ответ)")

again = s.credit_task("I went to school")
check("та же реплика второй раз не считается", again["tasks_done"] == 1,
      again["tasks_done"])
check("already_credited это видит", s.already_credited("I went to school") is True)
check("другая реплика — не «уже засчитана»",
      s.already_credited("I came home") is False)

print("[5] Три неудачных повтора — зачёт с пометкой")

p = lesson.LessonSession("1.2", lesson_type="speaking")
p.register_reply()
p.expect_repeat(["was"])
for _ in range(lesson.MAX_TASK_ATTEMPTS):
    p.note_task_attempt()
check("попыток ровно столько, сколько разрешено",
      p.task_attempts == lesson.MAX_TASK_ATTEMPTS, p.task_attempts)
st = p.credit_task("I is home", marked=True)
check("задание засчитано", st["tasks_done"] == 1, st["tasks_done"])
check("пометка «с подсказкой» записана", st["tasks_marked"] == 1,
      st["tasks_marked"])
text = lesson_summary.summary_text(p)
check("в итоге видно пометку", "(с подсказкой: 1)" in text, text)

print("[6] Все задания сданы — урок закрыт")

q = lesson.LessonSession("1.3", lesson_type="speaking", reply_target=12)
for said in ("one", "two", "three"):
    q.register_reply()
    q.credit_task(said)
check("3 из 3 сдано", q.tasks_done == 3 and q.all_tasks_done is True)
check("урок завершён", q.finished is True and q.is_active is False)
check("закрытие по заданиям, а не по репликам (реплик 3 из 12)",
      q.replies == 3 and q.reply_target == 12)
check("фаза done", q.task_phase == lesson.TASK_DONE, q.task_phase)
check("полоса «Задание 3/3»", q.progress_text() == "Задание 3/3", q.progress_text())
check("после закрытия зачёты не идут", q.credit_task("four")["tasks_done"] == 3)

# §38 (26.10.2026): план реплик НЕ обрывает урок с заданиями — он идёт
# дальше, пока не сданы задания, и закрывается только на СТРАХОВОЧНОМ пределе.
brake = lesson.LessonSession("1.5", lesson_type="speaking", reply_target=2)
for _ in range(2):
    brake.register_reply()
check("на плане реплик урок НЕ закрылся", brake.is_active is True, brake.state())
check("предел = план + запас", brake.hard_reply_limit == 2 + config.LESSON_HARD_REPLY_EXTRA,
      brake.hard_reply_limit)
while brake.is_active:
    brake.register_reply()
check("лимит реплик остаётся страховкой (закрылся на пределе)",
      brake.finished is True and brake.replies == brake.hard_reply_limit,
      (brake.replies, brake.hard_reply_limit))
check("экзамен живёт по репликам: предел = план",
      lesson.LessonSession("x", lesson_type="check").hard_reply_limit
      == lesson.LessonSession("x", lesson_type="check").reply_target)

print("[7] Промпт: блок заданий и его фаза")

base = {"title": "Hello / Hi", "type": "speaking", "topic": "Greetings",
        "task": "Greet the student."}
plain = prompt_builder._lesson_block(base)
check("без заданий блока НЕТ", "TASKS:" not in plain, plain[-120:])
ask = dict(base)
ask.update({"tasks_total": 3, "tasks_done": 0, "task_index": 1,
            "task_phase": "ask", "repeat_expected": ""})
ask_text = prompt_builder._lesson_block(ask)
check("фаза ask: есть блок заданий", "TASKS: this lesson has 3" in ask_text)
check("фаза ask: номер задания назван", "task 1 of 3" in ask_text, ask_text)
fix = dict(ask)
fix.update({"task_phase": "fix", "repeat_expected": "went"})
fix_text = prompt_builder._lesson_block(fix)
check("фаза fix: назван НЕ СДАННЫМ", "is NOT done yet" in fix_text, fix_text)
check("фаза fix: сказано, что повторять", '"went"' in fix_text, fix_text)
done = dict(ask)
done.update({"tasks_done": 3, "task_index": 3, "task_phase": "done"})
done_text = prompt_builder._lesson_block(done)
check("фаза done: нового задания не давать",
      "do NOT start a new task" in done_text, done_text)
now = dict(ask)
now.update({"tasks_done": 1, "task_index": 2, "task_done_now": True})
now_text = prompt_builder._lesson_block(now)
check("сдано только что: следующее в ЭТОЙ же реплике",
      "in this same reply" in now_text and "task 2 of 3" in now_text, now_text)
check("экзамену блок заданий не достаётся",
      prompt_builder._lesson_block({"title": "Check", "exam": True})
      .count("TASKS:") == 0)

print("[8] Аналитик: answer_state и что просили повторить")

check("состояния ответа знает lesson.py",
      analyst_mod.ANSWER_STATES == lesson.ANSWER_STATES, analyst_mod.ANSWER_STATES)
parsed = analyst_mod.parse_analysis(
    '{"move_type": "A", "move_status": "A", "answer_state": "repeat_ok", '
    '"errors": [], "topics": [], "note": ""}')
check("repeat_ok разобран", parsed and parsed.get("answer_state") == "repeat_ok",
      parsed)
bad = analyst_mod.parse_analysis('{"move_type": "A", "answer_state": "чепуха"}')
check("неизвестное состояние -> unclear",
      bad and bad.get("answer_state") == "unclear", bad)
question = analyst_mod.parse_analysis('{"move_type": "Q", "answer_state": "correct"}')
check("вопрос задание НЕ сдаёт",
      question and question.get("answer_state") == "unclear", question)
fallback = analyst_mod.default_analysis()
check("сбой разбора -> unclear (не «correct»)",
      fallback.get("answer_state") == "unclear" and fallback.get("ok") is False)

prompt = analyst_mod.Analyst(None).build_prompt(
    "I went home", "Say it again, please.", "A2", expected="I went home")
check("в промпте есть правило answer_state", "answer_state" in prompt)
check("в промпте есть просьба «повтори»", "asked the student to repeat" in prompt,
      prompt[-400:])
none_expected = analyst_mod.Analyst(None).build_prompt("hello", "")
check("без просьбы повтора строки НЕТ",
      "asked the student to repeat" not in none_expected)

# ---------- ui/app.py: порядок и склейка ----------
APP = os.path.join(ROOT, "ui", "app.py")
with open(APP, "r", encoding="utf-8") as fh:
    SOURCE = fh.read()


def method_body(name):
    start = SOURCE.find("def %s(" % name)
    if start < 0:
        return ""
    rest = SOURCE[start:]
    match = re.search(r"\n    def ", rest[1:])
    return rest[:match.start() + 1] if match else rest


print("[9] ui/app.py: зачёт ДО ответа учителя (иначе следующее задание не дать)")

send = method_body("_send_to_teacher")
pos_count = send.find("_register_lesson_reply")
pos_credit = send.find("_credit_task_by_text")
pos_send = send.find("self.chat.send(")
check("зачёт по тексту есть в _send_to_teacher", pos_credit > 0, send)
check("зачёт ПОСЛЕ счёта реплики", 0 < pos_count < pos_credit,
      (pos_count, pos_credit))
check("зачёт ДО отправки учителю", 0 < pos_credit < pos_send,
      (pos_credit, pos_send))

analysis = method_body("_on_analysis")
check("разбор зовёт зачёт по варианту Б", "_task_from_analysis" in analysis)

response = method_body("_on_response")
check("итог при закрытии урока НЕ встаёт перед озвучкой (§32)",
      response.find("_reply_in_flight = True", response.find("_reply_in_flight = False")) > 0,
      response[:400])

print("[10] Поведение на пустышке: зачёт В, зачёт Б, полоса и промпт")


def make_app():
    app = types.SimpleNamespace()
    app.lesson = lesson_controller.LessonController(dispatch=lambda fn: fn())
    app.lesson.start("1.1", lesson_type="speaking", title="Hello / Hi")
    app.bar = []
    app.finished = []
    app.payloads = []
    app.lesson.on_finished = lambda s: app.finished.append(s)
    app.lesson_bar = types.SimpleNamespace(set_progress=lambda t: app.bar.append(t))
    app.chat = types.SimpleNamespace(
        set_lesson=lambda payload: app.payloads.append(dict(payload)))
    app._lesson_payload = {"title": "Hello / Hi", "type": "speaking",
                           "topic": "Greetings", "exam": False}
    app._last_student_text = ""
    app._speech_busy = False
    app._reply_in_flight = False
    for name in ("_sync_lesson_prompt", "_credit_task_by_text", "_credit_task",
                 "_close_lesson_after_credit", "_task_from_analysis"):
        setattr(app, name, types.MethodType(getattr(EnglishTeacherApp, name), app))
    return app


app = make_app()
session = app.lesson.current()
session.expect_repeat(["went"])
app._last_student_text = "I went to school"
check("В: повтор засчитан", app._credit_task_by_text("I went to school") is True)
check("В: задание сдано", session.tasks_done == 1, session.tasks_done)
check("полоса обновлена", app.bar == ["Задание 2/3"], app.bar)
payload = app.payloads[-1] if app.payloads else {}
check("промпт знает номер задания", payload.get("task_index") == 2, payload)
check("промпт знает, что задание только что сдано",
      payload.get("task_done_now") is True, payload)
check("урок не закрыт раньше времени", app.finished == [], app.finished)

app2 = make_app()
s2 = app2.lesson.current()
s2.register_reply()
check("Б: ошибка -> ждём повтор", app2._task_from_analysis(
    {"ok": True, "answer_state": "needs_fix", "errors": [
        {"type": "grammar", "wrong": "go", "correct": "went"}]}) is False)
check("Б: фаза fix", s2.task_phase == lesson.TASK_FIX, s2.task_phase)
check("Б: что повторять — из разбора", s2.repeat_expected == ["went"],
      s2.repeat_expected)
check("Б: промпт пересобран с фазой fix",
      (app2.payloads[-1] if app2.payloads else {}).get("task_phase") == "fix",
      app2.payloads[-1:] )

app2._last_student_text = "I went there yesterday"
check("Б: синоним/другая фраза засчитана по разбору",
      app2._task_from_analysis(
          {"ok": True, "answer_state": "repeat_ok", "errors": []}) is True)
check("Б: задание сдано", s2.tasks_done == 1, s2.tasks_done)

app3 = make_app()
s3 = app3.lesson.current()
app3._last_student_text = "hello"
app3._task_from_analysis({"ok": True, "answer_state": "correct", "errors": []})
check("Б: верный первый ответ сразу закрывает задание", s3.tasks_done == 1,
      s3.tasks_done)
check("после зачёта фаза ask", s3.task_phase == lesson.TASK_ASK)

app4 = make_app()
s4 = app4.lesson.current()
s4.expect_repeat(["was"])
for said in ("no", "nope", "still no"):
    app4._last_student_text = said
    app4._task_from_analysis({"ok": True, "answer_state": "unclear", "errors": []})
check("после 3 неудач задание всё равно сдано", s4.tasks_done == 1, s4.tasks_done)
check("и помечено «с подсказкой»", s4.tasks_marked == 1, s4.tasks_marked)

app5 = make_app()
s5 = app5.lesson.current()
s5.expect_repeat(["went"])
app5._last_student_text = "I went to school"
app5._credit_task_by_text("I went to school")
app5._task_from_analysis({"ok": True, "answer_state": "correct", "errors": []})
check("двойного зачёта нет (В сработал, Б молчит)", s5.tasks_done == 1,
      s5.tasks_done)

app6 = make_app()
s6 = app6.lesson.current()
for said in ("one", "two", "three"):
    app6._last_student_text = said
    app6._task_from_analysis({"ok": True, "answer_state": "correct", "errors": []})
check("все 3 задания сданы -> урок закрыт", s6.finished is True)
check("итог запрошен ровно один раз", len(app6.finished) == 1, app6.finished)

print()
if FAILED:
    print("ПРОВАЛЕНО: %d -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
