# -*- coding: utf-8 -*-
# =========================================================
# GGUF_META.PY — чтение метаданных GGUF-файла (только stdlib)
# =========================================================
# Нужен, чтобы при авто-обнаружении моделей узнать ИЗ САМОГО ФАЙЛА, а не
# угадывать по имени: архитектуру, человекочитаемое имя и обучающий контекст.
#
# Формат заголовка GGUF (little-endian):
#   magic "GGUF" | version u32 | tensor_count u64 | kv_count u64
#   далее kv_count пар: key(строка) | value_type u32 | value
#   строка = u64-длина + utf-8 байты; массив = u32 тип + u64 количество + элементы
#
# Читаем ТОЛЬКО заголовок (KV-секция идёт до тензоров), а большие значения
# (например, tokenizer.ggml.tokens — сотни тысяч строк) ПРОПУСКАЕМ через
# seek/read-в-никуда, не декодируя: это доли секунды на файл.
# =========================================================

from __future__ import annotations

import struct
from typing import Any, Dict, Optional

MAGIC = b"GGUF"

_U32 = struct.Struct("<I")
_U64 = struct.Struct("<Q")

# id типов значений GGUF
T_UINT8, T_INT8, T_UINT16, T_INT16 = 0, 1, 2, 3
T_UINT32, T_INT32, T_FLOAT32, T_BOOL = 4, 5, 6, 7
T_STRING, T_ARRAY, T_UINT64, T_INT64, T_FLOAT64 = 8, 9, 10, 11, 12

# фиксированные типы: (struct-формат, ширина в байтах)
_FIXED = {
    T_UINT8: ("<B", 1), T_INT8: ("<b", 1), T_UINT16: ("<H", 2), T_INT16: ("<h", 2),
    T_UINT32: ("<I", 4), T_INT32: ("<i", 4), T_FLOAT32: ("<f", 4), T_BOOL: ("<?", 1),
    T_UINT64: ("<Q", 8), T_INT64: ("<q", 8), T_FLOAT64: ("<d", 8),
}

MAX_KEYS = 200000          # предохранитель от битого заголовка
MAX_ARRAY = 1 << 26        # предохранитель от абсурдного количества элементов


def _u32(f) -> int:
    data = f.read(4)
    if len(data) < 4:
        raise ValueError("неожиданный конец файла")
    return _U32.unpack(data)[0]


def _u64(f) -> int:
    data = f.read(8)
    if len(data) < 8:
        raise ValueError("неожиданный конец файла")
    return _U64.unpack(data)[0]


def _string(f) -> str:
    n = _u64(f)
    return f.read(n).decode("utf-8", "replace")


def _read_value(f, vtype: int) -> Any:
    """Прочитать значение нужного типа (для скалярных ключей)."""
    if vtype in _FIXED:
        fmt, width = _FIXED[vtype]
        data = f.read(width)
        if len(data) < width:
            raise ValueError("неожиданный конец файла")
        return struct.unpack(fmt, data)[0]
    if vtype == T_STRING:
        return _string(f)
    if vtype == T_ARRAY:
        return _read_array(f)
    raise ValueError("неизвестный тип значения %r" % vtype)


def _read_array(f) -> list:
    elem_type = _u32(f)
    count = _u64(f)
    if count > MAX_ARRAY:
        raise ValueError("слишком большой массив (%d)" % count)
    return [_read_value(f, elem_type) for _ in range(count)]


def _skip_value(f, vtype: int, count: int = 1) -> None:
    """Пропустить count значений типа vtype, НЕ читая их в память."""
    if vtype in _FIXED:
        _fmt, width = _FIXED[vtype]
        f.seek(width * count, 1)
        return
    if vtype == T_STRING:
        for _ in range(count):
            n = _u64(f)
            f.seek(n, 1)
        return
    if vtype == T_ARRAY:
        elem_type = _u32(f)
        n = _u64(f)
        if n > MAX_ARRAY:
            raise ValueError("слишком большой массив (%d)" % n)
        if elem_type in _FIXED:
            _fmt, width = _FIXED[elem_type]
            f.seek(width * n, 1)
        elif elem_type == T_STRING:
            for _ in range(n):
                ln = _u64(f)
                f.seek(ln, 1)
        else:
            for _ in range(n):
                _skip_value(f, elem_type)
        return
    raise ValueError("неизвестный тип значения %r" % vtype)


def read_meta(path: str) -> Dict[str, Any]:
    """Заголовок GGUF: ok/error + architecture/name/context_length/file_type.

    Возвращает словарь; поле "ok" = True, если заголовок прочитан. При любой
    проблеме (не GGUF, обрезан, битый) "ok"=False и "error" с причиной —
    исключений наружу нет.
    """
    result: Dict[str, Any] = {
        "ok": False, "error": None, "version": None,
        "architecture": None, "name": None, "context_length": None,
        "file_type": None, "keys": {},
    }
    try:
        with open(path, "rb") as f:
            if f.read(4) != MAGIC:
                result["error"] = "не GGUF-файл"
                return result
            version = _u32(f)
            result["version"] = version
            _tensor_count = _u64(f)
            kv_count = _u64(f)
            if kv_count > MAX_KEYS:
                result["error"] = "подозрительное число ключей (%d)" % kv_count
                return result

            meta: Dict[str, Any] = {}
            for _ in range(int(kv_count)):
                key = _string(f)
                vtype = _u32(f)
                # читаем только «дешёвые» нужные ключи; массивы пропускаем
                keep = (key.startswith("general.") or key.endswith(".context_length"))
                if keep and vtype != T_ARRAY:
                    meta[key] = _read_value(f, vtype)
                else:
                    _skip_value(f, vtype)

            arch = meta.get("general.architecture")
            result["architecture"] = arch
            result["name"] = meta.get("general.name")
            result["file_type"] = meta.get("general.file_type")
            if arch:
                ctx = meta.get("%s.context_length" % arch)
                if isinstance(ctx, int):
                    result["context_length"] = ctx
            result["keys"] = meta
            result["ok"] = True
    except Exception as exc:                       # noqa: BLE001 — битый файл не должен ронять
        result["error"] = str(exc)
    return result


def is_gguf(path: str) -> bool:
    """Быстрая проверка: файл начинается с magic 'GGUF'."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == MAGIC
    except OSError:
        return False
