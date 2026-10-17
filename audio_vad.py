import sounddevice as sd
import numpy as np
import time
import threading

class AudioVAD:
    def __init__(self, silence_limit=1.0, max_seconds=45.0, stop_on_silence=False):
        self.sample_rate = 16000
        self.is_recording = False
        self.stream = None
        self.current_audio = b""
        self.silence_counter = 0
        self.silence_limit = silence_limit
        # Режим «держать кнопку» (push-to-talk): по умолчанию НЕ режем запись
        # по тишине — ученику нужно время подумать, иначе фраза обрывается на
        # паузе. Страховка от «залипшей» кнопки — жёсткий предел длительности.
        self.stop_on_silence = stop_on_silence
        self.max_seconds = max_seconds
        self._start_time = None
        self.stop_callback = None
        # уровень громкости микрофона 0..100 (для эквалайзера и губ робота).
        # Пишется из аудио-потока, читается из главного — гонки безобидны.
        self.level = 0.0
        self.level_at = 0.0
        self.level_stale = 0.25

    def set_stop_callback(self, callback):
        self.stop_callback = callback

    def get_level(self):
        """Текущая громкость микрофона 0..100 (0.0, если давно тишина)."""
        import time as _time
        if _time.monotonic() - self.level_at > self.level_stale:
            return 0.0
        return self.level

    def has_input_device(self):
        """Есть ли в системе устройство ВВОДА звука (микрофон).

        Нужно ЗАРАНЕЕ, чтобы урок «говорение» не начинался там, где говорить
        физически нечем. Исключения не пробрасываем: нет ответа — считаем,
        что микрофон недоступен (лучше честно сказать ученику).
        """
        try:
            import sounddevice as sd
            devices = sd.query_devices()
        except Exception as exc:
            print(f"⚠️ Микрофон: не удалось опросить устройства ({exc})")
            return False
        try:
            for d in devices:
                if int(d.get("max_input_channels", 0)) > 0:
                    return True
        except Exception:
            return False
        return False

    def _find_input_device(self):
        """Находит первый доступный входной микрофон"""
        try:
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                if d['max_input_channels'] > 0:
                    return i
        except Exception:
            pass
        return None  # None = устройство по умолчанию

    def start_recording(self):
        if self.is_recording:
            return
        self.is_recording = True
        self.current_audio = b""
        self.silence_counter = 0
        self._start_time = time.time()
        self.level = 0.0
        device = self._find_input_device()
        self.stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=4000,
            dtype='int16',
            channels=1,
            device=device,
            callback=self._audio_callback
        )
        self.stream.start()
        print(f"🎤 Запись начата (микрофон: {device})")
        threading.Thread(target=self._monitor, daemon=True).start()

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        self.level = 0.0
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        print(f"🎤 Запись остановлена, собрано {len(self.current_audio)} байт")
        if self.stop_callback:
            self.stop_callback(self.current_audio)

    def _monitor(self):
        """Следит за длительностью записи (в фоне).

        В режиме «держать кнопку» тишину игнорируем (пауза = раздумье), но
        держим жёсткий предел: если кнопка «залипла», запись остановится сама.
        Прежнее поведение (стоп по тишине) включается флагом stop_on_silence.
        """
        while self.is_recording:
            time.sleep(0.1)
            if (self.max_seconds and self._start_time is not None
                    and (time.time() - self._start_time) >= self.max_seconds):
                print(f"⏱ Предел записи ({self.max_seconds:.0f} с) — останавливаю")
                self.stop_recording()
                break
            if self.stop_on_silence and self.silence_counter >= self.silence_limit:
                print(f"🔇 Тишина {self.silence_limit} сек, останавливаю запись")
                self.stop_recording()
                break

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f"Ошибка микрофона: {status}")
        if self.is_recording:
            self.current_audio += bytes(indata)
            audio_array = np.frombuffer(bytes(indata), dtype=np.int16)
            volume = np.abs(audio_array).mean()
            # тот же масштаб, что у озвучки: речь ~1500..4000 → 37..100
            self.level = max(0.0, min(100.0, float(volume) / 40.0))
            self.level_at = time.monotonic()
            if volume > 100:
                self.silence_counter = 0
            else:
                self.silence_counter += frames / self.sample_rate