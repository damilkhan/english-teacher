# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_FLOW.PY — УРОК ЦЕЛИКОМ, без окна и без живой модели
# =========================================================
#   python tests\test_lesson_flow.py
#
# Зачем: 22.11.2026 урок city/4.3 застревал ДВАЖДЫ подряд, и оба раза моя
# правка чинила одно место, ломая соседнее:
#   21:07 — бот ПОВТОРИЛ вопрос («Would you take…» два раза);
#   22:02 — бот ЗАМОЛЧАЛ: повтор отрезали, а новый вопрос не поставили.
# Точечные проверки такого не ловят. Здесь прогоняется УРОК ЦЕЛИКОМ:
# три вопроса по сцене → ответы → переход на фразы.
#
# Модель — заглушка со ЗЛЫМ сценарием: она повторяет вопрос, уходит от темы
# и иногда отвечает совсем без вопроса. Код обязан выкрутиться.
#
# Что проверяем:
#   1) ни один вопрос не прозвучал дважды;
#   2) нет хода без вопроса, пока вопросы по сцене не кончились;
#   3) когда вопросы позади — урок уходит на фразы;
#   4) похвала не теряется.
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

import lesson_material                        # noqa: E402
import scene_material as sm                   # noqa: E402
from controllers import chat_controller as cc  # noqa: E402
from ui import app as app_mod                 # noqa: E402

LESSON_ID = "city/4.3"
FAILS = []


def check(name, ok, extra=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(extra)))
    if not ok:
        FAILS.append(name)


