# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_MOUTH_MOVING.PY — рот двигается, пока идёт озвучка
# =========================================================
#   python tests\test_mouth_moving.py
#
# ЖИВОЙ БАГ (26.10.2026, §41). После третьего задания лицо робота ставится в
# happy (static_mouth = застывшая улыбка, talk=False), и похвала + задание к
# фото читались ВСЛУХ, а рот стоял. Причина: _mouth_layer() в
# character_face.py первым делом отдаёт static_mouth, громкость не смотрит.
# idle/smile/listening — та же беда (talk=False).
#
# Правило после правки: пока идёт озвучка (_speech_busy), лицо обязано быть
# «говорящим» (speaking / speak_happy / speak_sad / …). Когда речь кончилась,
# маска, которую поставили МЫ, снимается — возвращается покой.
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

import character_face as cf        # noqa: E402
from ui.app import EnglishTeacherApp as App   # noqa: E402

SOURCE = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeChar:
    def __init__(self, state="idle"):
        self.state = state
        self.available = True


class FakeApp:
    """Только то, что нужно _keep_mouth_moving (без окна и tkinter)."""

    _TALKING_FACE = App._TALKING_FACE
    _SPEAKING_STATES = App._SPEAKING_STATES
    _keep_mouth_moving = App._keep_mouth_moving

    def __init__(self, state="idle"):
        self._speech_busy = False
        self._face_auto = None
        self.char = FakeChar(state)
        self.calls = []

    def _character_state(self, state=None):
        self.calls.append(state)
        if state is None:
            return getattr(self.char, "state", None)
        self.char.state = state
        return state


def run(state, busy):
    app = FakeApp(state)
    app._speech_busy = busy
    app._keep_mouth_moving(app.char)
    return app


print("1) Пока идёт речь, лицо становится ГОВОРЯЩИМ")
for src, want in (("happy", "speak_happy"), ("smile", "speak_happy"),
                  ("idle", "speaking"), ("listening", "speaking"),
                  ("thinking", "speak_thinking"), ("surprised", "speak_surprised"),
                  ("sad", "speak_sad"), ("story_end", "speaking")):
    app = run(src, True)
    check("%s + речь → %s" % (src, want), app.char.state == want, app.char.state)

print("2) Уже говорим — лицо не дёргаем")
for src in ("speaking", "speak_happy", "speak_sad", "speak_story"):
    app = run(src, True)
    check("%s остаётся" % src, app.char.state == src and app.calls == [], app.calls)

print("3) Речь кончилась — наша маска снимается, возвращается покой")
app = FakeApp("happy")
app._speech_busy = True
app._keep_mouth_moving(app.char)
check("во время речи маска speak_happy", app.char.state == "speak_happy", app.char.state)
app._speech_busy = False
app._keep_mouth_moving(app.char)
check("после речи — idle", app.char.state == "idle", app.char.state)
check("запись о маске стёрта", app._face_auto is None, app._face_auto)

print("4) Чужое состояние после речи НЕ перебиваем")
app = FakeApp("happy")
app._speech_busy = True
app._keep_mouth_moving(app.char)
app._speech_busy = False
app.char.state = "sad"          # кто-то поставил эмоцию сам
app._keep_mouth_moving(app.char)
check("sad осталась", app.char.state == "sad", app.char.state)
check("маска забыта", app._face_auto is None, app._face_auto)

print("5) Тишина без речи — лицо не трогаем")
app = run("happy", False)
check("happy не меняется", app.char.state == "happy" and app.calls == [], app.calls)

print("6) Таблица состояний: без речи рот действительно СТОИТ")
for name in ("idle", "listening", "happy", "smile"):
    cfg = cf.STATES[name]
    moves = bool(cfg.talk and not cfg.static_mouth)
    check("%s — рот не двигается" % name, not moves, "talk=%s static=%s"
          % (cfg.talk, cfg.static_mouth))

print("7) «Говорящие» состояния рот двигают")
for name, cfg in cf.STATES.items():
    if name in App._SPEAKING_STATES:
        check("%s — talk и не static" % name,
              cfg.talk and not cfg.static_mouth,
              "talk=%s static=%s" % (cfg.talk, cfg.static_mouth))

print("8) Связки в коде на месте")
check("_keep_mouth_moving зовётся из _visual_tick",
      "self._keep_mouth_moving(getattr(self, \"character\", None))" in SOURCE)
check("_face_auto инициализирован в __init__",
      "self._face_auto = None" in SOURCE)
check("_TALKING_FACE в классе", "    _TALKING_FACE = {" in SOURCE)

print()
if FAILED:
    print("❌ ПРОВАЛЕНО: %d" % len(FAILED))
    for name in FAILED:
        print("   - " + name)
    sys.exit(1)
print("✅ ВСЁ ПРОЙДЕНО")
