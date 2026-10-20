# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_TTS_LOCAL_FALLBACK.PY
# =========================================================
#   python tests\test_tts_local_fallback.py
#
# Проверяет ДВА новых механизма озвучки:
#   1) ПАРАЛЛЕЛЬНЫЕ запросы к edge-tts (config.TTS_PARALLEL_JOBS = 3):
#      замер 20.10.2026 — один запрос лотерея (18 подряд → 8 сбоёв),
#      три параллельных — 10/10, медиана 1.08 с;
#   2) ЛОКАЛЬНЫЙ ЗАПАС piper для английских кусков (config.PIPER_FALLBACK):
#      когда сети нет, слово больше не пропадает молча.
#
# Ни сети, ни звука, ни модели не нужно: edge-tts и piper подменяются.
# =========================================================

import io
import os
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config  # noqa: E402
import tts     # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← %r" % (detail,)))
    if not ok:
        FAILED.append(name)


class silent_warm:
    """Не даём фоновому прогреву мешать счёту запросов."""
    def __enter__(self):
        self.lock = tts._warm_lock
        with tts._warm_lock:
            self.was = tts._warm_running
            tts._warm_running = True
        return self

    def __exit__(self, *a):
        with tts._warm_lock:
            tts._warm_running = self.was


class FakeVoice:
    """Заглушка piper: пишет крошечный настоящий WAV и считает вызовы."""

    def __init__(self):
        self.calls = []

    def synthesize_wav(self, text, wav_file, syn_config=None):
        self.calls.append((text, getattr(syn_config, "length_scale", None)))
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x01" * 400)


class FakeOut:
    def __init__(self):
        self.written = 0

    def write(self, arr):
        self.written += 1


# =========================================================
# 1. Параллельные запросы: первый удачный ответ побеждает
# =========================================================
def test_parallel_race():
    print("\n[1] Параллельные запросы: один кусок стреляем сразу в 3")
    orig_once = tts._download_once
    orig_jobs = config.TTS_PARALLEL_JOBS
    calls = []

    def flaky(text, voice):
        calls.append(time.monotonic())
        time.sleep(0.15 if len(calls) != 2 else 0.02)   # второй отвечает быстрее
        return b"MP3" if len(calls) >= 2 else None

    tts._download_once = flaky
    config.TTS_PARALLEL_JOBS = 3
    try:
        with silent_warm():
            t0 = time.monotonic()
            data = tts._download("Hello there.", tts.VOICE_EN)
            spent = time.monotonic() - t0
        check("ответ получен с первой удачной попытки", data == b"MP3", data)
        check("запросов ушло не больше TTS_PARALLEL_JOBS (%d)" % config.TTS_PARALLEL_JOBS,
              len(calls) <= 3, len(calls))
        check("запросы шли ОДНОВРЕМЕННО (все стартовали в 30 мс)", 
              max(calls) - min(calls) < 0.03, [round(c - calls[0], 3) for c in calls])
        check("ожидание короче последовательного: %.2f с" % spent, spent < 0.30, spent)
    finally:
        tts._download_once = orig_once
        config.TTS_PARALLEL_JOBS = orig_jobs


def test_parallel_all_fail():
    print("\n[1b] Все параллельные неудачны → повторов не больше RETRY_ATTEMPTS")
    orig_once = tts._download_once
    orig_jobs = config.TTS_PARALLEL_JOBS
    orig_delay = tts.RETRY_DELAY
    orig_rewarm = tts.warmup_async
    calls = []

    def dead(text, voice):
        calls.append(1)
        return None

    tts._download_once = dead
    tts.RETRY_DELAY = 0.01
    tts.warmup_async = lambda: None            # прогрев не должен мешать
    config.TTS_PARALLEL_JOBS = 3
    try:
        with silent_warm():
            data = tts._download("Hello there.", tts.VOICE_EN)
        check("ничего не скачалось", data is None, data)
        check("попыток ровно RETRY_ATTEMPTS (%d)" % tts.RETRY_ATTEMPTS,
              len(calls) == tts.RETRY_ATTEMPTS, len(calls))
    finally:
        tts._download_once = orig_once
        tts.RETRY_DELAY = orig_delay
        tts.warmup_async = orig_rewarm
        config.TTS_PARALLEL_JOBS = orig_jobs


