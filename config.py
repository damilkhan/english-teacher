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

# =========================================================
# Локальный LLM-сервер (llama.cpp) — ЕДИНЫЙ источник правды
# =========================================================
# Раньше адрес и порт были прописаны литералами в 4 файлах.
# Теперь меняем в одном месте.
LLM_HOST = "127.0.0.1"
LLM_PORT = 8080
LLM_BASE_URL = "http://%s:%d" % (LLM_HOST, LLM_PORT)
LLM_SERVER_URL = LLM_BASE_URL + "/completion"   # сюда шлём промпты
LLM_HEALTH_URL = LLM_BASE_URL + "/health"       # здесь проверяем готовность

# Значения по умолчанию для интерфейса
DEFAULT_MODE = "lesson"    # "lesson" (урок) | "free" (свободное общение)
DEFAULT_THEME = "dark"     # "dark" | "light"
DEFAULT_LANGUAGE = "en"    # язык ответа до первой реплики

# Настройки LLM
LLM_MAX_TOKENS = 200
LLM_TEMPERATURE = 0.7
LLM_STOP_WORDS = ["Student:", "\n\n"]

# =========================================================
# llama-server
# =========================================================
SERVER_EXE_PATH = r"D:\llama.cpp\llama-server.exe"
SERVER_CONTEXT = 4096          # -c
SERVER_STARTUP_TIMEOUT = 240   # сколько секунд ждём загрузку модели (реально ~30 с)


def check_paths():
    """Проверяет, что все необходимые файлы существуют"""
    paths_to_check = [RUSSIAN_MODEL_PATH, ENGLISH_MODEL_PATH, MODEL_PATH]
    all_exist = True
    for path in paths_to_check:
        if not os.path.exists(path):
            print(f"⚠️ Файл не найден: {path}")
            all_exist = False
    return all_exist
