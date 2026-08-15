import sounddevice as sd
import numpy as np
import queue
import json
import sys
import os

# Добавь путь к модели Vosk (проверь, что путь правильный)
from vosk import Model, KaldiRecognizer

# Путь к английской модели
MODEL_PATH = r"D:\EnglishTeacher\models\vosk-en\vosk-model-small-en-us-0.15"

if not os.path.exists(MODEL_PATH):
    print(f"Ошибка: модель не найдена в {MODEL_PATH}")
    sys.exit(1)

print("Загрузка модели Vosk...")
model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, 16000)
print("Модель загружена!")

# Настройки записи
SAMPLE_RATE = 16000
BLOCK_SIZE = 4000
audio_queue = queue.Queue()

def audio_callback(indata, frames, time, status):
    if status:
        print(f"Ошибка: {status}")
    audio_queue.put(bytes(indata))

print("Говорите в микрофон... (Ctrl+C для выхода)")

try:
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                           dtype='int16', channels=1, callback=audio_callback):
        
        accumulated = b""
        silence_counter = 0
        
        while True:
            try:
                data = audio_queue.get(timeout=0.5)
                accumulated += data
                
                # Простая проверка громкости
                audio_array = np.frombuffer(data, dtype=np.int16)
                volume = np.abs(audio_array).mean()
                
                if volume > 100:
                    silence_counter = 0
                    print(f"🎤 Громкость: {volume:.0f} - говорю...")
                else:
                    silence_counter += 1
                
                # Если тишина > 1.5 секунд (примерно 24 блока) и есть что распознавать
                if silence_counter > 24 and len(accumulated) > 8000:
                    print(f"Распознаю фразу длиной {len(accumulated)} байт...")
                    if recognizer.AcceptWaveform(accumulated):
                        result = json.loads(recognizer.Result())
                        text = result.get('text', '')
                        if text:
                            print(f"✅ РАСПОЗНАНО: {text}")
                        else:
                            print("❌ Ничего не распознано (пустой результат)")
                    else:
                        print("❌ Фраза не принята")
                    
                    accumulated = b""
                    silence_counter = 0
                    
            except queue.Empty:
                pass
                
except KeyboardInterrupt:
    print("\nВыход")