def test_sequential_still_works():
    print("\n[1c] TTS_PARALLEL_JOBS = 1 → прежнее поведение (по очереди)")
    orig_once = tts._download_once
    orig_jobs = config.TTS_PARALLEL_JOBS
    orig_delay = tts.RETRY_DELAY
    orig_rewarm = tts.warmup_async
    stamps = []

    def once(text, voice):
        stamps.append(time.monotonic())
        return None

    tts._download_once = once
    tts.RETRY_DELAY = 0.05
    tts.warmup_async = lambda: None
    config.TTS_PARALLEL_JOBS = 1
    try:
        with silent_warm():
            tts._download("Hello there.", tts.VOICE_EN)
        gaps = [round(b - a, 3) for a, b in zip(stamps, stamps[1:])]
        check("попыток RETRY_ATTEMPTS (%d)" % tts.RETRY_ATTEMPTS,
              len(stamps) == tts.RETRY_ATTEMPTS, len(stamps))
        check("попытки шли ПОСЛЕДОВАТЕЛЬНО (пауза ≥ RETRY_DELAY)",
              bool(gaps) and min(gaps) >= 0.04, gaps)
    finally:
        tts._download_once = orig_once
        tts.RETRY_DELAY = orig_delay
        tts.warmup_async = orig_rewarm
        config.TTS_PARALLEL_JOBS = orig_jobs


# =========================================================
# 2. Локальный запас: piper
# =========================================================
def test_piper_settings():
    print("\n[2] Настройки локального запаса")
    check("PIPER_FALLBACK включён по умолчанию", config.PIPER_FALLBACK is True,
          config.PIPER_FALLBACK)
    check("голос — файл .onnx", str(config.PIPER_VOICE_EN).endswith(".onnx"),
          config.PIPER_VOICE_EN)
    check("папка голосов — models/piper", "piper" in str(config.PIPER_MODEL_DIR),
          config.PIPER_MODEL_DIR)
    check("piper_path() собирает путь от корня проекта",
          tts.piper_path().replace("\\", "/").endswith("models/piper/" + config.PIPER_VOICE_EN),
          tts.piper_path())
    check("TTS_PARALLEL_JOBS ≥ 1", int(config.TTS_PARALLEL_JOBS) >= 1,
          config.TTS_PARALLEL_JOBS)


def test_piper_missing_file():
    print("\n[2b] Файла голоса нет → запас молчит, ничего не падает")
    orig_name = config.PIPER_VOICE_EN
    orig_failed = tts._piper_failed
    config.PIPER_VOICE_EN = "no_such_voice.onnx"
    tts._piper_failed = False
    try:
        check("piper_available() = False", tts.piper_available() is False,
              tts.piper_available())
        check("piper_synth() = None", tts.piper_synth("Hello") is None,
              tts.piper_synth("Hello"))
        check("_piper_play() = False", tts._piper_play(FakeOut(), "Hello", "en",
                                                       24000, 1, tts._bump_generation()) is False)
    finally:
        config.PIPER_VOICE_EN = orig_name
        tts._piper_failed = orig_failed


def test_piper_synth_wav():
    print("\n[2c] Заглушка голоса → настоящий WAV и кэш")
    orig_voice, orig_failed = tts._piper_voice, tts._piper_failed
    orig_name, orig_dir = config.PIPER_VOICE_EN, config.PIPER_MODEL_DIR
    fake = FakeVoice()
    tts._piper_voice = fake
    tts._piper_failed = False
    tts._piper_cache.clear()
    # своим «голосом» объявляем сам файл теста: он точно существует
    config.PIPER_MODEL_DIR = "tests"
    config.PIPER_VOICE_EN = os.path.basename(__file__)
    try:
        data = tts.piper_synth("Great job!")
        check("вернулись байты", bool(data), data and len(data))
        check("это WAV (заголовок RIFF)", bytes(data[:4]) == b"RIFF", data[:4])
        check("голос позвали один раз", len(fake.calls) == 1, fake.calls)
        check("темп взят из config", fake.calls[0][1] == config.PIPER_LENGTH_SCALE,
              fake.calls[0])
        tts.piper_synth("Great job!")
        check("повтор берётся из кэша (голос не звали)", len(fake.calls) == 1,
              fake.calls)
        with wave.open(io.BytesIO(data or b"")) as w:
            check("частота 22050 Гц", w.getframerate() == 22050, w.getframerate())
            check("моно", w.getnchannels() == 1, w.getnchannels())
    finally:
        tts._piper_voice, tts._piper_failed = orig_voice, orig_failed
        config.PIPER_VOICE_EN, config.PIPER_MODEL_DIR = orig_name, orig_dir
        tts._piper_cache.clear()


def test_piper_russian_refused():
    print("\n[2d] Русский кусок локальным голосом НЕ читаем")
    orig_voice, orig_failed = tts._piper_voice, tts._piper_failed
    orig_name, orig_dir = config.PIPER_VOICE_EN, config.PIPER_MODEL_DIR
    fake = FakeVoice()
    tts._piper_voice = fake
    tts._piper_failed = False
    tts._piper_cache.clear()
    config.PIPER_MODEL_DIR = "tests"
    config.PIPER_VOICE_EN = os.path.basename(__file__)
    try:
        gen = tts._bump_generation()
        ok = tts._piper_play(FakeOut(), "Молодец!", "ru", 24000, 1, gen)
        check("для ru → False", ok is False, ok)
        check("голос даже не звали", not fake.calls, fake.calls)
        ok_en = tts._piper_play(FakeOut(), "Well done!", "en", 24000, 1, tts._bump_generation())
        check("для en → True", ok_en is True, ok_en)
    finally:
        tts._piper_voice, tts._piper_failed = orig_voice, orig_failed
        config.PIPER_VOICE_EN, config.PIPER_MODEL_DIR = orig_name, orig_dir
        tts._piper_cache.clear()


