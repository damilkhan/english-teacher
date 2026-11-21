# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_QUESTION_CREDIT.PY — зачёт только за ответ ПО СМЫСЛУ вопроса
# =========================================================
#   python tests\test_question_credit.py
#
# ЖИВОЙ УРОК city/4.3 (18.11.2026, лог с 9368-й строки). На вопрос «Which
# phone did Ann take?» ученик сказал «the small phone has a bad battery» —
# и задание 1/9 было ЗАСЧИТАНО: разбор ошибок не нашёл (а в chat-уроке правка
# идёт молча), поэтому задание сдавалось за любую реплику по теме.
#
# Решение ученика 18.11.2026: «задание без проверки смысла — бессмысленное
# задание». Словами ответ с вопросом не сверить («Which phone did Ann take?»
# и «the small phone has a bad battery» не совпадают ни одним значимым
# словом), поэтому сверяет МОДЕЛЬ — коротким промптом (§88: 0,17-0,41 с).
#
# Что проверяем здесь:
#   1) блок промпта «NOT AN ANSWER» сильнее блока правки и несёт вопрос;
#   2) разбор ответа модели YES/NO (первое слово, а не подстрока);
#   3) проверка в контроллере: где берётся вопрос и когда она НЕ зовётся;
#   4) приложение: ответ не на вопрос → НЕ зачёт, попытка считается,
#      на пределе попыток задание засчитывается С ПОМЕТКОЙ.
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

import config                 # noqa: E402
import lesson                 # noqa: E402
import prompt_builder          # noqa: E402
import controllers.chat_controller as cc   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


Q1 = "Which phone did Ann take?"
Q2 = "What is worse about the small phone?"
OFF = "the small phone has a bad battery"


class FakeLLM:
    """Модель-заглушка: отдаёт заданный ответ и считает вызовы."""

    def __init__(self, raw="YES", ok=True, boom=False):
        self.raw = raw
        self.ok = ok
        self.boom = boom
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        if self.boom:
            raise RuntimeError("модель недоступна")
        return self.ok, self.raw


def make_controller(llm=None, ask=None, ask_done=0, last_question=""):
    """Контроллер без Tk: только то, что нужно проверке (§87-образец)."""
    obj = cc.ChatController.__new__(cc.ChatController)
    obj._opening = False
    obj.mode = "lesson"
    obj.llm = llm
    obj._last_question = last_question
    obj._lesson = {}
    if ask is not None:
        obj._lesson = {"ask": ask, "ask_done": ask_done, "task_phase": "ask"}
    obj._safe_analyze = lambda text, reply: {"ok": True, "errors": [],
                                             "move_type": "A",
                                             "answer_state": "correct"}
    return obj


print("1) Блок промпта: ответ не на вопрос")

block = prompt_builder._check_block(
    {"question": Q1, "question_ok": False, "errors": [], "said": OFF})
check("блок есть", "NOT AN ANSWER" in block, block)
check("вопрос внутри блока", Q1 in block, block)
check("правку НЕ просит (иначе два разных требования)",
      "CORRECTION FIRST" not in block, block)
check("пусто, если вопрос не проверен",
      prompt_builder._check_block({"errors": []}) == "",
      prompt_builder._check_block({"errors": []}))
check("правка при обычной ошибке на месте",
      "CORRECTION FIRST" in prompt_builder._check_block(
          {"errors": [{"wrong": "a phone", "correct": "the phone"}]}),
      prompt_builder._check_block(
          {"errors": [{"wrong": "a phone", "correct": "the phone"}]}))
both = prompt_builder._check_block(
    {"question": Q1, "question_ok": False, "said": OFF,
     "errors": [{"wrong": "a phone", "correct": "the phone"}]})
check("ошибка + не по вопросу → только NOT AN ANSWER",
      "NOT AN ANSWER" in both and "CORRECTION FIRST" not in both, both)
check("вопрос без ответа модели (question_ok True) — блока нет",
      prompt_builder._check_block({"question": Q1, "question_ok": True}) == "")

print("2) Ответ модели YES/NO — читаем ПЕРВОЕ слово")
for raw, want in (("YES", True), ("yes.", True), ("YES, it answers", True),
                  ("NO", False), ("no", False),
                  ("No, he took the black one.", False),
                  ("maybe", None), ("", None), ("OK", None)):
    check("%-30r -> %r" % (raw, want),
          prompt_builder.yes_no_verdict(raw) is want,
          prompt_builder.yes_no_verdict(raw))

print("3) Проверка в контроллере: «ответил ли на вопрос»")

