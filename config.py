# -*- coding: utf-8 -*-
# =========================================================
# CONFIG.PY — общие настройки приложения
# =========================================================
# Здесь только то, что действительно используется кодом.
# (Убраны пути к моделям Vosk и настройки микрофона: распознавание идёт
#  через faster-whisper, а Vosk в проекте больше не задействован.)
# =========================================================

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------- модель ----------
# Основная модель Gemma 4 E4B (без цензуры)
MODEL_PATH = os.path.join(
    BASE_DIR, "models", "gemma",
    "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf",
)

# Файл-проектор для мультимодальности (изображения/аудио).
# Если он у тебя есть и понадобится — раскомментируй и добавь в запуск сервера.
# MMPROJ_PATH = os.path.join(
#     BASE_DIR, "models", "gemma",
#     "mmproj-Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-f16.gguf",
# )

# ---------- значения по умолчанию для интерфейса ----------
DEFAULT_MODE = "lesson"      # "lesson" (урок) | "free" (свободное общение)
DEFAULT_THEME = "dark"       # "dark" | "light"
DEFAULT_LANGUAGE = "en"      # язык ответа до первой реплики

# ---------- локальный LLM-сервер (llama.cpp) ----------
LLM_HOST = "127.0.0.1"
LLM_PORT = 8080
LLM_BASE_URL = "http://%s:%d" % (LLM_HOST, LLM_PORT)
LLM_SERVER_URL = LLM_BASE_URL + "/completion"   # сюда шлём промпты
LLM_HEALTH_URL = LLM_BASE_URL + "/health"       # здесь проверяем готовность

LLM_MAX_TOKENS = 200
LLM_TEMPERATURE = 0.7
LLM_STOP_WORDS = ["Student:", "\n\n"]

# ---------- запуск llama-server ----------
SERVER_EXE_PATH = r"D:\llama.cpp\llama-server.exe"
SERVER_CONTEXT = 4096          # -c
SERVER_STARTUP_TIMEOUT = 240   # сколько секунд ждём загрузку модели (реально ~30 с)


def check_paths():
    """Проверяет, что на месте всё, без чего приложение не заработает.

    Раньше здесь проверялись модели Vosk — их в проекте уже нет,
    а из-за этой проверки запуск падал с «не найдены модели» ни за что.
    """
    required = [MODEL_PATH, SERVER_EXE_PATH]
    all_exist = True
    for path in required:
        if not os.path.exists(path):
            print(f"⚠️ Не найдено: {path}")
            all_exist = False
    return all_exist
