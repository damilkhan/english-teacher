import threading

import numpy as np
from faster_whisper import WhisperModel

import config


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
    """

    def __init__(self, model_size=None, on_state=None):
        # модель берём из config (STT_MODEL_SIZE); явный аргумент перекрывает
        self.model_size = model_size or getattr(config, "STT_MODEL_SIZE", "base")
        self.on_state = on_state
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

        # language=None — автоопределение языка!
        segments, info = model.transcribe(audio_float, language=None)

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
