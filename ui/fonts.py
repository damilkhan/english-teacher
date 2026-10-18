# -*- coding: utf-8 -*-
"""ui.fonts — подключение шрифтов ИЗ ФАЙЛА (без установки в систему).

Tk не умеет грузить шрифт по пути: он видит только те, что установлены в
Windows. Но есть способ GDI: `AddFontResourceExW` с флагом FR_PRIVATE —
шрифт доступен ТОЛЬКО текущему процессу и исчезает при закрытии приложения.
Система не засоряется, устанавливать ничего не нужно.

Порядок важен: шрифт надо зарегистрировать ДО того, как Tk впервые спросят
список семейств (theme.resolve_fonts), иначе Tk его не увидит.

Зачем нам это: чат рисуется пиксельным шрифтом Undertale (под стиль робота
и LED-эквалайзера). Он лежит в assets/fonts и в git не входит.
"""

from __future__ import annotations

import ctypes
import logging
import os

_log = logging.getLogger(__name__)

# Флаг GDI: шрифт доступен только процессу (система остаётся чистой).
FR_PRIVATE = 0x10

# Сколько шрифтов уже подключили (чтобы дважды не регистрировать).
_registered: dict = {}


def register_font(path: str) -> bool:
    """Подключить один файл шрифта. True — получилось (или уже был)."""
    if not path:
        return False
    full = os.path.abspath(path)
    if full in _registered:
        return _registered[full]
    if not os.path.isfile(full):
        _log.info("Шрифт не найден: %s", full)
        _registered[full] = False
        return False
    try:
        added = ctypes.windll.gdi32.AddFontResourceExW(
            ctypes.c_wchar_p(full), FR_PRIVATE, 0)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("Шрифт не подключился (%s): %s", full, exc)
        _registered[full] = False
        return False
    ok = bool(added)
    _registered[full] = ok
    if ok:
        _log.info("Шрифт подключён: %s", os.path.basename(full))
    else:
        _log.warning("GDI отказался подключить шрифт: %s", full)
    return ok


def register_fonts(paths) -> int:
    """Подключить несколько шрифтов. Возвращает число удачных."""
    return sum(1 for path in (paths or []) if register_font(path))


def release_font(path: str) -> None:
    """Освободить шрифт (вызывается при закрытии приложения)."""
    full = os.path.abspath(path or "")
    if not _registered.get(full):
        return
    try:
        ctypes.windll.gdi32.RemoveFontResourceExW(
            ctypes.c_wchar_p(full), FR_PRIVATE, 0)
    except Exception:                              # noqa: BLE001
        pass
    _registered[full] = False


def release_all() -> None:
    """Освободить все подключённые шрифты."""
    for path in list(_registered):
        release_font(path)


def family_available(root, family: str) -> bool:
    """Видит ли Tk такое семейство шрифтов."""
    if not family:
        return False
    try:
        from tkinter import font as tkfont
        # заставляем Tk перечитать список семейств
        try:
            root.tk.call("font", "families")
        except Exception:
            pass
        return family in set(tkfont.families(root))
    except Exception:                              # noqa: BLE001
        return False
