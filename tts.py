import asyncio
import os
import time
import pygame
import edge_tts
import re

# Голоса для разных языков
VOICE_EN = "en-US-JennyNeural"
VOICE_RU = "ru-RU-SvetlanaNeural"  # или ru-RU-DaryaNeural

EMOJI_PATTERN = re.compile("["
    u"\U0001F600-\U0001F64F"
    u"\U0001F300-\U0001F5FF"
    u"\U0001F680-\U0001F6FF"
    u"\U0001F700-\U0001F77F"
    u"\U0001F780-\U0001F7FF"
    u"\U0001F800-\U0001F8FF"
    u"\U0001F900-\U0001F9FF"
    u"\U0001FA00-\U0001FA6F"
    u"\U0001FA70-\U0001FAFF"
    u"\U00002702-\U000027B0"
    u"\U000024C2-\U0001F251"
    "]+", flags=re.UNICODE)

def remove_emojis(text):
    return EMOJI_PATTERN.sub('', text).strip()

def detect_language(text):
    """Определяет язык текста: 'ru' или 'en'"""
    russian_chars = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
    ru_count = sum(1 for c in text.lower() if c in russian_chars)
    en_count = sum(1 for c in text.lower() if c.isalpha() and c not in russian_chars)
    return "ru" if ru_count > en_count else "en"

def speak(text):
    if not text or not text.strip():
        return
    
    clean_text = remove_emojis(text)
    if not clean_text:
        return
    
    # Определяем язык
    lang = detect_language(clean_text)
    voice = VOICE_RU if lang == "ru" else VOICE_EN
    print(f"🔊 Озвучивание на языке: {'Русский' if lang == 'ru' else 'English'} ({voice})")
    
    async def _speak():
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save("response.mp3")
    
    try:
        asyncio.run(asyncio.wait_for(_speak(), timeout=10.0))
    except asyncio.TimeoutError:
        print("⚠️ TTS: таймаут скачивания")
        return
    except Exception as e:
        print(f"⚠️ TTS ошибка: {e}")
        return
    
    try:
        pygame.mixer.init()
        pygame.mixer.music.load("response.mp3")
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.quit()
        os.remove("response.mp3")
    except Exception as e:
        print(f"⚠️ TTS воспроизведение ошибка: {e}")