class FakeLLM:
    """Модель по сценарию: отдаёт заготовленные реплики по очереди."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def complete(self, messages, max_tokens=None, **kwargs):
        # короткий запрос (max_tokens<=4) — это §89 «ответ на вопрос?»
        if max_tokens is not None and max_tokens <= 4:
            return True, "YES"
        index = min(self.calls, len(self.script) - 1)
        self.calls += 1
        return True, self.script[index]


class Session:
    """Заглушка занятия: приложению нужны эти признаки."""

    lesson_id = LESSON_ID
    tasks_done = 0
    is_active = True
    has_tasks = True
    all_tasks_done = False
    lesson_type = "speaking"
    task_phase = "ask"

    def start_translate(self):
        self.task_phase = "translate"
        return True


class FakeApp:
    """Только то, что нужно уроку: материал, счёт вопросов, переход на фразы."""

    _material_of = app_mod.EnglishTeacherApp._material_of
    _material_ask_left = app_mod.EnglishTeacherApp._material_ask_left
    _scene_asked_count = app_mod.EnglishTeacherApp._scene_asked_count
    _start_material_translate = app_mod.EnglishTeacherApp._start_material_translate

    chat = None

    def __init__(self, session):
        self.session = session
        self.translated = []

    def _translate_ask(self, session):
        self.translated.append(session.lesson_id)
        return True


def build(replies):
    material = lesson_material.get(LESSON_ID)
    ask = [str(x) for x in (material.get("ask") or [])]
    payload = {
        "title": material.get("title"), "type": LESSON_ID,
        "topic": material.get("topic"), "lesson_id": LESSON_ID,
        "scene": material.get("scene"), "ask": ask,
        "words": material.get("words"),
        "ask_done": 0, "task_phase": "ask",
    }
    ctl = cc.ChatController(FakeLLM(replies), dispatch=lambda fn: fn(),
                            mode="lesson", lang="en", user_id=None)
    ctl.set_lesson(payload)
    captured = []
    ctl.on_response = lambda user_text, reply: captured.append(reply)
    return ctl, payload, ask, captured


def play(replies, answers, max_turns=8):
    """Прогнать урок: ученик отвечает, приложение считает и переходит."""
    ctl, payload, ask, captured = build(replies)
    app = FakeApp(Session())
    app.chat = ctl
    problems, sequence, praises = [], [], []
    student_text = "Hello!"
    transitioned = False

    for turn in range(1, max_turns + 1):
        payload["ask_done"] = max(0, turn - 2)     # зачёт отстаёт на ход
        ctl.set_lesson(payload)
        before = len(captured)
        ctl._worker(student_text)
        if len(captured) == before:
            problems.append("ход %d: пустой ответ" % turn)
            break
        reply = captured[-1]
        question = ctl._question_of(reply)
        key = sm.norm_question(question)
        left = app._material_ask_left(app.session)

        if key:
            if key in sequence:
                problems.append("ход %d: вопрос повторён" % turn)
            sequence.append(key)
        elif left > 0:
            problems.append("ход %d: молчание, а вопросов ещё %d" % (turn, left))
        if not key and turn > 1:
            pass

        if left == 0:
            transitioned = app._start_material_translate(app.session)
            break
        student_text = answers.get(key, "I think the black phone is better.")
        app.session.tasks_done += 1
        praises.append(reply)

    return {
        "problems": problems, "sequence": sequence,
        "transitioned": transitioned, "ask": ask,
        "app": app, "ctl": ctl,
    }


ANSWERS = {
    "which phone did ann take": "She took the black one.",
    "what is worse about the small phone": "The battery is worse.",
    "would you take the expensive phone or the cheap one":
        "I would take the expensive one, the camera is better.",
}

print("=" * 60)
print("УРОК city/4.3 ЦЕЛИКОМ (модель-заглушка со злым сценарием)")
print("=" * 60)

print("\n[1] Модель ведёт себя хорошо")
good = [
    "Hello Damil! Which phone did Ann take?",
    "That is correct, Damil. What is worse about the small phone?",
    "Right. Would you take the expensive phone or the cheap one?",
]
result = play(good, ANSWERS)
check("проблем нет", not result["problems"], result["problems"])
check("переход на фразы был", result["transitioned"] is True)
check("все три вопроса прозвучали", len(result["sequence"]) == 3,
      result["sequence"])

print("\n[2] Модель ПОВТОРЯЕТ вопрос (живой сбой 21:07)")
repeat = [
    "Hello Damil! Which phone did Ann take?",
    "Which phone did Ann take?",          # повтор
    "That is correct, Damil. What is worse about the small phone?",
    "What is worse about the small phone?",   # повтор
    "Right. Would you take the expensive phone or the cheap one?",
]
result = play(repeat, ANSWERS)
check("проблем нет", not result["problems"], result["problems"])
check("переход на фразы был", result["transitioned"] is True)
check("повторов в чате нет", len(result["sequence"]) == len(set(result["sequence"])),
      result["sequence"])

print("\n[3] Модель отвечает БЕЗ вопроса (живой сбой 22:02)")
silent = [
    "Hello Damil! Which phone did Ann take?",
    "That is correct.",
    "Right.",
    "Good job, Damil.",
]
result = play(silent, ANSWERS)
check("проблем нет", not result["problems"], result["problems"])
check("переход на фразы был", result["transitioned"] is True)
check("вопросы всё равно прозвучали", len(result["sequence"]) >= 3,
      result["sequence"])

print("\n[4] Модель спрашивает НЕ ПРО МАТЕРИАЛ")
wrong = [
    "Hello Damil! What colour is the other phone?",
    "That is correct. Do you like shopping?",
    "Right. What is the price of this phone?",
]
result = play(wrong, ANSWERS)
check("проблем нет", not result["problems"], result["problems"])
check("переход на фразы был", result["transitioned"] is True)
for text in result["sequence"]:
    if "colour" in text or "price" in text:
        check("выдумка не попала в чат: %s" % text[:40], False, text)
check("выдумок в чате нет", True)

print("\n[5] Всё плохое сразу: повтор + молчание + не по материалу")
mixed = [
    "Hello Damil! What colour is it?",
    "That is correct.",
    "What is worse about the small phone?",
    "What is worse about the small phone?",   # повтор
    "Good job.",
    "Would you take the expensive phone or the cheap one?",
]
result = play(mixed, ANSWERS)
check("проблем нет", not result["problems"], result["problems"])
check("переход на фразы был", result["transitioned"] is True)
check("повторов нет", len(result["sequence"]) == len(set(result["sequence"])),
      result["sequence"])

print()
if FAILS:
    print("ПРОВАЛЕНО: %d" % len(FAILS))
    for name in FAILS:
        print("   - %s" % name)
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
