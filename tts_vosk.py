import os
import time
import pygame
from vosk_tts import Model, Synth

MODEL_PATH = r"D:\EnglishTeacher\models\vosk-model-tts-ru-0.9-multi"
VOICE_ID = 2  # F02 (Natasha from Sova) — звучит моложе и естественнее

_tts_model = None
_tts_synth = None

def get_synth():
    global _tts_model, _tts_synth
    if _tts_synth is None:
        print("⏳ Загрузка Vosk TTS...")
        _tts_model = Model(model_name=MODEL_PATH)
        _tts_synth = Synth(_tts_model)
        print("✅ Vosk TTS загружен!")
    return _tts_synth

def speak(text):
    if not text or not text.strip():
        return
    
    # Проверяем, русский ли текст
    russian_chars = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
    if not any(c in russian_chars for c in text.lower()):
        # Если текст на английском — используем старый tts.py
        import tts
        tts.speak(text)
        return
    
    print(f"🔊 Озвучивание голосом Vosk (F02)...")
    
    synth = get_synth()
    temp_file = "response_vosk.wav"
    
    try:
        synth.synth(text, temp_file, speaker_id=VOICE_ID)
    except Exception as e:
        print(f"⚠️ Ошибка синтеза Vosk: {e}")
        return
    
    if not os.path.exists(temp_file):
        print("⚠️ Файл не создан")
        return
    
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
        pygame.mixer.music.load(temp_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.quit()
    except Exception as e:
        print(f"⚠️ Ошибка воспроизведения: {e}")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)