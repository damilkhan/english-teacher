import numpy as np
from faster_whisper import WhisperModel

class STTEngine:
    def __init__(self):
        print("⏳ Загрузка Whisper (автоопределение языка)...")
        # model_size: tiny (~75MB), base (~150MB), small (~500MB)
        self.model = WhisperModel("base", device="cpu", compute_type="int8")
        print("✅ Whisper готов! (будет определять язык автоматически)")

    def recognize(self, audio_data):
        """
        Распознаёт аудио с автоопределением языка
        Возвращает текст и язык ('ru' или 'en')
        """
        print(f"🔍 Распознаём {len(audio_data)} байт")
        
        if len(audio_data) < 8000:
            print("❌ Слишком коротко")
            return None
        
        # Конвертируем байты в float32 для Whisper
        audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
        audio_float = audio_int16.astype(np.float32) / 32768.0
        
        # language=None — автоопределение языка!
        segments, info = self.model.transcribe(audio_float, language=None)
        
        # ЯВНО ПЕЧАТАЕМ, ЧТО ОПРЕДЕЛИЛ WHISPER
        detected_lang = info.language
        print(f"🔍 Whisper определил язык: {detected_lang}")
        
        # Собираем текст из сегментов
        text = " ".join(seg.text for seg in segments).strip().lower()
        
        if text:
            print(f"✅ Распознано [{detected_lang}]: {text}")
            return text, detected_lang
        else:
            print("❌ Ничего не распознано")
            return None