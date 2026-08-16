import sounddevice as sd
import numpy as np
import time
import threading

class AudioVAD:
    def __init__(self):
        self.sample_rate = 16000
        self.is_recording = False
        self.stream = None
        self.current_audio = b""
        self.silence_counter = 0
        self.silence_limit = 1.0
        self.stop_callback = None

    def set_stop_callback(self, callback):
        self.stop_callback = callback

    def start_recording(self):
        if self.is_recording:
            return
        self.is_recording = True
        self.current_audio = b""
        self.silence_counter = 0
        self.stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=4000,
            dtype='int16',
            channels=1,
            callback=self._audio_callback
        )
        self.stream.start()
        print("🎤 Запись начата")
        threading.Thread(target=self._monitor_silence, daemon=True).start()

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        print(f"🎤 Запись остановлена, собрано {len(self.current_audio)} байт")
        if self.stop_callback:
            self.stop_callback(self.current_audio)

    def get_audio(self):
        audio = self.current_audio
        self.current_audio = b""
        return audio

    def _monitor_silence(self):
        while self.is_recording:
            time.sleep(0.1)
            if self.silence_counter >= self.silence_limit:
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
            if volume > 100:
                self.silence_counter = 0
            else:
                self.silence_counter += frames / self.sample_rate