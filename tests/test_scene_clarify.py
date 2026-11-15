# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_SCENE_CLARIFY.PY — уточняющий вопрос не двигает сцену (§81)
# =========================================================
#   python tests/test_scene_clarify.py
#
# Живой урок 15.11.2026: ученик спросил «what does it mean?» — приложение
# приняло это за ОТВЕТ, шаг засчитался, вопрос официанта остался без ответа.
# Здесь проверяется:
#   1) распознавание уточнения (13 случаев, в т.ч. «how much is coffee?» — НЕ
#      уточнение, это настоящий ответ про цену);
#   2) уточнение не считается ответом и не двигает шаг (счёт реплик стоит);
#   3) после третьего уточнения не застреваем — реплика идёт обычным путём.
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _utf8():
    for _stream in (sys.stdout, sys.stderr):
        try:
            if _stream.encoding and _stream.encoding.lower() != "utf-8":
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_utf8()

import scene_reactions as R                             # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    mark = "\u2705" if ok else "\u274c"
    print("  " + mark + " " + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


CASES = [
    ("drink", "what does it mean?", True),
    ("drink", "What is 'mild'?", True),
    ("drink", "how do you say this in russian?", True),
    ("drink", "I don't understand?", True),
    ("drink", "what?", True),
    ("drink", "why?", True),
    ("menu", "how much is the coffee?", False),
    ("people", "are we two persons?", False),
    ("drink", "one coffee please", False),
    ("table", "where is the toilet?", False),
    ("drink", "can i pay by card?", False),
    ("drink", "sorry, what?", False),
    ("drink", "", False),
    ("drink", "just water thanks", False),
    ("drink", "no, thanks", False),
]


def test_recognition():
    print("\n[1] Что считать уточнением")
    bad = []
    for slot, text, want in CASES:
        got = R.is_clarify(slot, text)
        if got != want:
            bad.append("%s: %r -> %s (ждали %s)" % (slot, text, got, want))
    check("%d случаев распознаны верно" % len(CASES), not bad, bad)
    check("без вопроса — не уточнение", R.is_clarify("drink", "what") is False)


class FakeSession(object):
    """Сцена в середине: шаг 2, вопрос 1, счётчик реплик."""

    def __init__(self):
        self.scene_id = "a2.restaurant"
        self.scene_step = 2
        self.scene_q = 1
        self.replies = 0
        self.tasks_done = 1


class FakeApp(object):
    """Только те методы App, что нужны уточнению (без Tk)."""

    def __init__(self):
        self._scene_asked_again = {}
        self.said = []
        self.asked = []

    _is_scene_clarify = None      # подставим ниже
    _scene_clarify = None

    def _scene_say(self, session, line, finish=False, ask=True):
        self.said.append(line)
        if ask:
            self.asked.append((session.scene_step, session.scene_q))


def _bind():
    """Взять настоящие методы из App (модуль импортируется без Tk-окна)."""
    from ui.app import EnglishTeacherApp as App
    FakeApp._is_scene_clarify = App._is_scene_clarify
    FakeApp._scene_clarify = App._scene_clarify


def test_no_advance():
    print("\n[2] Уточнение не двигает сцену")
    _bind()
    app, session = FakeApp(), FakeSession()
    taken = app._scene_clarify(session, "what does it mean?")
    check("реплику забрала сцена", taken is True, taken)
    check("шаг не сдвинулся", (session.scene_step, session.scene_q) == (2, 1),
          (session.scene_step, session.scene_q))
    check("в счёт реплик НЕ попало", session.replies == 0, session.replies)
    check("шаг не засчитан", session.tasks_done == 1, session.tasks_done)
    check("ученику сказали и ПОВТОРИЛИ вопрос",
          len(app.said) == 1 and app.asked == [(2, 1)], (app.said, app.asked))


def test_second_then_normal():
    print("\n[3] Второе уточнение и выход")
    _bind()
    app, session = FakeApp(), FakeSession()
    check("первое — уточнение", app._scene_clarify(session, "what?") is True)
    check("второе — тоже уточнение", app._scene_clarify(session, "what?") is True)
    check("третье — уже НЕ уточнение (обычный путь)",
          app._scene_clarify(session, "what?") is False)
    check("реплик не прибавилось", session.replies == 0, session.replies)
    check("вопрос повторили дважды", len(app.asked) == 2, app.asked)
    check("и второй раз спросили иначе",
          app.said[0] != app.said[1], app.said)


def main():
    test_recognition()
    test_no_advance()
    test_second_then_normal()
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
