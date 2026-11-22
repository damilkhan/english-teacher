# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_SCENE_MATERIAL.PY — вопрос только ПРО материал урока (§91.7)
# =========================================================
#   python tests\test_scene_material.py
#
# ЖИВОЙ УРОК city/4.3 (22.11.2026, лог 12:2x): модель спросила
# «What color was the other phone?» — цвета второй трубки в сцене НЕТ,
# есть только «OK, I will take the black one.» Ученик ответил на этот
# вопрос, и урок стал бессмысленным (§91.2 лишь не дал его наказать).
#
# Решение ученика 22.11.2026: режем ТОЛЬКО вопрос вне материала.
# Вопрос про материал остаётся живым, даже если его нет в списке ask.
#
# Что проверяем:
#   1) материал урока собирается (сцена, ask, слова, тема);
#   2) настоящее реплики учителя 22.11 НЕ трогаются;
#   3) выдуманный вопрос про цвет — режется, виновник «color»;
#   4) код берёт вопрос из файла по ask_done;
#   5) реплика без вопроса не меняется;
#   6) выключатель config.LESSON_ASK_MATERIAL_ONLY работает;
#   7) в СЦЕНАХ и в фазе fix метод молчит (правило «в сценах правок нет»).
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

import config                 # noqa: E402
import scene_material as sm   # noqa: E402
from controllers import chat_controller as cc   # noqa: E402

FAILS = []


def check(name, ok, extra=""):
    if ok:
        print("  OK   %s" % name)
    else:
        print("  FAIL %s   %s" % (name, extra))
        FAILS.append(name)


def lesson_base(ask_done=0, phase="ask"):
    return {
        "title": "Two phones: which one?",
        "topic": "Comparing Things",
        "scene": [
            {"who": "Assistant", "en": "Can I help you?"},
            {"who": "Ann", "en": "Yes, I need a phone. Which one is better?"},
            {"who": "Assistant",
             "en": "This one is more expensive, but the camera is better."},
            {"who": "Ann", "en": "And the small one? It is cheaper."},
            {"who": "Assistant",
             "en": "It is cheaper, but the battery is worse."},
            {"who": "Ann", "en": "OK, I will take the black one."},
        ],
        "ask": [
            "Which phone did Ann take?",
            "What is worse about the small phone?",
            "Would you take the expensive phone or the cheap one?",
        ],
        "words": ["which one", "more expensive", "cheaper", "a better camera",
                  "I will take", "is there"],
        "ask_done": ask_done,
        "task_phase": phase,
    }


def controller(lesson, reply):
    obj = cc.ChatController.__new__(cc.ChatController)
    obj._lesson = lesson
    obj._last_question = ""
    return obj._keep_question_in_material(reply)


print("1) материал урока собран")
bag = sm.material_words(lesson_base())
for word in ("phone", "camera", "battery", "cheap", "black", "ann"):
    check("«%s» в материале" % word, word in bag, sorted(bag))
check("«color» НЕТ в материале", "color" not in bag, sorted(bag))

print("2) настоящие реплики учителя 22.11 не трогаем")
for text in (
        "Hello Damil, which phone did Ann take?",
        "Good job, Damil. What is worse about the small phone?",
        "That is true, Damil. Would you take the expensive phone or the cheap one?",
        "Which phone did Ann take?",
        "Can you say that again?",
        'What does "worse" mean?'):
    got = controller(lesson_base(), text)
    check("не тронуто: %s" % text[:44], got == text, got)

print("3) выдуманный вопрос про цвет")
bad, culprit = sm.outside_material(
    "That is a good choice, Damil. What color was the other phone?",
    lesson_base())
check("вне материала", bad, culprit)
check("виновник color", culprit == "color", culprit)
got = controller(lesson_base(),
                 "That is a good choice, Damil. What color was the other phone?")
check("похвала сохранена", got.startswith("That is a good choice, Damil."), got)
check("свой вопрос подставлен", "Which phone did Ann take?" in got, got)
check("выдумки больше нет", "color" not in got.lower(), got)

got = controller(lesson_base(), "What color is the second phone?")
check("похвалы не было — реплика стала вопросом урока",
      got == "Which phone did Ann take?", got)
print("4) вопрос из файла — по ask_done")
got = controller(lesson_base(ask_done=1),
                 "Nice. What colour is the second phone?")
check("второй вопрос файла", "What is worse about the small phone?" in got, got)
# ask_done за пределом = все вопросы позади. Раньше здесь ждали ПОСЛЕДНИЙ
# вопрос — но это и есть повтор, из-за которого ученик и пожаловался
# 22.11.2026. Правильно: новых вопросов нет, вопрос не задаём.
got = controller(lesson_base(ask_done=99), "Nice. What colour is it?")
check("ask_done за пределом — вопрос не задаём", "?" not in got, got)

