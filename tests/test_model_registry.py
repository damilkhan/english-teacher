# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_MODEL_REGISTRY.PY — реестр моделей и выбор модели
# =========================================================
#   python tests\test_model_registry.py
#
# Проверяем:
#   1) структуру реестра config.MODELS;
#   2) config.get_model / available_models / model_is_available;
#   3) settings_store: чтение/запись, битый файл, выбор модели;
#   4) server_manager.build_args (path/ctx/jinja/mmproj/extra_args);
#   5) server_manager._resolve_model учитывает выбор в настройках;
#   6) running_model не падает без сервера.
# =========================================================

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                       # noqa: E402
import server_manager               # noqa: E402
import settings_store               # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class patch_models:
    """Подменяет config.MODELS и (по желанию) settings_store.SETTINGS_PATH."""

    def __init__(self, models, settings_path=None):
        self.models = models
        self.settings_path = settings_path

    def __enter__(self):
        self.real_models = config.MODELS
        config.MODELS = self.models
        if self.settings_path is not None:
            self.real_path = settings_store.SETTINGS_PATH
            settings_store.SETTINGS_PATH = self.settings_path
        return self

    def __exit__(self, *exc):
        config.MODELS = self.real_models
        if self.settings_path is not None:
            settings_store.SETTINGS_PATH = self.real_path


def _touch(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("x")
    return path


# =========================================================
# 1. Структура реестра
# =========================================================
def test_registry_shape():
    print("\n[1] Структура реестра")
    ids = [m.get("id") for m in config.MODELS]
    check("id уникальны", len(ids) == len(set(ids)), ids)
    check("DEFAULT_MODEL_ID есть в реестре", config.DEFAULT_MODEL_ID in ids, ids)
    ok = True
    for m in config.MODELS:
        ok = ok and isinstance(m.get("id"), str) and isinstance(m.get("label"), str) \
            and isinstance(m.get("path"), str) and isinstance(m.get("ctx", 0), int)
    check("у каждой модели есть id/label/path/ctx", ok)


# =========================================================
# 2. get_model / available_models
# =========================================================
def test_get_model():
    print("\n[2] get_model / available_models")
    gemma = config.get_model("gemma4-e4b")
    check("get_model по id", gemma.get("id") == "gemma4-e4b")
    default = config.get_model("нет-такой")
    check("неизвестный id → модель по умолчанию",
          default.get("id") == config.DEFAULT_MODEL_ID, default.get("id"))
    check("get_model(None) → дефолт", config.get_model(None).get("id") == config.DEFAULT_MODEL_ID)

    tmp = tempfile.mkdtemp(prefix="et_models_")
    existing = _touch(os.path.join(tmp, "a.gguf"))
    models = [
        {"id": "a", "label": "A", "path": existing, "ctx": 2048, "extra_args": []},
        {"id": "b", "label": "B", "path": os.path.join(tmp, "missing.gguf"), "ctx": 4096},
    ]
    with patch_models(models):
        av = config.available_models()
        check("available_models фильтрует отсутствующие", [m["id"] for m in av] == ["a"],
              [m["id"] for m in av])
        check("model_is_available: есть файл → True", config.model_is_available("a"))
        check("model_is_available: нет файла → False", not config.model_is_available("b"))


# =========================================================
# 3. settings_store
# =========================================================
def test_settings_store():
    print("\n[3] settings_store")
    tmp = tempfile.mkdtemp(prefix="et_settings_")
    path = os.path.join(tmp, "settings.json")
    with patch_models(config.MODELS, settings_path=path):
        check("по умолчанию выбран дефолт",
              settings_store.get_selected_model_id() == config.DEFAULT_MODEL_ID)
        check("get() отдаёт дефолт при отсутствии ключа",
              settings_store.get("model_id") == config.DEFAULT_MODEL_ID)
        check("set_selected_model пишет файл",
              settings_store.set_selected_model("gemma4-e4b") and os.path.exists(path))
        check("round-trip: set → get", settings_store.get("model_id") == "gemma4-e4b")
        settings_store.set_value("extra", 42)
        check("set_value сохраняет другие ключи",
              settings_store.load().get("model_id") == "gemma4-e4b"
              and settings_store.get("extra") == 42)

        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ битый json")
        check("битый файл не роняет", isinstance(settings_store.load(), dict))
        check("битый файл → дефолт", settings_store.get("model_id") == config.DEFAULT_MODEL_ID)


def test_selected_fallback():
    print("\n[3b] Выбор недоступной модели → доступная")
    tmp = tempfile.mkdtemp(prefix="et_sel_")
    path = os.path.join(tmp, "settings.json")
    existing = _touch(os.path.join(tmp, "real.gguf"))
    models = [
        {"id": "real", "label": "Real", "path": existing, "ctx": 2048, "extra_args": []},
        {"id": "ghost", "label": "Ghost", "path": os.path.join(tmp, "no.gguf"), "ctx": 2048},
    ]
    with patch_models(models, settings_path=path):
        settings_store.set_value("model_id", "ghost")     # недоступна
        check("недоступный выбор заменяется доступной моделью",
              settings_store.get_selected_model_id() == "real",
              settings_store.get_selected_model_id())


# =========================================================
# 4. server_manager.build_args
# =========================================================
def test_build_args():
    print("\n[4] server_manager.build_args")
    model = {"id": "x", "label": "X", "path": r"D:\m\x.gguf", "ctx": 2048,
             "mmproj": r"D:\m\proj.gguf", "extra_args": ["--no-mmap"]}
    args = server_manager.build_args(model)
    check("путь модели (-m) в аргументах", model["path"] in args)
    check("контекст (-c 2048) задан", "-c" in args and args[args.index("-c") + 1] == "2048")
    check("--jinja присутствует", "--jinja" in args)
    check("--mmproj добавлен", "--mmproj" in args and model["mmproj"] in args)
    check("extra_args добавлены", "--no-mmap" in args)

    plain = server_manager.build_args({"id": "y", "label": "Y", "path": "p.gguf"})
    check("без ctx берётся общий SERVER_CONTEXT",
          plain[plain.index("-c") + 1] == str(server_manager.CONTEXT), plain)
    check("без mmproj флага нет", "--mmproj" not in plain)


# =========================================================
# 5. _resolve_model учитывает настройки
# =========================================================
def test_resolve_model():
    print("\n[5] _resolve_model")
    tmp = tempfile.mkdtemp(prefix="et_res_")
    path = os.path.join(tmp, "settings.json")
    existing = _touch(os.path.join(tmp, "a.gguf"))
    models = [{"id": "a", "label": "A", "path": existing, "ctx": 2048, "extra_args": []}]
    with patch_models(models, settings_path=path):
        settings_store.set_selected_model("a")
        check("явный id имеет приоритет",
              server_manager._resolve_model("a").get("id") == "a")
        check("None → выбранная в настройках",
              server_manager._resolve_model(None).get("id") == "a")


# =========================================================
# 6. running_model без сервера
# =========================================================
def test_running_model_safe():
    print("\n[6] running_model не падает без сервера")
    real = server_manager.BASE_URL
    try:
        server_manager.BASE_URL = "http://127.0.0.1:1"      # заведомо мёртвый порт
        mid, label = server_manager.running_model()
        check("вернулась пара (None, None)", mid is None and label is None, (mid, label))
    finally:
        server_manager.BASE_URL = real


def main():
    print("=" * 60)
    print("Проверка реестра моделей и выбора модели")
    print("=" * 60)

    test_registry_shape()
    test_get_model()
    test_settings_store()
    test_selected_fallback()
    test_build_args()
    test_resolve_model()
    test_running_model_safe()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
