# -*- coding: utf-8 -*-
# =========================================================
# THEME.PY — единственный источник цветов и шрифтов
# =========================================================
# Раньше цвета (#1a1a1a, #8C43EB, #2a2a2a ...) были разбросаны по gui.py
# в ~40 местах, а смена темы — это две копии длинного if/else
# configure(). Теперь палитра описана здесь один раз, а каждый виджет
# умеет применять её к себе методом apply_theme(palette).
#
# Поправить цвет = поправить одну строку здесь.
# =========================================================

# Ключи палитры. Имена смысловые, а не «по цвету», —
# поэтому светлая тема не требует переписывать виджеты.
DARK = {
    "window":       "#121212",   # фон окна
    "surface":      "#1a1a1a",   # панели/фреймы
    "chat_bg":      "#1e1e1e",   # фон чата и визуализатора
    "block":        "#222222",   # вложенные блоки (режим/тема)
    "input_bg":     "#1a1a1a",   # поле ввода
    "text":         "#e0e0e0",   # основной текст
    "text_strong":  "#ffffff",   # заголовки
    "muted":        "#888888",   # подписи
    "accent":       "#8C43EB",   # акцент (кнопки, ники в чате)
    "accent_hover": "#6b2fb8",
    "btn":          "#2a2a2a",   # обычные кнопки
    "btn_hover":    "#3a3a3a",
    "border":       "#3a3a3a",
    "ok":           "#4CAF50",   # статус «готов»
    "warn":         "#FF9800",   # статус «идёт процесс»
    "err":          "#f44336",   # статус «ошибка»
    "record":       "#f44336",   # активная запись
}

LIGHT = {
    "window":       "#f0f0f0",
    "surface":      "#ffffff",
    "chat_bg":      "#f5f5f5",
    "block":        "#e8e8e8",
    "input_bg":     "#ffffff",
    "text":         "#1a1a1a",
    "text_strong":  "#1a1a1a",
    "muted":        "#5a5a5a",
    "accent":       "#8C43EB",
    "accent_hover": "#6b2fb8",
    "btn":          "#e0e0e0",
    "btn_hover":    "#d0d0d0",
    "border":       "#cccccc",
    "ok":           "#2E7D32",
    "warn":         "#E65100",
    "err":          "#C62828",
    "record":       "#D32F2F",
}

PALETTES = {"dark": DARK, "light": LIGHT}

# Шрифты — тоже в одном месте
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_PANEL_TITLE = ("Segoe UI", 16, "bold")
FONT_BODY = ("Segoe UI Emoji", 14)
FONT_HEAD = ("Segoe UI", 12, "bold")
FONT_SMALL = ("Segoe UI", 12)


def palette(name):
    """Палитра по имени темы. Неизвестное имя → тёмная."""
    return PALETTES.get(name, DARK)


def names():
    return list(PALETTES.keys())