llm = FakeLLM("NO")
ctrl = make_controller(llm, ask=[Q1, Q2], ask_done=0)
got = ctrl._question_check(OFF, ctrl._lesson, {"move_type": "A"})
check("NO от модели → question_ok=False", got.get("question_ok") is False, got)
check("вопрос взят из файла урока (ask[0])", got.get("question") == Q1, got)
check("модель спросили один раз", len(llm.calls) == 1, llm.calls)
text = llm.calls[0][-1]["content"] if llm.calls else ""
check("в промпт ушли вопрос и ответ", Q1 in text and OFF in text, text)

llm2 = FakeLLM("YES")
ctrl2 = make_controller(llm2, ask=[Q1, Q2], ask_done=1)
got2 = ctrl2._question_check(OFF, ctrl2._lesson, {"move_type": "A"})
check("YES → question_ok=True", got2.get("question_ok") is True, got2)
check("вопрос по счёту заданий (ask[1])", got2.get("question") == Q2, got2)

print("4) Когда проверка НЕ зовётся (иначе лишнее ожидание)")

llm3 = FakeLLM("NO")
c3 = make_controller(llm3, ask=[Q1])
check("мусор («bye») — не ответ по заданию",
      c3._question_check("bye", c3._lesson, {}) == {} and not llm3.calls,
      llm3.calls)

llm4 = FakeLLM("NO")
c4 = make_controller(llm4, ask=[Q1])
check("уточняющий вопрос ученика — не ответ (§81/§85)",
      c4._question_check("what does small mean", c4._lesson,
                         {"move_type": "Q"}) == {} and not llm4.calls,
      llm4.calls)

llm5 = FakeLLM("NO")
c5 = make_controller(llm5, ask=[Q1])
keep = config.LESSON_QUESTION_CHECK
config.LESSON_QUESTION_CHECK = False
try:
    off = c5._question_check(OFF, c5._lesson, {})
finally:
    config.LESSON_QUESTION_CHECK = keep
check("выключателем проверка снимается", off == {} and not llm5.calls,
      llm5.calls)
check("выключатель снова включён", config.LESSON_QUESTION_CHECK is True)

llm6 = FakeLLM(boom=True)
c6 = make_controller(llm6, ask=[Q1])
check("модель упала — урока не держим (пусто, без исключения)",
      c6._question_check(OFF, c6._lesson, {}) == {}, "исключение")

llm7 = FakeLLM("NO")
c7 = make_controller(llm7, ask=None, last_question="Would you take the cheap one?")
got7 = c7._question_check(OFF, c7._lesson, {})
check("файла ask нет — берём вопрос, который задал учитель",
      got7.get("question") == "Would you take the cheap one?", got7)

llm8 = FakeLLM("NO")
c8 = make_controller(llm8, ask=None, last_question="")
check("вопроса нет вовсе — проверки нет",
      c8._question_check(OFF, c8._lesson, {}) == {} and not llm8.calls,
      llm8.calls)

print("5) _precheck: разбор ошибок + проверка вопроса вместе")

llm9 = FakeLLM("NO")
c9 = make_controller(llm9, ask=[Q1], ask_done=0)
pre, used = c9._precheck(OFF)
check("разбор был", used is True, used)
check("в разборе есть вердикт по вопросу",
      pre and pre.get("question_ok") is False, pre)
check("вопрос записан рядом с разбором",
      pre and pre.get("question") == Q1, pre)

import ui.app as app_mod          # noqa: E402  (импорт после проверок: Tk не нужен)

App = app_mod.EnglishTeacherApp


def make_app(lesson_type="chat"):
    app = types.SimpleNamespace()
    app.lesson = cc_lesson_controller()
    app.lesson.start("city/4.3", lesson_type=lesson_type,
                     title="Two phones: which one?")
    app.bar = []
    app.finished = []
    app.payloads = []
    app.said = []
    app.lesson.on_finished = lambda s: app.finished.append(s)
    app.lesson_bar = types.SimpleNamespace(set_progress=lambda t: app.bar.append(t))
    app.chat = types.SimpleNamespace(
        set_lesson=lambda payload: app.payloads.append(dict(payload)))
    app.teacher_name = "Jane"
    app._lesson_payload = {"title": "Two phones: which one?", "type": lesson_type,
                           "topic": "Comparing Things", "exam": False,
                           "ask": [Q1, Q2], "ask_done": 0}
    app._last_student_text = ""
    app._speech_busy = False
    app._reply_in_flight = False
    app.add_message = lambda who, text, **kw: app.said.append(text)
    app._say_after_current = lambda text, **kw: app.said.append("(голос) " + text)
    for name in ("_sync_lesson_prompt", "_credit_task_by_text", "_credit_task",
                 "_close_lesson_after_credit", "_task_from_analysis",
                 "_off_topic_miss"):
        setattr(app, name, types.MethodType(getattr(App, name), app))
    return app


