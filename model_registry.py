# -*- coding: utf-8 -*-
# =========================================================
# MODEL_REGISTRY.PY — единый реестр моделей (ручной + авто-найденный)
# =========================================================
# Собирает модели из ДВУХ источников:
#   1) ручной список config.MODELS (там можно точно задать ctx/mmproj/флаги);
#   2) авто-обнаружение: скан config.MODELS_DIR на *.gguf + чтение заголовка
#      GGUF (gguf_meta) — так модель подхватывается без правки config.py.
#
# Правила:
#   * при конфликте (один и тот же путь) выигрывает РУЧНАЯ запись;
#   * для авто-моделей ctx КОНСЕРВАТИВНЫЙ: min(обучающий ctx, config.AUTO_CTX),
#     чтобы не вылетать по памяти — точное значение задаётся вручную;
#   * ручные overrides из settings.json ("model_overrides" по id) накладываются
#     поверх любой записи;
#   * mmproj авто НЕ угадывается (только вручную).
#
# Модуль не тянет tkinter и импортирует settings_store ЛЕНИВО (чтобы не было
# циклического импорта: settings_store тоже спрашивает реестр о доступности).
# =========================================================

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import config
import gguf_meta


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path or ""))


def _slug(name: str) -> str:
    """id из имени файла: строчные буквы/цифры/дефисы."""
    base = os.path.splitext(os.path.basename(name or ""))[0]
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return slug or "model"


def _overrides() -> Dict[str, Dict[str, Any]]:
    """Ручные overrides по id модели из settings.json (если есть)."""
    try:
        import settings_store
        data = settings_store.get_overrides()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def discover_models(folder: Optional[str] = None) -> List[Dict[str, Any]]:
    """Авто-найденные модели: скан папки на *.gguf с чтением заголовка."""
    folder = folder or getattr(config, "MODELS_DIR", "")
    found: List[Dict[str, Any]] = []
    if not folder or not os.path.isdir(folder):
        return found
    for root, _dirs, files in os.walk(folder):
        for name in sorted(files):
            low = name.lower()
            if not low.endswith(".gguf"):
                continue
            if "mmproj" in low:            # проектор — не модель
                continue
            path = os.path.join(root, name)
            meta = gguf_meta.read_meta(path)
            if not meta.get("ok"):
                continue                    # не GGUF / битый — пропускаем
            ctx_train = meta.get("context_length") or config.AUTO_CTX
            ctx = int(min(int(ctx_train), int(config.AUTO_CTX)))
            label = meta.get("name") or os.path.splitext(name)[0]
            found.append({
                "id": _slug(name),
                "label": label,
                "path": path,
                "ctx": ctx,
                "mmproj": None,
                "extra_args": [],
                "max_tokens": None,
                "temperature": None,
                "stop": None,
                "note": "найдено автоматически (ctx=%d — изменить вручную при необходимости)" % ctx,
                "_auto": True,
            })
    return found


def _merge(manual: List[Dict[str, Any]], auto: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ручные + авто, дедуп по пути; при конфликте выигрывает ручная запись."""
    seen = {}
    result: List[Dict[str, Any]] = []
    for model in list(manual) + list(auto):
        key = _norm(model.get("path", ""))
        if key in seen:
            continue
        seen[key] = True
        result.append(dict(model))
    return result


def _apply_overrides(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    overrides = _overrides()
    if not overrides:
        return models
    result = []
    for model in models:
        patch = overrides.get(model.get("id"))
        if isinstance(patch, dict):
            model = dict(model)
            for key, value in patch.items():
                if value is not None:
                    model[key] = value
        result.append(model)
    return result


def all_models() -> List[Dict[str, Any]]:
    """Ручные + авто (если включено) + overrides. Без побочных эффектов."""
    manual = [dict(m) for m in getattr(config, "MODELS", [])]
    auto = discover_models() if getattr(config, "AUTO_DISCOVER_MODELS", False) else []
    return _apply_overrides(_merge(manual, auto))


def available_models() -> List[Dict[str, Any]]:
    """Модели, чей файл реально есть на диске (их и показываем в UI)."""
    return [m for m in all_models() if m.get("path") and os.path.exists(m["path"])]


def get_model(model_id: Optional[str] = None) -> Dict[str, Any]:
    """Запись модели: id → иначе первая доступная → иначе дефолт."""
    mid = model_id or getattr(config, "DEFAULT_MODEL_ID", None)
    for model in all_models():
        if model.get("id") == mid:
            return model
    available = available_models()
    if available:
        return available[0]
    models = all_models()
    return dict(models[0]) if models else {}


def model_is_available(model_id: Optional[str]) -> bool:
    model = get_model(model_id)
    return bool(model) and os.path.exists(model.get("path", ""))
