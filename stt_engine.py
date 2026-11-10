import os
import re
import threading
import time

import numpy as np
try:
    from scipy.io import wavfile
except Exception:                 # noqa: BLE001 — без scipy просто не сохраняем
    wavfile = None
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
        # Принудительный язык распознавания (None — определять самому).
        # Нужен в окне повторения слов: там ученик ВСЕГДА говорит по-английски,
        # и автоопределение на одном коротком слове ошибается (27.10.2026).
        self.language = None
        self.model = None
        # Английская речь распознаётся ОТДЕЛЬНОЙ моделью с жёстким языком
        # (замер 09.11.2026: base путал "canned food", small — нет).
        self.english_model_size = str(getattr(config, "STT_ENGLISH_MODEL", "") or "")
        self._english_model = None
        self._english_failed = False
        self._english_lock = threading.Lock()
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

    def set_language(self, language=None):
        """Задать язык распознавания жёстко ('en', 'ru') или сбросить (None).

        Нужно окну повторения слов: там ученик говорит ТОЛЬКО по-английски,
        а на одном коротком слове автоопределение языка ошибается.
        """
        self.language = str(language) if language else None

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
            if bool(getattr(config, "STT_WARM_ENGLISH", True)):
                # английскую модель грузим в фоне: иначе первая английская
                # реплика ждала бы ещё 2-3 с
                threading.Thread(target=self._ensure_english_model,
                                 daemon=True).start()
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

    def _ensure_english_model(self):
        """Модель для английской речи (по умолчанию small), лениво и один раз.
        
        Замер 09.11.2026: на живых записях ученика base с автоопределением 
        слышал "i eat and food" вместо "i eat canned food" и три раза решал,
        что речь немецкая; small с жёстким "en" дал верный текст.
        Ошибка загрузки не ломает приложение: работаем старой моделью.
        """
        if self._english_model is not None or self._english_failed:
            return self._english_model
        with self._english_lock:
            if self._english_model is not None or self._english_failed:
                return self._english_model
            size = self.english_model_size
            if not size or size == self.model_size:
                self._english_model = self.model      # та же модель — бесплатно
                return self._english_model
            try:
                started = time.time()
                self._english_model = WhisperModel(size, device="cpu",
                                                compute_type="int8")
                print("✅ Английская модель '%s' готова за %.1f с"
                      % (size, time.time() - started))
            except Exception as exc:                  # noqa: BLE001
                self._english_failed = True
                print("⚠️ Английская модель не загрузилась: %s" % exc)
        return self._english_model

    def _detect_language(self, model, audio):
        """Язык записи БЕЗ распознавания: (язык, уверенность).
        
        Стоит ~0,46 с (только энкодер). Нужен, чтобы решить, какой моделью
        распознавать: русская речь — быстрой base, остальная — английской.
        Не получилось — ("", 0.0), и тогда работает английский путь.
        """
        try:
            lang, prob, _all = model.detect_language(audio=audio)
            return str(lang or ""), float(prob or 0.0)
        except Exception as exc:                      # noqa: BLE001
            print("⚠️ Язык записи не определён: %s" % exc)
            return "", 0.0

    @staticmethod
    def _looks_broken(text):
        """Текст похож на мусор? (много слов из одной буквы или пусто)

        Живой случай 09.11.2026: модель с жёстким языком на непонятной речи
        выдаёт "R r Pi r S r r u NG r" — такие слова в речи не встречаются.
        """
        # 10.11.2026: порог 0,4 срабатывал на НОРМАЛЬНОЙ речи — в
        # «usually i pay a card» два коротких слова из пяти («i», «a»), и
        # запись уходила в русскую проверку. Там на английской речи модель
        # выдала «я же поймал картошку», и ученик получил бред вместо ответа.
        # Настоящий мусор («R r Pi r S r r u NG r») — это почти все слова
        # из одной буквы И ни одного нормального длинного слова.
        words = [w for w in re.split(r"[^\w']+", str(text or "")) if w]
        if not words:
            return True
        short = sum(1 for w in words if len(w) <= 1)
        if float(short) / len(words) < 0.5:
            return False
        return not any(len(w) >= 4 for w in words)

    def _rescue_russian(self, audio):
        """Резерв: проверить запись как РУССКУЮ базовой моделью.

        Зачем: язык определяется ДО распознавания, и если детектор ошибся,
        русская просьба («как сказать вилка по-английски») ушла бы в
        английскую модель и превратилась в мусор. Срабатывает только когда
        английский текст вышел подозрительным, и только если кириллицы в
        русском варианте действительно много.
        """
        try:
            segments, _info = self.model.transcribe(
                audio, **self._transcribe_options("ru"))
            text = " ".join(seg.text for seg in segments).strip().lower()
        except Exception as exc:                      # noqa: BLE001
            print("⚠️ Резервная проверка по-русски не удалась: %s" % exc)
            return None
        words = [w for w in re.split(r"[^\w']+", text) if w]
        cyr = [w for w in words if len(w) >= 3 and all("\u0400" <= ch <= "\u04ff"
                                                    for ch in w)]
        # 10.11.2026: двух русских слов мало — английская фраза иногда даёт
        # пару русских «слов» случайно. Нужно ТРИ и больше.
        if len(cyr) >= 3:
            print("🔁 Похоже, речь русская (русских слов: %d) — беру вариант"
                  " базовой модели" % len(cyr))
            return text, "ru"
        return None

    def _pick_model_and_language(self, audio):
        """Какая модель и какой язык пойдут в transcribe() (и почему).
        
        * язык задан жёстко (set_language) — уважаем его;
        * иначе он определяется дёшево: русский — base как есть, а всё
          остальное считается английским и идёт в английскую модель.
        Возвращает (модель, язык, причина) — причину печатаем в лог.
        """
        base_model = self.model
        forced = self.language
        if forced:
            lang = str(forced).lower()
            if lang.startswith("ru"):
                return base_model, "ru", "язык задан: ru"
            english = self._ensure_english_model() or base_model
            return (english, lang,
                    "язык задан: %s, модель '%s'"
                    % (lang, self.english_model_size or self.model_size))
        detected, prob = self._detect_language(base_model, audio)
        if detected.startswith("ru"):
            return (base_model, "ru",
                    "речь русская (p=%.2f) — модель '%s'"
                    % (prob, self.model_size))
        english = self._ensure_english_model() or base_model
        lang = str(getattr(config, "STT_ENGLISH_LANGUAGE", "en") or "en")
        return (english, lang,
                "речь не русская (%s, p=%.2f) — модель '%s'"
                % (detected or "?", prob, self.english_model_size or self.model_size))

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


    def _save_audio(self, audio_data) -> None:
        """Сохранить запись в logs/stt/ для разбора (см. config.STT_SAVE_AUDIO).

        Нужно, чтобы спорные распознавания проверялись на РЕАЛЬНОМ звуке:
        сравнить две модели на синтезированной речи мало что даёт.
        Ошибку сохранения глушим: диагностика не должна ломать урок.
        """
        try:
            if not getattr(config, "STT_SAVE_AUDIO", False):
                return
            folder = getattr(config, "LOGS_DIR", "logs")
            path = os.path.join(folder, "stt")
            os.makedirs(path, exist_ok=True)
            name = time.strftime("%Y%m%d_%H%M%S") + ".wav"
            if wavfile is not None:
                wavfile.write(os.path.join(path, name), SAMPLE_RATE,
                              np.frombuffer(audio_data, dtype=np.int16))
            keep = max(1, int(getattr(config, "STT_AUDIO_KEEP", 8) or 8))
            files = sorted(f for f in os.listdir(path) if f.endswith(".wav"))
            for old in files[:-keep]:
                os.remove(os.path.join(path, old))
        except Exception as exc:                 # noqa: BLE001
            print("⚠️ Запись для разбора не сохранена: %s" % exc)

    def _transcribe_options(self, language=None):
        """Параметры transcribe() из config — единая точка настройки скорости.
        
        language: None — не задавать (автоопределение); иначе жёсткий язык.
        """
        beam = int(getattr(config, "STT_BEAM_SIZE", 1) or 1)
        options = {
            "language": language or self.language,
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
        Распознаёт аудио и возвращает (текст, язык 'ru'/'en') или None.

        Язык больше НЕ всегда автоопределение: он определяется дёшево, а текст
        пишет та модель, что слышит этот язык лучше (09.11.2026).
        """
        print(f"🔍 Распознаём {len(audio_data)} байт")
        self._save_audio(audio_data)

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

        # Какой моделью и на каком языке распознавать: русская речь — быстрой
        # base, остальная — английской моделью с жёстким "en" (09.11.2026).
        run_model, language, why = self._pick_model_and_language(audio_float)
        print("🔍 Распознаю: %s" % why)
        segments, info = run_model.transcribe(
            audio_float, **self._transcribe_options(language))

        detected_lang = language or info.language

        # Собираем текст из сегментов
        text = " ".join(seg.text for seg in segments).strip().lower()

        # Страховка: английский вариант получился мусором — возможно, речь
        # русская, а детектор языка ошибся (09.11.2026).
        if text and detected_lang == "en" and self._looks_broken(text):
            rescued = self._rescue_russian(audio_float)
            if rescued:
                text, detected_lang = rescued
            else:
                print("ℹ️ Страховка по-русски не сработала — остаётся: %r" % text)

        if text:
            print(f"✅ Распознано [{detected_lang}]: {text}")
            return text, detected_lang
        print("❌ Ничего не распознано")
        return None
