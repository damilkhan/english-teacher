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

# ---------- реестр моделей ----------
# llama.cpp-сервер может запускаться с ЛЮБОЙ моделью из этого списка: выбор
# хранится в settings.json (settings_store), а запускает нужную server_manager.
# Поля записи:
#   id         — ключ (хранится в настройках);
#   label      — подпись в интерфейсе;
#   path       — путь к .gguf;
#   ctx        — размер контекста (-c), по умолчанию SERVER_CONTEXT;
#   mmproj     — опциональный проектор (мультимодальность), или None;
#   extra_args — дополнительные флаги llama-server;
#   max_tokens / temperature / stop — переопределения генерации чата
#              (None → общие LLM_CHAT_MAX_TOKENS / LLM_TEMPERATURE / LLM_STOP_WORDS);
#   note       — короткая подсказка для UI.
#
# Модели с недоступным файлом в списке остаются, но в UI не показываются
# (см. available_models) — так удобно держать «примеры» для будущих моделей.
MODELS = [
    {
        "id": "gemma4-e4b",
        "label": "Gemma-4-E4B (Q4_K_M)",
        "path": os.path.join(BASE_DIR, "models", "gemma",
                             "Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"),
        "ctx": 4096,
        "mmproj": None,
        "extra_args": [],
        "max_tokens": None,
        "temperature": None,
        "stop": None,
        "note": "по умолчанию; загрузка ~30 с",
    },
    {
        "id": "example-qwen2.5-7b",
        "label": "Qwen2.5-7B-Instruct (пример)",
        "path": os.path.join(BASE_DIR, "models", "qwen2.5-7b-instruct-q4_k_m.gguf"),
        "ctx": 8192,
        "mmproj": None,
        "extra_args": [],
        "max_tokens": None,
        "temperature": None,
        "stop": None,
        "note": "пример: положите GGUF в models/ и перезапустите",
    },
]
DEFAULT_MODEL_ID = "gemma4-e4b"

# ---------- авто-обнаружение моделей ----------
# Дополнительно к ручному списку MODELS можно сканировать папку на *.gguf
# (model_registry): модель подхватится без правки config.py.
AUTO_DISCOVER_MODELS = True
MODELS_DIR = os.path.join(BASE_DIR, "models")
# КОНСЕРВАТИВНЫЙ контекст для авто-найденных моделей: даже если модель умеет
# 128k, по умолчанию даём немного — иначе легко вылететь по памяти. Точное
# значение задаётся вручную (ручная запись в MODELS или overrides в настройках).
AUTO_CTX = 4096

# MODEL_PATH сохранён как «путь модели по умолчанию» (обратная совместимость).
MODEL_PATH = next((m["path"] for m in MODELS if m["id"] == DEFAULT_MODEL_ID),
                  MODELS[0]["path"] if MODELS else "")


def get_model(model_id=None):
    """Запись модели по id. Неизвестный/пустой id → модель по умолчанию."""
    mid = model_id or DEFAULT_MODEL_ID
    for model in MODELS:
        if model.get("id") == mid:
            return dict(model)
    return dict(MODELS[0]) if MODELS else {}


def available_models():
    """Модели, чей файл реально есть на диске (их и показываем в UI)."""
    return [dict(m) for m in MODELS if m.get("path") and os.path.exists(m["path"])]


def model_is_available(model_id):
    """Есть ли у модели id файл на диске."""
    model = get_model(model_id)
    return bool(model) and os.path.exists(model.get("path", ""))



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

# Лимит токенов на ОТВЕТ в чате. У Gemma бывает «канал размышлений»
# (<|channel>thought …), и при маленьком лимите модель тратит все токены
# на «размышления», не успевая ответить ученику (раньше было 120 — не хватало).
LLM_CHAT_MAX_TOKENS = 400

# ---------- запуск llama-server ----------
SERVER_EXE_PATH = r"D:\llama.cpp\llama-server.exe"
SERVER_CONTEXT = 4096          # -c
SERVER_STARTUP_TIMEOUT = 240   # сколько секунд ждём загрузку модели (реально ~30 с)

# ---------- распознавание речи (STT, faster-whisper) ----------
# Модель распознавания. Замеры на этой машине (CPU, int8), примерно:
#   base   ~10x быстрее реального времени, но хуже слышит имена/редкие слова;
#   small  ~3.4x быстрее, заметно точнее (особенно русский и смешанная речь);
#   medium ~1x (на CPU уже тормозит — брать при работе на GPU / в облаке).
STT_MODEL_SIZE = "small"

# ---------- база знаний (RAG) ----------
# Подключать ли методические заметки (knowledge_base/) в промпт Учителя.
# RAG локальный и дешёвый (без LLM), но его легко выключить одной строкой.
RAG_ENABLED = True
RAG_TOP_K = 2

# ---------- делегирование ролей (Учитель / Аналитик / Планировщик) ----------
# Аналитик разбирает реплики ученика в режиме урока (второй вызов LLM).
ANALYST_ENABLED = True
PLANNER_ENABLED = False        # Планировщик пока не реализован


def check_paths():
    """Проверяет, что на месте всё, без чего приложение не заработает.

    Обязателен только llama-server.exe; моделей достаточно ОДНОЙ доступной.
    (Раньше требовалась одна конкретная модель — из-за этого падал запуск,
    если выбрана другая или модель ещё не скачана.)
    """
    all_exist = True
    if not os.path.exists(SERVER_EXE_PATH):
        print(f"⚠️ Не найдено: {SERVER_EXE_PATH}")
        all_exist = False
    # Доступность моделей спрашиваем у РЕЕСТРА (ручные + авто-найденные).
    try:
        import model_registry
        models = model_registry.available_models()
    except Exception:
        models = available_models()
    if not models:
        print("⚠️ Не найдено ни одной доступной модели (MODELS или models/)")
        print(f"   папка автопоиска: {MODELS_DIR}")
        all_exist = False
    return all_exist
