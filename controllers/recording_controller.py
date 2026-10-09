# -*- coding: utf-8 -*-
# =========================================================
# RECORDING_CONTROLLER.PY — запись с микрофона и распознавание
# =========================================================
# Что переехало из gui.py: toggle_recording, on_recording_stopped,
# _on_recording_main, _recognize_worker, _after_recognition.
#
# Главная тонкость, ради которой это отдельный класс:
# VAD зовёт колбэк из СВОЕГО потока, а Tk-виджеты можно трогать только
# из главного. Поэтому здесь есть dispatch, и наружу (в GUI) ничего
# не уходит напрямую из чужого потока.
# =========================================================

import threading

# Минимальная длина фразы в байтах (16 кГц, int16): 0.25 с
MIN_AUDIO_BYTES = 8000


class RecordingController:
    def __init__(self, vad, stt, dispatch=None, on_status=None,
                 on_recording_changed=None, on_recognized=None):
        self.vad = vad
        self.stt = stt
        self._dispatch = dispatch or (lambda fn: fn())
        self.on_status = on_status                    # (text, color_key)
        self.on_recording_changed = on_recording_changed  # (bool)
        self.on_recognized = on_recognized            # (text, lang)
        self.is_recording = False

    # -----------------------------------------------------
    # Публичный интерфейс
    # -----------------------------------------------------
    def toggle(self):
        if self.is_recording:
            self.stop()
        else:
            self.start()

    def start(self):
        """Начало записи (в режиме удержания — пока кнопка нажата).

        Останавливает запись не по тишине, а явный stop() (отпускание кнопки)
        либо страховочный предел времени в audio_vad._monitor.
        """
        if self.is_recording:
            return
        self.is_recording = True
        self._emit(self.on_recording_changed, True)
        self._emit(self.on_status, "● Слушаю… отпусти кнопку — отправить", "warn")
        try:
            self.vad.set_stop_callback(self._on_vad_stopped)
            self.vad.start_recording()
        except Exception as exc:
            self.is_recording = False
            self._emit(self.on_recording_changed, False)
            self._emit(self.on_status, "● Микрофон недоступен", "err")
            print(f"❌ Не удалось начать запись: {exc}")

    def stop(self):
        try:
            self.vad.stop_recording()
        except Exception as exc:
            print(f"⚠️ Ошибка остановки записи: {exc}")

    # -----------------------------------------------------
    # Колбэк из потока VAD
    # -----------------------------------------------------
    def _on_vad_stopped(self, audio_data):
        self._dispatch(lambda: self._handle_audio(audio_data))

    def _handle_audio(self, audio_data):
        """Главный поток: обновляем интерфейс и уходим в фон за распознаванием."""
        self.is_recording = False
        self._emit(self.on_recording_changed, False)

        if len(audio_data) <= MIN_AUDIO_BYTES:
            self._emit(self.on_status, "● Слишком коротко", "err")
            return

        self._emit(self.on_status, "● Распознаю...", "warn")
        threading.Thread(target=self._recognize_worker, args=(audio_data,), daemon=True).start()

    def _recognize_worker(self, audio_data):
        """Фон: Whisper не должен подвешивать окно."""
        try:
            result = self.stt.recognize(audio_data)
        except Exception as exc:
            print(f"❌ Ошибка распознавания: {exc}")
            result = None
        self._dispatch(lambda: self._after_recognition(result))

    def _after_recognition(self, result):
        """Главный поток: отдаём распознанный текст в приложение."""
        if not result:
            self._emit(self.on_status, "● Не распознано", "err")
            return
        text, detected_lang = result
        self._emit(self.on_recognized, text, detected_lang)

    # -----------------------------------------------------
    @staticmethod
    def _emit(callback, *args):
        if callback is None:
            return
        try:
            callback(*args)
        except Exception as exc:
            print(f"⚠️ Ошибка в колбэке записи: {exc}")
