# =========================================================
# MAIN.PY — Точка входа в приложение
# =========================================================

import warnings
import time
import sys
import config
import requests

# Фикс кодировки консоли Windows (для корректного вывода эмодзи)
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Наши модули
from tts import speak
from llm_client import LLMClient
from profile_manager import ProfileManager
from audio_vad import AudioVAD
from stt_engine import STTEngine
import server_manager

warnings.filterwarnings("ignore")

def main():
    print("\n" + "=" * 50)
    print("🤖 ИИ-ПРЕПОДАВАТЕЛЬ АНГЛИЙСКОГО")
    print("=" * 50)
    
    # 1. Проверяем наличие файлов
    if not config.check_paths():
        print("❌ Ошибка: Не найдены необходимые файлы. Проверьте config.py")
        sys.exit(1)
    
    # 2. Запускаем сервер llama.cpp
    server_manager.start_server()
    
    # 3. Проверяем, что сервер работает
    llm = LLMClient()
    if not server_manager.wait_for_server(timeout=30):
        print("❌ Ошибка: Сервер llama.cpp не запустился!")
        server_manager.stop_server()
        sys.exit(1)
    print("✅ Сервер готов!")
    
    # 4. Создаём менеджер режимов (с функцией голосового приветствия)
    profile = ProfileManager(speak_callback=speak)
    
    # 5. Запускаем VAD (голосовую активность)
    vad = AudioVAD()
    vad.start()
    
    # 6. Инициализируем распознавание речи
    stt = STTEngine()
    
    print("\n🎤 Говори в микрофон.")
    print("   Скажи «перерыв» → режим ДРУГ")
    print("   Скажи «урок» → режим УЧИТЕЛЬ")
    print("   Для выхода Ctrl+C.\n")
    
    try:
        while True:
            # Ждём готовую фразу от VAD
            audio_data = vad.get_phrase()
            
            if audio_data:
                # Распознаём текст (возвращает кортеж: текст, язык)
                result = stt.recognize(audio_data)
                
                if not result:
                    continue
                
                recognized_text, detected_lang = result
                
                print(f"\n🎤 Вы: {recognized_text}")
                
                # Проверяем команды переключения режимов
                if recognized_text in ["перерыв", "отдохнем", "друг"]:
                    profile.switch_to_friend()
                    continue
                elif recognized_text in ["урок", "заниматься", "учитель"]:
                    profile.switch_to_teacher()
                    continue
                
                # Формируем промпт с историей
                prompt = profile.format_prompt(recognized_text)
                print("🤔 Джейн думает...")
                
                # Получаем ответ от LLM
                response = llm.generate_response(prompt)
                
                if response:
                    print(f"👩‍🏫 Джейн: {response}")
                    profile.add_exchange(recognized_text, response)
                    speak(response)  # Озвучиваем ответ
                else:
                    print("❌ Не удалось получить ответ от модели")
                    
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"❌ Непредвиденная ошибка: {e}")
    finally:
        vad.stop()
        server_manager.stop_server()

if __name__ == "__main__":
    main()