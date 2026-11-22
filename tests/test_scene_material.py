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
got = controller(lesson_base(ask_done=99), "Nice. What colour is it?")
check("ask_done за пределом — последний вопрос",
      "Would you take the expensive phone or the cheap one?" in got, got)

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

print("")
if FAILS:
    print("ПРОВАЛЕНО: %d" % len(FAILS))
    for name in FAILS:
        print("   - %s" % name)
    sys.exit(1)
print("ВСЁ ЗЕЛЁНОЕ")