print("5) реплика без вопроса")
for text in ("Good job, Damil.", "Well done! I will take the black one.",
             "Yes.", ""):
    check("не тронуто: %r" % text[:30], controller(lesson_base(), text) == text)

print("6) выключатель")
old = getattr(config, "LESSON_ASK_MATERIAL_ONLY", True)
config.LESSON_ASK_MATERIAL_ONLY = False
try:
    text = "That is a good choice, Damil. What color was the other phone?"
    check("выключено — реплика как есть", controller(lesson_base(), text) == text)
finally:
    config.LESSON_ASK_MATERIAL_ONLY = old

print("7) сцены и прочие фазы — метод молчит")
scene_like = lesson_base()
scene_like["ask"] = ["Where are you?"]
scene_like.pop("scene")
text = "What color was the other phone?"
check("без scene не трогаем", controller(scene_like, text) == text)
check("фаза fix не трогаем",
      controller(lesson_base(phase="fix"), text) == text)
check("фаза done не трогаем",
      controller(lesson_base(phase="done"), text) == text)
empty = {"task_phase": "ask"}
check("пустой урок не трогаем", controller(empty, text) == text)

print("8) §91.8: нормализация вопроса (повтор ловится)")
check("приветствие и имя не мешают",
      sm.norm_question("Hello Damil, which phone did Ann take?")
      == sm.norm_question("Which phone did Ann take?"),
      sm.norm_question("Hello Damil, which phone did Ann take?"))
check("регистр и знаки не важны",
      sm.norm_question("WHICH PHONE did Ann take")
      == sm.norm_question("which phone did ann take?"))
check("разные вопросы — разные",
      sm.norm_question("Which phone did Ann take?")
      != sm.norm_question("What is worse about the small phone?"))

print("9) §91.8: выбираем только НЕзаданные вопросы")
lesson = lesson_base()
check("сначала первый",
      sm.pick_unasked(lesson, [], "") == "Which phone did Ann take?")
check("первый уже задан — берём второй",
      sm.pick_unasked(lesson, ["Which phone did Ann take?"], "")
      == "What is worse about the small phone?",
      sm.pick_unasked(lesson, ["Which phone did Ann take?"], ""))
check("ask_done НЕ решает (он отстаёт)",
      sm.pick_unasked({"ask": lesson["ask"], "ask_done": 0},
                      lesson["ask"], "") == "", "взял заданный вопрос")
check("все заданы — пусто",
      sm.pick_unasked(lesson, lesson["ask"], "") == "")
check("вчерашний вопрос не берём (avoid)",
      sm.pick_unasked(lesson, [], "Which phone did Ann take?")
      == "What is worse about the small phone?",
      sm.pick_unasked(lesson, [], "Which phone did Ann take?"))

print("10) §91.8: живой урок 22.11.2026 — повтора НЕТ")
# Реплики ровно как в логе (строки 10219-10276). На четвёртой ход сломался:
# ask_done отставал, и код подставлял ТОТ ЖЕ вопрос. Ученик видел повтор.
live = {"scene": lesson_base()["scene"], "ask": lesson_base()["ask"],
        "words": lesson_base()["words"], "task_phase": "ask", "ask_done": 0}
ctl = cc.ChatController.__new__(cc.ChatController)
ctl._lesson = live
ctl._last_question = ""
ctl._scene_asked = []
ctl._scene_ask_key = ""


def turn(reply, ask_done):
    ctl._lesson["ask_done"] = ask_done
    out = ctl._final_question_guard(ctl._keep_question_in_material(reply))
    ctl._last_question = ctl._question_of(out)
    return out


said = []
for reply, done in (
        ("Hello Damil, which phone did Ann take?", 0),
        ("That is correct, Damil. What is worse about the small phone?", 1),
        ("That is correct, Damil. Would you take the expensive phone or"
         " the cheap one?", 2),
        ("Great choice, Damil. The expensive phone has a better camera."
         " Would you want to take it?", 2)):
    said.append(turn(reply, done))

repeats = 0
for i in range(1, len(said)):
    first = sm.norm_question(cc.ChatController._question_of(said[i - 1]))
    second = sm.norm_question(cc.ChatController._question_of(said[i]))
    if first and second and first == second:
        repeats += 1
check("ни одного повтора за весь урок", repeats == 0, repeats)
check("первая реплика не тронута", said[0] == ctl._scene_asked[0] + "?",
      said[0])

