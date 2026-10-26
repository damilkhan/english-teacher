# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_EMOJI_SPEECH.PY — ни один эмодзи не попадает в озвучку
# =========================================================
#   python tests\test_emoji_speech.py
#
# Живой баг 26.10.2026: Вербот написал «…wake up on a weekday? ⏰ 😊», и
# озвучка прочитала будильник словом. Причина — дыры в диапазонах
# EMOJI_PATTERN в tts.py: U+23F0 (⏰), U+231A (⌚), U+23F3 (⏳) лежали ВНЕ
# набора и доходили до edge-tts. Проверка сторожит символы, которые озвучка
# умеет произнести словом.
#
# Без сети и без звука: только чистые функции tts.
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# консоль Windows по умолчанию cp1251 — без этого падаем на эмодзи
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import tts  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def gone(symbol):
    return tts.remove_emojis(symbol) == ""


# =========================================================
# 1. Часы, таймеры, кнопки — тот самый будильник
# =========================================================
def test_clock():
    print("\n[1] Часы и таймеры (живой баг: ⏰ читался словом)")
    for code, symbol in ((0x231A, "⌚"), (0x23F0, "⏰"), (0x23F3, "⏳"),
                         (0x23E9, "⏩"), (0x23F8, "⏸")):
        check("U+%04X вырезан" % code, gone(symbol), repr(tts.remove_emojis(symbol)))
    check("фраза с будильником: эмодзи нет",
          "⏰" not in tts.remove_emojis("wake up on a weekday? ⏰ 😊"),
          repr(tts.remove_emojis("wake up on a weekday? ⏰ 😊")))


# =========================================================
# 2. Обычные эмодзи и значки
# =========================================================
def test_symbols():
    print("\n[2] Эмодзи и значки")
    for symbol in ("👋", "😊", "👍", "🎉", "✅", "⚽", "⭐", "☕", "⚠︎"):
        check("%s вырезан" % symbol, gone(symbol), repr(tts.remove_emojis(symbol)))
    for code, symbol in ((0x203C, "‼"), (0x2049, "⁉"), (0x2122, "™"), (0x2139, "ℹ")):
        check("U+%04X вырезан" % code, gone(symbol), repr(tts.remove_emojis(symbol)))
    check("флаг из двух codepoint вырезан",
          gone("\U0001F1FA\U0001F1F8"), repr(tts.remove_emojis("\U0001F1FA\U0001F1F8")))


# =========================================================
# 3. Составные эмодзи: селектор начертания и склейка
# =========================================================
def test_compound():
    print("\n[3] Составные эмодзи (FE0F, 20E3, 200D)")
    heart = "\u2764\uFE0F"
    check("сердце с FE0F вырезано целиком",
          tts.remove_emojis(heart) == "", repr(tts.remove_emojis(heart)))
    warn = "\u26A0\uFE0F"
    check("предупреждение с FE0F вырезано целиком",
          tts.remove_emojis(warn) == "", repr(tts.remove_emojis(warn)))
    keycap = "1\uFE0F\u20E3"
    out = tts.remove_emojis(keycap)
    check("цифра-в-рамке: осталась только цифра (рамка и FE0F ушли)",
          out == "1", repr(out))
    zwi = "\U0001F469\u200D\U0001F4BB"
    check("эмодзи со склейкой ZWJ вырезано целиком",
          tts.remove_emojis(zwi) == "", repr(tts.remove_emojis(zwi)))


# =========================================================
# 4. Обычный текст НЕ портится
# =========================================================
def test_keeps_text():
    print("\n[4] Обычный текст остаётся как был")
    samples = [
        "Hey Damil! I'm ready to chat!",
        "I wake up at 7:30 on weekdays.",
        "That's 50% right — try again.",
        "Numbers: 1, 2, 3 — and 10:30.",
        "«Ёлочки» и тире — не эмодзи.",
    ]
    for text in samples:
        out = tts.remove_emojis(text)
        check("текст цел: %s" % text[:28], out == text, repr(out))


# =========================================================
# 5. clean_for_speech: путь, которым текст идёт в озвучку
# =========================================================
def test_clean_for_speech():
    print("\n[5] clean_for_speech — ровно то, что слышит ученик")
    raw = ("Hey Damil! \U0001F44B I'm ready to chat! What time do you usually "
           "wake up on a weekday? \u23F0 \U0001F60A")
    got = tts.clean_for_speech(raw)
    check("эмодзи в речи нет", "\u23F0" not in got and "\U0001F60A" not in got, repr(got))
    check("слова на месте", got.startswith("Hey Damil!") and got.endswith("weekday?"), repr(got))
    check("двойных пробелов нет", "  " not in got, repr(got))
    check("разметка тоже снята",
          tts.clean_for_speech("**Good** job! \u23F0") == "Good job!",
          repr(tts.clean_for_speech("**Good** job! \u23F0")))
    check("только эмодзи → в озвучку не идёт",
          tts.clean_for_speech("\u23F0 \U0001F60A") == "",
          repr(tts.clean_for_speech("\u23F0 \U0001F60A")))


def main():
    test_clock()
    test_symbols()
    test_compound()
    test_keeps_text()
    test_clean_for_speech()

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