def cc_lesson_controller():
    return _lesson_ctrl()


from controllers import lesson_controller as _lc


def _lesson_ctrl():
    return _lc.LessonController(dispatch=lambda fn: fn())


print("6) Приложение: ответ не на вопрос НЕ засчитан")

app = make_app("chat")
session = app.lesson.current()
app._last_student_text = OFF
result_off = {"ok": True, "move_type": "A", "answer_state": "needs_fix",
              "errors": [{"type": "article", "wrong": "the small phone",
                          "correct": "a small phone"}],
              "question": Q1, "question_ok": False}
done = app._task_from_analysis(result_off)
check("зачёт не поставлен", done is False, done)
check("задание осталось 0", session.tasks_done == 0, session.tasks_done)
check("попытка посчитана", session.task_attempts == 1, session.task_attempts)
check("первый промах — без лишнего пузыря (учитель переспросил сам)",
      app.said == [], app.said)

app._task_from_analysis(result_off)
check("второй промах — вопрос показан строкой", any(Q1 in s for s in app.said),
      app.said)
check("и после двух промахов задания всё ещё нет", session.tasks_done == 0,
      session.tasks_done)

app._task_from_analysis(result_off)
check("предел попыток — задание сдано", session.tasks_done == 1,
      session.tasks_done)
check("и помечено «с подсказкой»", session.tasks_marked == 1, session.tasks_marked)

print("7) Ответ ПО вопросу засчитывается как раньше")

app2 = make_app("chat")
s2 = app2.lesson.current()
app2._last_student_text = "the black one"
ok = app2._task_from_analysis({"ok": True, "move_type": "A",
                               "answer_state": "correct", "errors": [],
                               "question": Q1, "question_ok": True})
check("зачёт поставлен", ok is True, ok)
check("задание 1", s2.tasks_done == 1, s2.tasks_done)
check("без пометки", s2.tasks_marked == 0, s2.tasks_marked)
check("лишних строк в чат нет", app2.said == [], app2.said)

print("8) Разбор без проверки вопроса (старый путь) не изменился")

app3 = make_app("chat")
s3 = app3.lesson.current()
app3._last_student_text = "the small phone has a bad battery"
ok3 = app3._task_from_analysis({"ok": True, "move_type": "A",
                                "answer_state": "correct", "errors": []})
check("без поля question_ok зачёт идёт по-прежнему", ok3 is True, ok3)
check("задание 1", s3.tasks_done == 1, s3.tasks_done)

print("9) Подсказка распознаванию: имена из материала урока (§89.1)")

MATERIAL = {
    "scene": [{"who": "Assistant", "en": "Can I help you?"},
              {"who": "Ann", "en": "Yes, I need a phone."}],
    "ask": [Q1, Q2],
}


def make_stt_app(material, scene_lesson=False):
    app = types.SimpleNamespace()
    session = types.SimpleNamespace(
        is_active=True, is_scene=scene_lesson, lesson_id="city/4.3",
        repeat_expected=[], drill_correct="", topic="Comparing Things")
    app.lesson = types.SimpleNamespace(current=lambda: session)
    app._material_of = lambda lesson_id: material
    app._vocab_stt_card = lambda: None
    app._scene_stt_words = lambda: []
    app._picture = None
    for name in ("_lesson_stt_words", "_material_stt_names",
                 "_my_stt_words", "_picture_stt_words"):
        setattr(app, name, types.MethodType(getattr(App, name), app))
    return app


stt = make_stt_app(MATERIAL)
words = stt._lesson_stt_words()
check("имя «Ann» попало в подсказку", "Ann" in words, words)
check("действующее лицо сцены тоже", "Assistant" in words, words)
check("имя стоит в начале (предел 24 слова его не съест)",
      words[:2] in (["Assistant", "Ann"], ["Ann", "Assistant"]), words)
check("слова-вопросы не стали именами («Which», «What»)",
      "Which" not in words and "What" not in words, words)
check("тема урока по-прежнему в подсказке", "Comparing" in words, words)

empty = make_stt_app(None)
check("материала нет — подсказки прежние, без имён",
      isinstance(empty._lesson_stt_words(), list)
      and "Ann" not in empty._lesson_stt_words(),
      empty._lesson_stt_words())

scene_app = make_stt_app(MATERIAL, scene_lesson=True)
check("урок-сцена идёт своим списком (не дублируем)",
      scene_app._lesson_stt_words() == [], scene_app._lesson_stt_words())

print()
if FAILED:
    print("ПРОВАЛЕНО: %d -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
