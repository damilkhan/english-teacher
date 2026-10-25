# =========================================================
# TESTS/TEST_VOICE_CHOICE.PY — выбор английского голоса в настройках
# =========================================================
#   python tests\test_voice_choice.py
#
# ЗАЧЕМ (просьба ученика 26.10.2026): дать выбор Emma / Ava / Ana в
# настройках. Проверяем БЕЗ звука и БЕЗ окна:
#   1) в списке ровно три голоса, у каждого есть тон и темп;
#   2) set_voice меняет голос, кэш чистится, неизвестный → Emma;
#   3) settings_store хранит voice_en (round-trip, битый файл не роняет).
# =========================================================

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import settings_store                                          # noqa: E402
import tts                                                     # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def test_voice_list():
    print("\n[1] список голосов")
    items = tts.voices()
    ids = [vid for vid, _lb in items]
    check("три голоса", len(items) == 3, items)
    check("Emma / Ava / Ana",
          ids == ["en-US-EmmaNeural", "en-US-AvaMultilingualNeural",
                  "en-US-AnaNeural"], ids)
    check("у каждого свой тон", all(vid in tts.VOICE_PITCH for vid in ids),
          list(tts.VOICE_PITCH))
    check("у каждого свой темп", all(vid in tts.VOICE_RATE for vid in ids),
          list(tts.VOICE_RATE))
    check("подписи не пустые", all(lb.strip() for _vid, lb in items), items)
    check("по умолчанию Emma", tts.VOICE_EN_DEFAULT == "en-US-EmmaNeural",
          tts.VOICE_EN_DEFAULT)


def test_set_voice():
    print("\n[2] set_voice")
    orig = tts.VOICE_EN
    try:
        check("Emma → VOICE_EN", tts.set_voice("en-US-EmmaNeural") == "en-US-EmmaNeural"
              and tts.VOICE_EN == "en-US-EmmaNeural", tts.VOICE_EN)
        check("Ana → VOICE_EN", tts.set_voice("en-US-AnaNeural") == "en-US-AnaNeural"
              and tts.VOICE_EN == "en-US-AnaNeural", tts.VOICE_EN)
        check("Ava → VOICE_EN", tts.set_voice("en-US-AvaMultilingualNeural")
              == "en-US-AvaMultilingualNeural"
              and tts.VOICE_EN == "en-US-AvaMultilingualNeural", tts.VOICE_EN)
        check("старый VOICE (совместимость) следует за VOICE_EN",
              tts.VOICE == tts.VOICE_EN, (tts.VOICE, tts.VOICE_EN))
        check("русский голос не менялся",
              tts.VOICE_RU == "ru-RU-SvetlanaNeural", tts.VOICE_RU)
        check("пустое → голос по умолчанию",
              tts.set_voice("") == tts.VOICE_EN_DEFAULT, tts.VOICE_EN)
        check("неизвестный → голос по умолчанию",
              tts.set_voice("en-US-GhostNeural") == tts.VOICE_EN_DEFAULT, tts.VOICE_EN)
        check("None не роняет",
              tts.set_voice(None) == tts.VOICE_EN_DEFAULT, tts.VOICE_EN)
        check("voice_for('en') отдаёт выбранный",
              tts.voice_for("en") == tts.VOICE_EN, tts.voice_for("en"))
        check("voice_for('ru') отдаёт Светлану",
              tts.voice_for("ru") == tts.VOICE_RU, tts.voice_for("ru"))
        # кэш: кладём подделку, set_voice обязан её вычистить
        tts._cache[("x", "+0%", "y")] = b"zzz"
        tts.set_voice("en-US-EmmaNeural")
        check("кэш чистится при смене", len(tts._cache) == 0, len(tts._cache))
    finally:
        tts.set_voice(orig)


def test_settings_store():
    print("\n[3] settings_store: voice_en")
    real = settings_store.SETTINGS_PATH
    tmp = os.path.join(tempfile.mkdtemp(), "settings.json")
    settings_store.SETTINGS_PATH = tmp
    try:
        check("нет файла → ''", settings_store.get_voice_en() == "",
              settings_store.get_voice_en())
        check("запись голоса", settings_store.set_voice_en("en-US-AnaNeural")
              and os.path.exists(tmp))
        check("round-trip", settings_store.get_voice_en() == "en-US-AnaNeural",
              settings_store.get_voice_en())
        settings_store.set_selected_model("gemma4-e4b")
        check("другие ключи не потерялись",
              settings_store.get_voice_en() == "en-US-AnaNeural"
              and settings_store.load().get("model_id") == "gemma4-e4b",
              settings_store.load())
        settings_store.set_voice_en("")
        check("пусто сохраняется как ''", settings_store.get_voice_en() == "",
              settings_store.get_voice_en())
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("{ битый")
        check("битый файл → ''", settings_store.get_voice_en() == "",
              settings_store.get_voice_en())
    finally:
        settings_store.SETTINGS_PATH = real


def main():
    test_voice_list()
    test_set_voice()
    test_settings_store()
    print()
    if FAILED:
        print("❌ ПРОВАЛОВ: %d — %s" % (len(FAILED), FAILED))
        return 1
    print("✅ все проверки прошли")
    return 0


if __name__ == "__main__":
    sys.exit(main())
