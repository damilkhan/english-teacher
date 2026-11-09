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

    def __init__(self, lang="en", prob=0.9):
        self.calls = []
        self.lang = lang
        self.prob = prob

    def detect_language(self, audio=None, **_kw):
        # язык определяется БЕЗ распознавания (см. stt_engine 09.11.2026)
        return self.lang, self.prob, [(self.lang, self.prob)]

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return [FakeSegment(" Hello ")], FakeInfo()


def make_engine(**kwargs):
    """STTEngine с уже «загруженной» заглушкой модели (без сети/диска)."""
    eng = stt_engine.STTEngine(**kwargs)
    eng.model = FakeModel()
    # английскую модель не грузим с диска: по умолчанию — та же заглушка
    eng._english_model = eng.model
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
    check("язык английской речи задан жёстко (en)",
          kwargs.get("language") == "en", kwargs)
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

    eng.set_language("")
    check("пустая строка тоже сбрасывает язык", eng.language is None, eng.language)


def test_english_model():
    print("\n[7] Английская речь — английской моделью (09.11.2026)")
    data = pcm(speech_with_silence())

    eng = make_engine()
    base, english = FakeModel(), FakeModel()
    eng.model, eng._english_model = base, english
    eng.recognize(data)
    check("английская реплика ушла в английскую модель",
          len(english.calls) == 1 and not base.calls,
          (len(base.calls), len(english.calls)))
    _, kwargs = english.calls[0]
    check("и с жёстким языком en", kwargs.get("language") == "en", kwargs)

    print("\n[8] Русская речь — быстрой базовой моделью, без подмены")
    eng2 = make_engine()
    base2, english2 = FakeModel(lang="ru"), FakeModel()
    eng2.model, eng2._english_model = base2, english2
    result = eng2.recognize(data)
    check("русская реплика ушла в базовую модель",
          len(base2.calls) == 1 and not english2.calls,
          (len(base2.calls), len(english2.calls)))
    _, kwargs2 = base2.calls[0]
    check("язык ru", kwargs2.get("language") == "ru", kwargs2)
    check("вернулся язык ru", bool(result) and result[1] == "ru", result)

    print("\n[9] Язык не определился — всё равно английский путь")
    eng3 = make_engine()
    base3, english3 = FakeModel(lang="", prob=0.0), FakeModel()
    eng3.model, eng3._english_model = base3, english3
    eng3.recognize(data)
    check("работает английская модель", len(english3.calls) == 1,
          len(english3.calls))

    print("\n[10] Английская модель грузится ОДИН раз")
    eng4 = stt_engine.STTEngine()
    eng4.model = FakeModel()
    eng4._ready.set()
    calls = []

    def fake_loader(size, device="cpu", compute_type="int8"):
        calls.append(size)
        return FakeModel()

    real = stt_engine.WhisperModel
    stt_engine.WhisperModel = fake_loader
    try:
        first = eng4._ensure_english_model()
        second = eng4._ensure_english_model()
    finally:
        stt_engine.WhisperModel = real
    check("загрузка была ровно одна", len(calls) == 1, calls)
    check("взята модель из config.STT_ENGLISH_MODEL",
          calls == [config.STT_ENGLISH_MODEL], calls)
    check("модель закеширована", first is second and first is not None)


def test_rescue():
    data = pcm(speech_with_silence())
    print("\n[11] Страховка: мусорный английский текст -> проверка по-русски")
    eng11 = make_engine()
    base11, english11 = FakeModel(lang="lt", prob=0.31), FakeModel()
    english11.transcribe = lambda audio, **kw: ([FakeSegment(" R r Pi r S r ")],
                                               FakeInfo())
    eng11.model, eng11._english_model = base11, english11
    rescued = []

    def fake_rescue(audio):
        rescued.append(True)
        return "как сказать вилка по-английски", "ru"

    eng11._rescue_russian = fake_rescue
    result = eng11.recognize(data)
    check("страховка сработала", bool(rescued), rescued)
    check("вернулся русский текст",
          bool(result) and result[1] == "ru" and "вилка" in result[0], result)

    eng12 = make_engine()
    base12, english12 = FakeModel(lang="en", prob=0.65), FakeModel()
    english12.transcribe = lambda audio, **kw: ([FakeSegment(" I eaten canned food ")],
                                                FakeInfo())
    eng12.model, eng12._english_model = base12, english12
    called = []
    eng12._rescue_russian = lambda audio: called.append(True) or ("нельзя", "ru")
    result2 = eng12.recognize(data)
    check("нормальный текст страховку НЕ зовёт", not called, called)
    check("и остаётся английским",
          bool(result2) and result2[1] == "en" and "canned" in result2[0], result2)

    check("_looks_broken на бреде",
          stt_engine.STTEngine._looks_broken("R r Pi r S r r u") is True)
    check("_looks_broken на живой фразе",
          stt_engine.STTEngine._looks_broken("i eaten canned food") is False)


def main():
    print("=" * 60)
    print("Проверка распознавания речи (настройка, без реальной модели)")
    print("=" * 60)

    # ВАЖНО: тест не должен писать свои «записи» в logs/stt — там лежат живые
    # записи ученика, а список держит только 8 последних (09.11.2026: тест
    # вытеснил три настоящие записи синтетическими).
    saved_audio = getattr(config, "STT_SAVE_AUDIO", False)
    config.STT_SAVE_AUDIO = False

    test_trim()
    test_recognize_options()
    test_silence_only()
    test_too_short()
    test_hotwords()
    test_forced_language()
    test_english_model()
    test_rescue()

    config.STT_SAVE_AUDIO = saved_audio

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()