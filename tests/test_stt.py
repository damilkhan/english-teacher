# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_STT.PY — настройка распознавания (faster-whisper)
# =========================================================
#   python tests\test_stt.py
#
# Проверяем БЕЗ загрузки настоящей модели (она тяжёлая): подменяем модель
# заглушкой и смотрим, какие параметры уходят в transcribe(), как работает
# обрезка тишины и подсказки (hotwords / initial_prompt).
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

import numpy as np                                # noqa: E402
import config                                     # noqa: E402
import stt_engine                                 # noqa: E402

SR = stt_engine.SAMPLE_RATE

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeInfo:
    language = "en"
    language_probability = 0.99


class FakeModel:
    """Заглушка WhisperModel: запоминаем, что пришло на вход."""

    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return [FakeSegment(" Hello ")], FakeInfo()


def make_engine(**kwargs):
    """STTEngine с уже «загруженной» заглушкой модели (без сети/диска)."""
    eng = stt_engine.STTEngine(**kwargs)
    eng.model = FakeModel()
    eng._ready.set()
    return eng


def pcm(samples):
    """Массив сэмплов int16 → байты, как отдаёт микрофон."""
    return np.asarray(samples, dtype=np.int16).tobytes()


def speech_with_silence(before=0.3, speech=1.0, after=0.3, amp=6000):
    """Запись: тишина + «речь» (постоянный тон) + тишина."""
    return np.concatenate([
        np.zeros(int(SR * before), np.int16),
        np.full(int(SR * speech), amp, np.int16),
        np.zeros(int(SR * after), np.int16),
    ])


def test_trim():
    print("\n[1] Обрезка тишины по краям")
    eng = stt_engine.STTEngine()
    data = speech_with_silence().astype(np.float32) / 32768.0
    trimmed = eng._trim_silence(data, 0.01)
    check("тишина по краям убрана", trimmed.size < data.size,
          "было %d, стало %d" % (data.size, trimmed.size))
    check("сама речь осталась целиком", trimmed.size >= SR * 0.95, trimmed.size)

    silence = np.zeros(SR * 2, np.float32)
    check("полная тишина → пусто", eng._trim_silence(silence, 0.01).size == 0)


def test_recognize_options():
    print("\n[2] Параметры transcribe() уходят из config")
    eng = make_engine()
    data = pcm(speech_with_silence())
    result = eng.recognize(data)

    check("модель вызвана один раз", len(eng.model.calls) == 1, len(eng.model.calls))
    check("текст распознан и приведён к нижнему регистру", result == ("hello", "en"), result)

    audio, kwargs = eng.model.calls[0]
    check("language=None (автоопределение)", kwargs.get("language", "?") is None, kwargs)
    check("beam_size из config.STT_BEAM_SIZE",
          kwargs.get("beam_size") == config.STT_BEAM_SIZE, kwargs)
    check("best_of >= beam_size", kwargs.get("best_of", 0) >= kwargs.get("beam_size", 9), kwargs)
    check("without_timestamps=True", kwargs.get("without_timestamps") is True, kwargs)
    check("condition_on_previous_text=False",
          kwargs.get("condition_on_previous_text") is False, kwargs)
    check("в модель ушло ОБРЕЗАННОЕ аудио", audio.size < len(data) // 2,
          "было %d, стало %d" % (len(data) // 2, audio.size))


def test_silence_only():
    print("\n[3] Запись из одной тишины не уходит в модель")
    eng = make_engine()
    result = eng.recognize(pcm(np.zeros(SR * 2, np.int16)))
    check("результат None", result is None, result)
    check("модель НЕ вызывалась", not eng.model.calls, eng.model.calls)


def test_too_short():
    print("\n[4] Слишком короткая запись не уходит в модель")
    eng = make_engine()
    result = eng.recognize(b"\x00" * 100)
    check("результат None", result is None, result)
    check("модель НЕ вызывалась", not eng.model.calls, eng.model.calls)


def test_hotwords():
    print("\n[5] Подсказки: провайдер и set_context")
    data = pcm(speech_with_silence())

    eng = make_engine(hotwords_provider=lambda: "Damil, Дамиль")
    eng.recognize(data)
    _, kwargs = eng.model.calls[0]
    check("hotwords от провайдера ушли в модель",
          kwargs.get("hotwords") == "Damil, Дамиль", kwargs)

    eng2 = make_engine()
    eng2.set_context(hotwords="Damil", initial_prompt="English lesson about travel")
    eng2.recognize(data)
    _, kwargs2 = eng2.model.calls[0]
    check("hotwords от set_context ушли в модель",
          kwargs2.get("hotwords") == "Damil", kwargs2)
    check("initial_prompt ушёл в модель",
          kwargs2.get("initial_prompt") == "English lesson about travel", kwargs2)

    eng3 = make_engine()
    eng3.recognize(data)
    _, kwargs3 = eng3.model.calls[0]
    check("без подсказок ключей hotwords/initial_prompt нет",
          "hotwords" not in kwargs3 and "initial_prompt" not in kwargs3, kwargs3)


def test_forced_language():
    print("\n[6] Жёсткий английский в окне повторения слов (27.10.2026)")
    data = pcm(speech_with_silence())

    eng = make_engine()
    eng.set_language("en")
    eng.recognize(data)
    _, kwargs = eng.model.calls[0]
    check("set_language('en') → language='en' в модель",
          kwargs.get("language") == "en", kwargs)

    eng.set_language(None)
    eng.recognize(data)
    _, kwargs2 = eng.model.calls[1]
    check("set_language(None) → снова автоопределение",
          kwargs2.get("language") is None, kwargs2)

    eng.set_language("")
    check("пустая строка тоже сбрасывает язык", eng.language is None, eng.language)


def main():
    print("=" * 60)
    print("Проверка распознавания речи (настройка, без реальной модели)")
    print("=" * 60)

    test_trim()
    test_recognize_options()
    test_silence_only()
    test_too_short()
    test_hotwords()
    test_forced_language()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()