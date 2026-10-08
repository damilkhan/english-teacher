# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GGUF_META.PY — парсер заголовка GGUF
# =========================================================
#   python tests\test_gguf_meta.py
# Строим настоящий (крошечный) GGUF-файл в памяти и читаем его парсером.
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

import gguf_meta  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


# ---------- сериализация GGUF-заголовка ----------
U8, I8, U16, I16, U32, I32, F32, BOOL = 0, 1, 2, 3, 4, 5, 6, 7
STR, ARR, U64, I64, F64 = 8, 9, 10, 11, 12


def _s(text):
    data = text.encode("utf-8")
    return struct.pack("<Q", len(data)) + data


def _val(vtype, value):
    if vtype == U32:
        return struct.pack("<I", value)
    if vtype == U64:
        return struct.pack("<Q", value)
    if vtype == I32:
        return struct.pack("<i", value)
    if vtype == STR:
        return _s(value)
    if vtype == ARR:
        et, items = value
        out = struct.pack("<I", et) + struct.pack("<Q", len(items))
        for it in items:
            out += _val(et, it)
        return out
    raise ValueError(vtype)


def make_gguf(path, version=3, kvs=()):
    with open(path, "wb") as f:
        f.write(b"GGUF")
        f.write(struct.pack("<I", version))
        f.write(struct.pack("<Q", 0))        # tensor_count
        f.write(struct.pack("<Q", len(kvs)))
        for key, vtype, value in kvs:
            f.write(_s(key))
            f.write(struct.pack("<I", vtype))
            f.write(_val(vtype, value))
    return path


# =========================================================
def test_read_meta():
    print("\n[1] Чтение метаданных")
    tmp = tempfile.mkdtemp(prefix="et_gguf_")
    path = os.path.join(tmp, "tiny.gguf")
    # ВАЖНО: массив строк (как tokenizer.ggml.tokens) ставим ПЕРЕД context_length,
    # чтобы проверить, что пропуск больших массивов не мешает найти нужный ключ.
    make_gguf(path, kvs=[
        ("general.architecture", STR, "llama"),
        ("general.name", STR, "Tiny Test Model"),
        ("tokenizer.ggml.tokens", ARR, (STR, ["a", "b", "c", "dd", "eee"])),
        ("llama.context_length", U32, 8192),
        ("general.file_type", U32, 15),
    ])
    meta = gguf_meta.read_meta(path)
    check("ok=True", meta["ok"] is True, meta.get("error"))
    check("version прочитан", meta["version"] == 3)
    check("architecture", meta["architecture"] == "llama", meta["architecture"])
    check("name", meta["name"] == "Tiny Test Model", meta["name"])
    check("context_length найден ПОСЛЕ массива", meta["context_length"] == 8192, meta["context_length"])
    check("is_gguf True", gguf_meta.is_gguf(path) is True)


def test_big_array_skip():
    print("\n[2] Пропуск крупного массива (скорость/устойчивость)")
    tmp = tempfile.mkdtemp(prefix="et_gguf_")
    path = os.path.join(tmp, "big.gguf")
    make_gguf(path, kvs=[
        ("general.architecture", STR, "gemma"),
        ("tokenizer.ggml.tokens", ARR, (STR, ["t%d" % i for i in range(5000)])),
        ("gemma.context_length", U32, 131072),
    ])
    meta = gguf_meta.read_meta(path)
    check("нашли context_length за массивом 5000 строк",
          meta["ok"] and meta["architecture"] == "gemma" and meta["context_length"] == 131072,
          (meta.get("ok"), meta.get("architecture"), meta.get("context_length")))


def test_not_gguf():
    print("\n[3] Не GGUF / битый файл → ok=False, без падений")
    tmp = tempfile.mkdtemp(prefix="et_gguf_")
    plain = os.path.join(tmp, "note.txt")
    with open(plain, "w", encoding="utf-8") as fh:
        fh.write("просто текст")
    meta = gguf_meta.read_meta(plain)
    check("не GGUF: ok=False", meta["ok"] is False)
    check("is_gguf False", gguf_meta.is_gguf(plain) is False)

    trunc = os.path.join(tmp, "trunc.gguf")
    with open(trunc, "wb") as fh:
        fh.write(b"GGUF")                    # оборвано сразу после magic
    meta2 = gguf_meta.read_meta(trunc)
    check("обрезанный: ok=False, есть error", meta2["ok"] is False and bool(meta2["error"]))

    check("несуществующий файл: ok=False", gguf_meta.read_meta(os.path.join(tmp, "no.gguf"))["ok"] is False)


def main():
    print("=" * 60)
    print("Проверка парсера GGUF (gguf_meta.py)")
    print("=" * 60)
    test_read_meta()
    test_big_array_skip()
    test_not_gguf()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
