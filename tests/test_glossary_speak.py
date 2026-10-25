# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GLOSSARY_SPEAK.PY — клик по слову: Вербот произносит его
# =========================================================
#   python tests\test_glossary_speak.py
#
# ЗАЧЕМ. Решение ученика (25.10.2026): клик по подсвеченному слову в
# подсказке — Вербот произносит его по-английски. Первый клик обычным
# темпом, второй по тому же слову — вдвое медленнее, и так поочерёдно.
#
# Проверяем:
#   1) tts.rate_for: явная скорость важнее скорости голоса;
#   2) speak(rate=...) доносит скорость до скачивания И до кэша
#      (одинаковый текст в двух темпах — два разных mp3);
#   3) ChatView: клик по слову зовёт on_speak_word("слово", False);
#      второй клик — True; третий — снова False;
#   4) другое слово → снова обычный темп (счёт начинается заново);
#   5) клик мимо слова закрывает подсказку и НЕ зовёт озвучку;
#   6) окно при клике остаётся открытым (не мешает слушать);
#   7) ui/app._speak_word: slow=True → rate="−50%", slow=False → None;
#   8) константа WORD_SLOW_RATE медленнее обычного (знак «−»);
#   9) в app.py у ChatView передан on_speak_word.
# =========================================================

import os
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import customtkinter as ctk      # noqa: E402

import theme                     # noqa: E402
import tts                       # noqa: E402
from ui.widgets.chat_view import ChatView   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  \u2705 " if ok else "  \u274c ") + name + ("" if ok else "  \u2190 " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class Ev:
    def __init__(self, x=0, y=0, x_root=0, y_root=0):
        self.x, self.y = x, y
        self.x_root, self.y_root = x_root, y_root


# ---------------------------------------------------------
print("[1] tts: явная скорость важнее скорости голоса")
check("обычная скорость берётся из VOICE_RATE",
      tts.rate_for(tts.VOICE_EN) == tts.VOICE_RATE[tts.VOICE_EN],
      tts.rate_for(tts.VOICE_EN))
check("явная скорость перебивает голос",
      tts.rate_for(tts.VOICE_EN, tts.WORD_SLOW_RATE) == tts.WORD_SLOW_RATE,
      tts.rate_for(tts.VOICE_EN, tts.WORD_SLOW_RATE))
check("пустая скорость = скорость голоса",
      tts.rate_for(tts.VOICE_EN, None) == tts.VOICE_RATE[tts.VOICE_EN])
check("WORD_SLOW_RATE — замедление",
      tts.WORD_SLOW_RATE.startswith("-") and tts.WORD_SLOW_RATE.endswith("%"),
      tts.WORD_SLOW_RATE)

# ---------------------------------------------------------
print("\n[2] speak(rate=...) доносит скорость до скачивания и кэша")
seen = []


def fake_download(text, voice, rate=None):
    seen.append((text, voice, rate))
    return ("mp3:" + text + "|" + str(rate)).encode("utf-8")


played_words = []
orig = (tts._download, tts._stream_play_segments, tts._STREAM_OK,
        tts._stream_play, tts._streaming_enabled, tts._play)
try:
    tts._download = fake_download
    tts._stream_play_segments = lambda *a, **k: False   # идём запасным путём
    tts._stream_play = lambda *a, **k: False
    tts._streaming_enabled = lambda: False              # без сети и потока
    tts._play = lambda data, gen, suffix=".mp3": played_words.append(data)
    tts.clear_cache()
    tts.speak("hello", rate=tts.WORD_SLOW_RATE)
    check("скорость дошла до скачивания", seen and seen[-1][2] == tts.WORD_SLOW_RATE, seen)
    tts.clear_cache()
    seen.clear()
    tts.speak("hello")
    check("без rate скорость = обычная (None)", seen and seen[-1][2] is None, seen)
    tts.clear_cache()
    seen.clear()
    tts.speak("hello", rate=tts.WORD_SLOW_RATE)
    tts.speak("hello")
    check("два темпа — два скачивания (кэш по скорости)",
          len(seen) == 2 and {seen[0][2], seen[1][2]} == {tts.WORD_SLOW_RATE, None}, seen)
finally:
    (tts._download, tts._stream_play_segments, tts._STREAM_OK,
     tts._stream_play, tts._streaming_enabled, tts._play) = orig

# ---------------------------------------------------------
print("\n[3] Клик по слову: чередование темпа")
root = ctk.CTk()
root.geometry("760x520+40+40")
root.withdraw()
said = []


def on_hover(text, pos):
    """Как настоящий словарь: пробел и знак — не слово (там None)."""
    if not (0 <= pos < len(text)) or not text[pos].isalnum():
        return None
    for word in ("Look forward to", "there"):
        start = text.find(word)
        if start <= pos < start + len(word):
            return {"en": word, "ru": "перевод", "phrase": " " in word,
                    "start": start, "end": start + len(word)}
    return None


chat = ChatView(root, theme.DARK, on_hover_word=on_hover,
                on_speak_word=lambda word, slow: said.append((word, slow)))
