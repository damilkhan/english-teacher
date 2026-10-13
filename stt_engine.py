import threading

import numpy as np
from faster_whisper import WhisperModel

import config

# Частота дискретизации записи: audio_vad.py пишет 16 кГц, int16.
SAMPLE_RATE = 16000
# Длина кадра при обрезке тишины, мс.
TRIM_FRAME_MS = 20


class STTEngine:
    """Распознавание речи (faster-whisper).

    Загрузка модели занимает десятки секунд. Раньше она шла прямо в
    конструкторе — в главном потоке Tk, из-за чего окно «не отвечало» при
    старте. Теперь модель грузится в ФОНЕ (preload), а окно появляется сразу;
    recognize() при необходимости дожидается окончания загрузки (он и так
    вызывается из фонового потока распознавания).

    on_state(state, message) — необязательный колбэк: "loading" | "ready" |
    "error". Вызывается из фонового потока, поэтому интерфейс обязан
    прокинуть его в главный поток (в приложении — через dispatch).

    Подсказки для распознавания (имена и термины, которые Whisper часто
    слышит неверно) задаются через set_context() ЛИБО через
    hotwords_provider — вызываемый объект, возвращающий строку слов. Если
    задан провайдер, подсказка берётся у него на КАЖДОМ распознавании
    (например, имя активного ученика всегда актуально).
    """

    def __init__(self, model_size=None, on_state=None, hotwords_provider=None):
        # модель берём из config (STT_MODEL_SIZE); явный аргумент перекрывает
        self.model_size = model_size or getattr(config, "STT_MODEL_SIZE", "base")
        self.on_state = on_state
        self.hotwords_provider = hotwords_provider
        self.hotwords = str(getattr(config, "STT_HOTWORDS", "") or "")
        self.initial_prompt = ""
        self.model = None
        self.error = None
        self._ready = threading.Event()   # загрузка завершилась (успех/ошибка)
        self._loading = False
        self._failed = False

    # -----------------------------------------------------
    # Состояние
    # -----------------------------------------------------
    @property
    def is_ready(self):
        return self._ready.is_set() and self.model is not None

    def set_context(self, hotwords=None, initial_prompt=None):
        """Подсказки для распознавания (необязательны; None — не менять).

        hotwords — короткий список слов (имена, термины), которые нужно
        «подсказать» модели; initial_prompt — фраза-контекст (например, тема
        урока). Оба необязательны и спокойно переживают отсутствие модели.
        """
        if hotwords is not None:
            self.hotwords = str(hotwords)
        if initial_prompt is not None:
            self.initial_prompt = str(initial_prompt)

    def _emit(self, state, message):
        if self.on_state is None:
            return
        try:
            self.on_state(state, message)
        except Exception as exc:
            print("⚠️ STT: колбэк состояния не сработал (%s)" % exc)

    # -----------------------------------------------------
    # Фоновая загрузка
    # -----------------------------------------------------
    def preload(self):
        """Запускает загрузку модели в фоновом потоке. Не блокирует окно."""
        if self._loading or self._ready.is_set():
            return False
        self._loading = True
        self._emit("loading", "загружаю модель распознавания")
        threading.Thread(target=self._load, daemon=True).start()
        return True

    def _load(self):
        try:
            print(f"⏳ Загрузка Whisper '{self.model_size}' (автоопределение языка)...")
            # model_size: tiny (~75MB), base (~150MB), small (~500MB), medium (~1.5GB)
            self.model = WhisperModel(self.model_size, device="cpu",
                                      compute_type="int8")
            print("✅ Whisper готов! (будет определять язык автоматически)")
            self._ready.set()
            self._emit("ready", "распознавание готово")
        except Exception as exc:
            self._failed = True
            self.error = str(exc)
            self._ready.set()             # не заставляем recognize ждать вечно
            print("❌ Whisper не загрузился: %s" % exc)
            self._emit("error", "распознавание недоступно")

    def _ensure_model(self):
        """Модель, дождавшись загрузки. Вызывается из фонового потока."""
        if self._ready.is_set():
            return self.model
        if self._loading:
            self._ready.wait()
            return self.model
        # preload() не вызывали — грузим синхронно (как работало раньше)
        self._loading = True
        self._load()
        return self.model

    # -----------------------------------------------------
    # Подсказки и подготовка аудио
    # -----------------------------------------------------
    def _resolve_hotwords(self):
        """Строка-подсказка: сначала провайдер (всегда свежая), иначе config."""
        if self.hotwords_provider is not None:
            try:
                text = self.hotwords_provider()
            except Exception as exc:
                print("⚠️ STT: подсказка недоступна (%s)" % exc)
                text = None
            if text:
                return str(text)
        return self.hotwords

    @staticmethod
    def _trim_silence(audio, threshold):
        """Убрать тишину по краям: по пиковой амплитуде кадров по 20 мс.

        Возвращает срез аудио от первого до последнего «громкого» кадра.
        Если громких кадров нет — пустой массив (в записи одна тишина).
        """
        frame = max(1, int(SAMPLE_RATE * TRIM_FRAME_MS / 1000))
        usable = (audio.size // frame) * frame
        if usable == 0:
            return audio
        peaks = np.abs(audio[:usable].reshape(-1, frame)).max(axis=1)
        loud = np.nonzero(peaks >= threshold)[0]
        if loud.size == 0:
            return audio[:0]
        return audio[loud[0] * frame:(loud[-1] + 1) * frame]

    def _transcribe_options(self):
        """Параметры transcribe() из config — единая точка настройки скорости."""
        beam = int(getattr(config, "STT_BEAM_SIZE", 1) or 1)
        options = {
            "language": None,           # автоопределение языка
            "beam_size": beam,
            "best_of": max(1, beam),    # нужен только при подборе temp > 0
            "without_timestamps": bool(getattr(config, "STT_WITHOUT_TIMESTAMPS", True)),
            "condition_on_previous_text": bool(getattr(config, "STT_CONDITION_ON_PREVIOUS", False)),
        }
        if bool(getattr(config, "STT_USE_WHISPER_VAD", False)):
            options["vad_filter"] = True
        if self.initial_prompt:
            options["initial_prompt"] = self.initial_prompt
        hotwords = self._resolve_hotwords()
        if hotwords:
            options["hotwords"] = hotwords
        return options

    # -----------------------------------------------------
    # Распознавание
    # -----------------------------------------------------
    def recognize(self, audio_data):
        """
        Распознаёт аудио с автоопределением языка.
        Возвращает (текст, язык 'ru'/'en') или None.
        """
        print(f"🔍 Распознаём {len(audio_data)} байт")

        if len(audio_data) < 8000:
            print("❌ Слишком коротко")
            return None

        model = self._ensure_model()
        if model is None:
            print("❌ Распознавание недоступно (модель не загружена)")
            return None

        # Конвертируем байты в float32 для Whisper
        audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
        audio_float = audio_int16.astype(np.float32) / 32768.0

        # Обрезка тишины по краям: короче аудио → быстрее распознавание и
        # меньше «галлюцинаций» Whisper на пустом звуке.
        if bool(getattr(config, "STT_TRIM_SILENCE", True)):
            peak = max(1, int(getattr(config, "STT_SILENCE_PEAK", 200))) / 32768.0
            trimmed = self._trim_silence(audio_float, peak)
            if trimmed.size < SAMPLE_RATE * 0.2:      # после обрезки < 0.2 с речи
                print("❌ В записи только тишина/шум")
                return None
            removed = audio_float.size - trimmed.size
            if removed > 0:
                print("✂️ Обрезал тишину: %.1f с" % (removed / SAMPLE_RATE))
            audio_float = trimmed

        # language=None — автоопределение языка!
        segments, info = model.transcribe(audio_float, **self._transcribe_options())

        # ЯВНО ПЕЧАТАЕМ, ЧТО ОПРЕДЕЛИЛ WHISPER
        detected_lang = info.language
        print(f"🔍 Whisper определил язык: {detected_lang}")

        # Собираем текст из сегментов
        text = " ".join(seg.text for seg in segments).strip().lower()

        if text:
            print(f"✅ Распознано [{detected_lang}]: {text}")
            return text, detected_lang
        print("❌ Ничего не распознано")
        return None
