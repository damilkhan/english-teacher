# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_MODEL_DISCOVERY.PY — автопоиск моделей и реестр
# =========================================================
#   python tests\test_model_discovery.py
# =========================================================

import os
import struct
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

import config        # noqa: E402
import model_registry  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def _write_gguf(path, arch="llama", name="Test", ctx=8192):
    def _s(t):
        d = t.encode("utf-8")
        return struct.pack("<Q", len(d)) + d

    with open(path, "wb") as f:
        f.write(b"GGUF")
        f.write(struct.pack("<I", 3))
        f.write(struct.pack("<Q", 0))
        f.write(struct.pack("<Q", 3))
        f.write(_s("general.architecture") + struct.pack("<I", 8) + _s(arch))
        f.write(_s("general.name") + struct.pack("<I", 8) + _s(name))
        f.write(_s("%s.context_length" % arch) + struct.pack("<I", 4) + struct.pack("<I", ctx))
    return path


class patch_cfg:
    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.saved = {}
        for k, v in self.kw.items():
            self.saved[k] = getattr(config, k, None)
            setattr(config, k, v)
        return self

    def __exit__(self, *e):
        for k, v in self.saved.items():
            setattr(config, k, v)


# =========================================================
def test_discover():
    print("\n[1] discover_models: сканирует, читает gguf, консервативный ctx")
    tmp = tempfile.mkdtemp(prefix="et_disc_")
    _write_gguf(os.path.join(tmp, "Llama-Test-Q4.gguf"), name="Llama Test", ctx=131072)
    sub = os.path.join(tmp, "sub_arch")
    os.makedirs(sub)
    _write_gguf(os.path.join(sub, "qwen2.5.gguf"), arch="qwen2", name="Qwen Tiny", ctx=2048)
    with open(os.path.join(tmp, "readme.txt"), "w", encoding="utf-8") as fh:
        fh.write("x")
    # проектор (mmproj) не должен попасть в модели
    _write_gguf(os.path.join(tmp, "mmproj-model-f16.gguf"), name="Projector (should skip)")

    with patch_cfg(MODELS_DIR=tmp, AUTO_CTX=4096, MODELS=[], AUTO_DISCOVER_MODELS=True,
                   DEFAULT_MODEL_ID="x"):
        found = model_registry.discover_models(tmp)
        ids = sorted(m["id"] for m in found)
        check("найдены только .gguf-модели (без mmproj и .txt)", len(found) == 2, ids)
        by_label = {m["label"]: m for m in found}
        check("имя взято из метаданных (а не из файла)", "Llama Test" in by_label, list(by_label))
        big = by_label.get("Llama Test")
        check("консервативный ctx = min(131072, AUTO_CTX=4096)",
              big and big["ctx"] == 4096, big and big["ctx"])
        small = by_label.get("Qwen Tiny")
        check("малый ctx не увеличивается", small and small["ctx"] == 2048, small and small["ctx"])
        check("id — из имени файла (slug)", "llama-test-q4" in ids, ids)


def test_merge_and_override():
    print("\n[2] Ручной список + авто + override")
    tmp = tempfile.mkdtemp(prefix="et_disc_")
    auto_path = _write_gguf(os.path.join(tmp, "auto.gguf"), name="Auto", ctx=8192)
    manual_path = os.path.join(tmp, "manual.gguf")
    _write_gguf(manual_path, name="Manual", ctx=4096)

    with patch_cfg(MODELS_DIR=tmp, AUTO_CTX=4096, AUTO_DISCOVER_MODELS=True,
                   DEFAULT_MODEL_ID="manual",
                   MODELS=[{"id": "manual", "label": "Manual", "path": manual_path,
                            "ctx": 1024, "mmproj": None, "extra_args": []}]):
        models = model_registry.all_models()
        by_id = {m["id"]: m for m in models}
        check("ручная модель на месте", "manual" in by_id)
        check("авто-модель добавлена", "auto" in by_id, list(by_id))
        check("ручной ctx не перебит", by_id["manual"]["ctx"] == 1024, by_id["manual"]["ctx"])

        # override из settings.json по id
        import settings_store
        real = settings_store.SETTINGS_PATH
        sp = os.path.join(tmp, "settings.json")
        try:
            settings_store.SETTINGS_PATH = sp
            settings_store.set_override("auto", {"ctx": 2048, "extra_args": ["--no-mmap"]})
            models = model_registry.all_models()
            auto = next(m for m in models if m["id"] == "auto")
            check("override применил ctx", auto["ctx"] == 2048, auto["ctx"])
            check("override применил extra_args", auto["extra_args"] == ["--no-mmap"], auto["extra_args"])
        finally:
            settings_store.SETTINGS_PATH = real


def test_dedup_by_path():
    print("\n[3] Дедуп по пути (ручная запись выигрывает)")
    tmp = tempfile.mkdtemp(prefix="et_disc_")
    p = _write_gguf(os.path.join(tmp, "same.gguf"), name="Same", ctx=8192)
    with patch_cfg(MODELS_DIR=tmp, AUTO_CTX=4096, AUTO_DISCOVER_MODELS=True,
                   DEFAULT_MODEL_ID="same.gguf",
                   MODELS=[{"id": "same.gguf", "label": "Hand-written", "path": p,
                            "ctx": 777, "mmproj": None, "extra_args": []}]):
        models = model_registry.all_models()
        same = [m for m in models if os.path.normcase(os.path.abspath(m["path"])) == os.path.normcase(os.path.abspath(p))]
        check("запись про этот путь ровно одна", len(same) == 1, len(same))
        check("осталась ручная запись", same and same[0]["label"] == "Hand-written", same)


def main():
    print("=" * 60)
    print("Проверка автопоиска моделей (model_registry)")
    print("=" * 60)
    test_discover()
    test_merge_and_override()
    test_dedup_by_path()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
