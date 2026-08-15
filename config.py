import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Пути к моделям Vosk (для распознавания речи)
RUSSIAN_MODEL_PATH = os.path.join(BASE_DIR, "models", "vosk-ru", "vosk-model-small-ru-0.22")
ENGLISH_MODEL_PATH = os.path.join(BASE_DIR, "models", "vosk-en", "vosk-model-small-en-us-0.15")

# Путь к основной модели Gemma 4 E4B (новая, без цензуры)
MODEL_PATH = os.path.join(BASE_DIR, "models", "gemma", "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf")

# Путь к файлу-проектору для мультимодальности (изображения, аудио)
# Если он у тебя есть — раскомментируй и укажи путь
# MMPROJ_PATH = os.path.join(BASE_DIR, "models", "gemma", "mmproj-Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-f16.gguf")

# Настройки микрофона
SAMPLE_RATE = 16000
BLOCK_SIZE = 4000
SILENCE_THRESHOLD = 30
SILENCE_TIMEOUT = 1.2
MIN_PHRASE_DURATION = 0.5

# Настройки LLM
LLM_SERVER_URL = "http://127.0.0.1:8080/completion"
LLM_MAX_TOKENS = 200
LLM_TEMPERATURE = 0.7
LLM_STOP_WORDS = ["Student:", "\n\n"]

def check_paths():
    """Проверяет, что все необходимые файлы существуют"""
    paths_to_check = [RUSSIAN_MODEL_PATH, ENGLISH_MODEL_PATH, MODEL_PATH]
    all_exist = True
    for path in paths_to_check:
        if not os.path.exists(path):
            print(f"⚠️ Файл не найден: {path}")
            all_exist = False
    return all_exist