print("11) §91.8: модель САМА повторяет вопрос — отрезаем, похвалу оставляем")
ctl2 = cc.ChatController.__new__(cc.ChatController)
ctl2._lesson = dict(live)
ctl2._last_question = "Which phone did Ann take"
ctl2._scene_asked = []
ctl2._scene_ask_key = ""
got = ctl2._final_question_guard("Right. Which phone did Ann take?")
check("повтор отрезан", "?" not in got, got)
check("похвала осталась", got.startswith("Right."), got)

print("12) §91.8: прочие фазы не трогаем")
for phase in ("fix", "drill", "done", ""):
    ctl3 = cc.ChatController.__new__(cc.ChatController)
    ctl3._lesson = dict(live)
    ctl3._lesson["task_phase"] = phase
    ctl3._last_question = "Which phone did Ann take"
    ctl3._scene_asked = []
    ctl3._scene_ask_key = ""
    text = "Right. Which phone did Ann take?"
    check("фаза %r — как есть" % (phase or "пусто",),
          ctl3._final_question_guard(text) == text)

print("13) §91.8: новый урок — список заданных чистый")
ctl4 = cc.ChatController.__new__(cc.ChatController)
ctl4._lesson = {"scene": [{"en": "x"}], "ask": ["First one?", "Second one?"],
                "task_phase": "ask", "ask_done": 0}
ctl4._last_question = "Old lesson question"
ctl4._scene_asked = ["Old lesson question"]
ctl4._scene_ask_key = "Old lesson question?"
out = ctl4._final_question_guard("Fine. What color is it?")
check("вопрос нового урока всё равно подставлен или отрезан",
      "Old lesson question" not in out, out)
print("14) §91.8: тот же урок начали заново — вопросы снова доступны")
ctl5 = cc.ChatController.__new__(cc.ChatController)
ctl5._lesson = dict(live)
ctl5._lesson["ask_done"] = 3          # все три позади
ctl5._last_question = "Anything"
ctl5._scene_asked = list(lesson_base()["ask"])
ctl5._scene_ask_key = cc.ChatController._ask_signature(ctl5, ctl5._lesson)
# новый заход по тому же уроку: приложение сбросило счётчик в 0
ctl5._lesson["ask_done"] = 0
out = ctl5._final_question_guard("Nice. What color is it?")
check("первый вопрос урока снова можно задать", "?" in out, out)
check("список заданных начат заново", len(ctl5._scene_asked) <= 1,
      ctl5._scene_asked)
print("15) §91.9: урок не застревает — переход на фразы")
# Живой урок 22.11.2026, 21:26: ученик ответил на все три вопроса, но
# `tasks_done` отставал (зачёт ставит Аналитик после ответа учителя),
# переход на фразы не срабатывал, а бот уже не задавал вопросов — урок
# стоял. Считаем по РЕАЛЬНО заданным вопросам.
from ui import app as app_mod    # noqa: E402


class _Session:
    lesson_id = "city/4.3"
    tasks_done = 2


class _App:
    chat = None

    _material_of = app_mod.EnglishTeacherApp._material_of
    _material_ask_left = app_mod.EnglishTeacherApp._material_ask_left
    _scene_asked_count = app_mod.EnglishTeacherApp._scene_asked_count


app_stub = _App()
sess = _Session()

# без контроллера — прежнее поведение (1 вопрос ещё впереди)
app_stub.chat = None
check("без контроллера считаем по tasks_done",
      app_stub._material_ask_left(sess) == 1,
      app_stub._material_ask_left(sess))

# с контроллером, где все три вопроса прозвучали
app_stub.chat = ctl
check("все вопросы прозвучали — осталось 0",
      app_stub._material_ask_left(sess) == 0,
      app_stub._material_ask_left(sess))
check("счётчик заданных = 3", app_stub._scene_asked_count(sess) == 3,
      app_stub._scene_asked_count(sess))

# и обратный случай: задан только один — урок ещё не готов к фразам
one = cc.ChatController.__new__(cc.ChatController)
one._lesson = dict(lesson_base())
one._lesson["task_phase"] = "ask"
one._lesson["ask_done"] = 0
one._last_question = ""
one._scene_asked = ["Which phone did Ann take"]
one._scene_ask_key = ""
app_stub.chat = one
class _Session0(_Session):
    tasks_done = 0


sess0 = _Session0()
check("задан один, зачёта ещё нет — осталось 2",
      app_stub._material_ask_left(sess0) == 2,
      app_stub._material_ask_left(sess))
print("")
if FAILS:
    print("ПРОВАЛЕНО: %d" % len(FAILS))
    for name in FAILS:
        print("   - %s" % name)
    sys.exit(1)
print("ВСЁ ЗЕЛЁНОЕ")
