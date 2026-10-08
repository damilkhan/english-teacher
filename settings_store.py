# -*- coding: utf-8 -*-
# =========================================================
# SETTINGS_STORE.PY — настройки приложения (сейчас: выбранная модель)
# =========================================================
# Маленькое надёжное хранилище настроек в settings.json (рядом с config.py).
# Файл НЕ обязателен: нет/битый → берём значения по умолчанию, не падаем.
# Читается ОДИН раз при старте сервера — до появления окна, поэтому модуль
# не зависит ни от tkinter, ни от ролей.
# =========================================================

import json
import os

import config

SETTINGS_PATH = os.path.join(config.BASE_DIR, "settings.json")

DEFAULTS = {
    "model_id": config.DEFAULT_MODEL_ID,
}


def load():
    """Все настройки словарём. Нет/битый файл → {} (кладём дефолты ниже)."""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, ValueError, OSError):
        pass
    return {}


def save(data):
    """Полностью перезаписывает настройки. True при успехе."""
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(data if isinstance(data, dict) else {}, fh,
                      indent=4, ensure_ascii=False)
        return True
    except OSError as exc:
        print(f"⚠️ Не удалось сохранить настройки: {exc}")
        return False


def get(key, default=None):
    value = load().get(key)
    if value is None:
        return DEFAULTS.get(key, default)
    return value


def set_value(key, value):
    """Меняет один ключ, остальные сохраняет."""
    data = load()
    data[key] = value
    return save(data)


def get_overrides():
    """Ручные переопределения записей моделей: {model_id: {ctx, extra_args, ...}}."""
    data = load().get("model_overrides")
    return data if isinstance(data, dict) else {}


def set_override(model_id, patch):
    """Переопределить поля модели (ctx/mmproj/extra_args/...). None-поля стирают."""
    data = load()
    overrides = data.get("model_overrides")
    if not isinstance(overrides, dict):
        overrides = {}
    if patch is None:
        overrides.pop(model_id, None)
    else:
        overrides[model_id] = dict(patch)
    data["model_overrides"] = overrides
    return save(data)


def get_selected_model_id():
    """id выбранной модели. Недоступную заменяем на доступную/дефолт."""
    model_id = load().get("model_id") or config.DEFAULT_MODEL_ID
    # доступность спрашиваем у РЕЕСТРА (учитывает авто-найденные), с откатом
    # на ручной список, если реестр недоступен (например, в ранних тестах)
    try:
        import model_registry
        if model_registry.model_is_available(model_id):
            return model_id
        available = model_registry.available_models()
        if available:
            return available[0]["id"]
        return model_id
    except Exception:
        if config.model_is_available(model_id):
            return model_id
        available = config.available_models()
        if available:
            return available[0]["id"]
        return model_id


def set_selected_model(model_id):
    return set_value("model_id", model_id)