def test_segment_falls_back_to_piper():
    print("\n[3] Сеть молчит → _play_segment уходит в локальный голос")
    orig = (tts._download, tts._decode_into, tts._decode_stream_into,
            tts._piper_voice, tts._piper_failed)
    orig_name, orig_dir = config.PIPER_VOICE_EN, config.PIPER_MODEL_DIR
    fake = FakeVoice()
    order = []

    def no_decode(out, data, sr, ch, gen):
        order.append("предзагрузка")
        return False

    def no_stream(out, text, voice, sr, ch, gen):
        order.append("поток")
        return False

    tts._piper_voice = fake
    tts._piper_failed = False
    tts._piper_cache.clear()
    config.PIPER_MODEL_DIR = "tests"
    config.PIPER_VOICE_EN = os.path.basename(__file__)
    tts._download = lambda text, voice: None
    tts._decode_into = no_decode
    tts._decode_stream_into = no_stream
    try:
        out = FakeOut()
        gen = tts._bump_generation()
        ok = tts._play_segment(out, "See you tomorrow!", tts.VOICE_EN,
                               24000, 1, gen, None, lang="en")
        check("кусок всё-таки прозвучал", ok is True, ok)
        check("сначала попробовали сеть (потоком)", order == ["поток"], order)
        check("потом локальный голос (1 раз)", len(fake.calls) == 1, fake.calls)
        check("звук ушёл в общий поток вывода", out.written > 0, out.written)

        # русский кусок: локального голоса нет — молчим, но не падаем
        fake.calls.clear()
        ok_ru = tts._play_segment(FakeOut(), "Молодец!", tts.VOICE_RU,
                                  24000, 1, tts._bump_generation(), None, lang="ru")
        check("русский кусок локально не читается", ok_ru is False, ok_ru)
        check("голос для ru не звали", not fake.calls, fake.calls)
    finally:
        (tts._download, tts._decode_into, tts._decode_stream_into,
         tts._piper_voice, tts._piper_failed) = orig
        config.PIPER_VOICE_EN, config.PIPER_MODEL_DIR = orig_name, orig_dir
        tts._piper_cache.clear()


def test_speak_chunk_uses_piper():
    print("\n[3b] Запасной путь speak(): сбой сети → локальный голос")
    orig = (tts._synthesize, tts._play, tts._piper_voice, tts._piper_failed,
            tts._streaming_enabled)
    orig_name, orig_dir = config.PIPER_VOICE_EN, config.PIPER_MODEL_DIR
    fake = FakeVoice()
    played = []
    tts._piper_voice = fake
    tts._piper_failed = False
    tts._piper_cache.clear()
    config.PIPER_MODEL_DIR = "tests"
    config.PIPER_VOICE_EN = os.path.basename(__file__)
    tts._synthesize = lambda text, voice: None
    tts._play = lambda data, gen, suffix=".mp3": played.append((data[:4], suffix))
    tts._streaming_enabled = lambda: False
    try:
        ok = tts._speak_chunk("Hello there", tts.VOICE_EN, tts._bump_generation())
        check("кусок озвучен локально", ok is True, ok)
        check("сыграли WAV с расширением .wav",
              played and played[0][0] == b"RIFF" and played[0][1] == ".wav", played)
        played.clear()
        ok_ru = tts._speak_chunk("Привет, друг", tts.VOICE_RU, tts._bump_generation())
        check("русский кусок без сети не играется (и не падает)", ok_ru is False, ok_ru)
        check("ничего не проиграно для ru", not played, played)
    finally:
        (tts._synthesize, tts._play, tts._piper_voice, tts._piper_failed,
         tts._streaming_enabled) = orig
        config.PIPER_VOICE_EN, config.PIPER_MODEL_DIR = orig_name, orig_dir
        tts._piper_cache.clear()


def main():
    print("=" * 60)
    print("  TTS: параллельные запросы + локальный запас (piper)")
    print("=" * 60)
    test_parallel_race()
    test_parallel_all_fail()
    test_sequential_still_works()
    test_piper_settings()
    test_piper_missing_file()
    test_piper_synth_wav()
    test_piper_russian_refused()
    test_segment_falls_back_to_piper()
    test_speak_chunk_uses_piper()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        return 1
    print("ВСЁ ЗЕЛЁНОЕ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