chat.pack(fill="both", expand=True)
root.update()
mark = chat.add_message("Jane", "Look forward to seeing you there!")
root.update()
body = chat._messages[mark].body
root.update()

box = body.bbox("1.2")
check("слово «there» видно", box is not None, box)
# bbox по индексу 1.2 — курсор внутри «Look forward to»; берём точку по слову
start = body.get("1.0", "end-1c").find("there")
box_t = body.bbox(chat._text_index(body, start))
check("слово «there» имеет координаты", box_t is not None, box_t)


def click_on(index_offset):
    box = body.bbox(chat._text_index(body, index_offset))
    chat._gloss_click(body, Ev(x=box[0] + 2, y=box[1] + box[3] // 2,
                               x_root=100, y_root=100))
    root.update()


if box_t:
    click_on(start)
    check("первый клик — обычная скорость", said == [("there", False)], said)
    check("окно открыто после клика", chat._gloss_tip is not None)
    click_on(start)
    check("второй клик — медленно", said[-1] == ("there", True), said)
    click_on(start)
    check("третий клик — снова обычная", said[-1] == ("there", False), said)
    check("всего три озвучки", len(said) == 3, said)

    print("\n[4] Другое слово — счёт темпа заново")
    said.clear()
    other = body.get("1.0", "end-1c").find("Look")
    click_on(other)
    check("первый клик по другому слову — обычная скорость",
          said and said[-1][1] is False, said)
    click_on(other)
    check("и его второй клик — медленно", said[-1][1] is True, said)

    print("\n[5] Клик мимо слова")
    said.clear()
    chat._gloss_hide()
    root.update()
    # берём ПРОБЕЛ в тексте: bbox пробела (а не «далеко вбок» — там текст)
    clean = body.get("1.0", "end-1c")
    space = clean.find(" ", clean.find("there") + len("there"))
    if space < 0:
        space = clean.find(" ")
    sbox = body.bbox(chat._text_index(body, space))
    check("пробел имеет координаты", sbox is not None, sbox)
    chat._gloss_click(body, Ev(x=sbox[0] + 1, y=sbox[1] + sbox[3] // 2,
                               x_root=100, y_root=100))
    root.update()
    check("клик мимо слова ничего не озвучивает", said == [], said)
    check("подсказка закрыта", chat._gloss_tip is None)
    check("подсветка снята", tuple(body.tag_ranges("gloss")) == (),
          tuple(body.tag_ranges("gloss")))
else:
    check("координаты слова получены", False, "bbox не посчитан")

# ---------------------------------------------------------
print("\n[6] ui/app: _speak_word переводит флаг в скорость")
app_path = os.path.join(ROOT, "ui", "app.py")
source = open(app_path, encoding="utf-8").read()
check("ChatView получает on_speak_word",
      "on_speak_word=self._speak_word" in source)
check("_speak_word объявлен", "def _speak_word(self, word, slow)" in source)
check("медленный темп берётся из tts.WORD_SLOW_RATE",
      "tts.WORD_SLOW_RATE" in source)
check("_say принимает rate", re.search(r"def _say\(self, text, on_done=None, parts=None, "
                                       r"on_part=None, rate=None\)", source) is not None)
check("_say передаёт rate в tts.speak", "on_part=on_part, rate=rate" in source)


class Stub:
    """Пустышка приложения: только то, что нужно _say/_speak_word."""

    def __init__(self):
        self.current_user = {}
        self._speech_busy = False
        self.calls = []
        self._notify_no_voice = lambda: None
        self._clear_no_voice = lambda: None

    def _dispatch(self, fn):
        fn()


import ui.app as app_mod   # noqa: E402

APP_CLS = app_mod.EnglishTeacherApp
Stub._say = APP_CLS._say          # проверяем настоящую _say, а не заглушку

stub = Stub()
orig_speak = tts.speak
recorded = []


def fake_speak(text, **kw):
    recorded.append((text, kw.get("rate")))
    return True


try:
    tts.speak = fake_speak
    APP_CLS._speak_word(stub, "there", False)
    for _ in range(50):
        if recorded:
            break
        time.sleep(0.02)
    check("обычный клик → rate None", recorded == [("there", None)], recorded)
    recorded.clear()
    APP_CLS._speak_word(stub, "there", True)
    for _ in range(50):
        if recorded:
            break
        time.sleep(0.02)
    check("медленный клик → rate WORD_SLOW_RATE",
          recorded == [("there", tts.WORD_SLOW_RATE)], recorded)
    recorded.clear()
    APP_CLS._speak_word(stub, "   ", True)
    time.sleep(0.1)
    check("пустое слово не озвучивается", recorded == [], recorded)
finally:
    tts.speak = orig_speak

# ---------------------------------------------------------
print()
if FAILED:
    print("\u0418\u0422\u041e\u0413: \u043f\u0440\u043e\u0432\u0430\u043b\u043e\u0432: %d" % len(FAILED))
    for name in FAILED:
        print("  - " + name)
    sys.exit(1)
print("\u0418\u0422\u041e\u0413: \u0432\u0441\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u043f\u0440\u043e\u0439\u0434\u0435\u043d\u044b")
