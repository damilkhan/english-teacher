# -*- coding: utf-8 -*-
# =========================================================
# THEME.PY — единственный источник цветов, шрифтов и радиусов
# =========================================================
# Дизайн переделан: «полупрозрачные карточки на градиенте».
#   * фон окна — мягкий вертикальный градиент (тёмная тема: почти
#     чёрный с уходом в фиолетовый, светлая: белый в лаванду);
#   * карточки — плотные, скруглённые, с тонкой рамкой;
#   * акцент — фиолетовый #7C5CFF, второй акцент — циан #22D3EE
#     (используется в градиенте полосок эквалайзера и нике «Вы»);
#   * шрифты — Segoe UI Variable (Win11), с откатом на Segoe UI/Arial.
#
# Правило прежнее: поправить цвет = поправить одну строку здесь.
# Виджеты не знают конкретных значений, они берут ключи палитры.
# =========================================================

# ---------------------------------------------------------
# Палитры
# ---------------------------------------------------------
DARK = {
    # фоны
    "window":        "#0E1017",   # база-фон окна (под градиентом)
    "grad_top":      "#12141D",   # верх градиента страницы
    "grad_bottom":   "#1D1738",   # низ градиента страницы (уход в фиолетовый)
    "surface":       "#1A1E2A",   # карточки
    "surface_alt":   "#1F2331",   # вложенные блоки (секции настроек)
    "chat_bg":       "#14161F",   # область чата — чуть темнее карточки
    "input_bg":      "#1B1F2B",
    # текст
    "text":          "#E7E9F0",
    "text_strong":   "#FFFFFF",
    "muted":         "#8A90A6",
    # акценты
    "accent":        "#7C5CFF",
    "accent_hover":  "#6A4AEB",
    "accent_soft":   "#241E3F",
    "cyan":          "#22D3EE",
    "hero_a":        "#241A4D",   # градиент шапки
    "hero_b":        "#5B32C9",
    # кнопки и линии
    "btn":           "#222735",
    "btn_hover":     "#2C3345",
    "border":        "#2A3040",
    # статусы
    "ok":            "#34D399",
    "ok_soft":       "#10352B",
    "warn":          "#FBBF24",
    "warn_soft":     "#3A2E10",
    "err":           "#FB7185",
    "err_soft":      "#3A1721",
    "muted_soft":    "#232839",
    "record":        "#F43F5E",
}

LIGHT = {
    "window":        "#F4F5FA",
    "grad_top":      "#FFFFFF",
    "grad_bottom":   "#E6E9F8",
    "surface":       "#FFFFFF",
    "surface_alt":   "#F1F3FA",
    "chat_bg":       "#FAFBFE",
    "input_bg":      "#FFFFFF",
    "text":          "#1B1E28",
    "text_strong":   "#0F1117",
    "muted":         "#6B7186",
    "accent":        "#6D5DF6",
    "accent_hover":  "#5B4BE0",
    "accent_soft":   "#EDEAFE",
    "cyan":          "#0891B2",
    "hero_a":        "#6D5DF6",
    "hero_b":        "#9B8BFF",
    "btn":           "#EDEFF7",
    "btn_hover":     "#E1E4EF",
    "border":        "#DFE3EE",
    "ok":            "#0E9F6E",
    "ok_soft":       "#E3F7EF",
    "warn":          "#B45309",
    "warn_soft":     "#FEF3E2",
    "err":           "#E11D48",
    "err_soft":      "#FDE7EC",
    "muted_soft":    "#EEF0F7",
    "record":        "#E11D48",
}

PALETTES = {"dark": DARK, "light": LIGHT}

# ---------------------------------------------------------
# Геометрия
# ---------------------------------------------------------
R = {                      # радиусы скругления
    "card": 16,
    "block": 12,
    "button": 10,
    "input": 10,
    "pill": 12,
    "strip": 2,
}

PAGE_PAD = 16              # отступ страницы от края окна
CARD_PAD = 14              # внутренние отступы карточки
GAP = 14                   # зазор между колонками

# ---------------------------------------------------------
# Шрифты
# ---------------------------------------------------------
# Значения переопределяются в resolve_fonts() после создания окна:
# подобрать шрифт можно только зная, что установлено в системе.
_TITLE_FAMILY = "Segoe UI"
_UI_FAMILY = "Segoe UI"
_MONO_FAMILY = "Consolas"

FONT_TITLE = (_TITLE_FAMILY, 20, "bold")       # заголовок шапки
FONT_SUBTITLE = (_UI_FAMILY, 12)               # подпись под заголовком
FONT_PANEL_TITLE = (_TITLE_FAMILY, 15, "bold") # «Настройки»
FONT_SECTION = (_UI_FAMILY, 11, "bold")        # подписи секций (РЕЖИМ, ТЕМА)
FONT_UI = (_UI_FAMILY, 13)                     # кнопки, обычные подписи
FONT_BODY = ("Segoe UI Emoji", 14)             # текст в чате (умеет эмодзи)
FONT_HEAD = (_UI_FAMILY, 11, "bold")           # ники и время в чате
FONT_SMALL = (_UI_FAMILY, 11)                  # бейдж статуса
FONT_MONO = (_MONO_FAMILY, 11)

# Кандидаты: берём первый установленный
_TITLE_CANDIDATES = ("Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Arial")
_UI_CANDIDATES = ("Segoe UI Variable Text", "Segoe UI", "Arial")
_MONO_CANDIDATES = ("Cascadia Code", "Consolas", "Courier New")


def resolve_fonts(root):
    """Подбирает шрифты по факту (вызывать после создания окна Tk)."""
    global _TITLE_FAMILY, _UI_FAMILY, _MONO_FAMILY
    global FONT_TITLE, FONT_SUBTITLE, FONT_PANEL_TITLE, FONT_SECTION
    global FONT_UI, FONT_HEAD, FONT_SMALL, FONT_MONO

    try:
        from tkinter import font as tkfont
        installed = set(tkfont.families(root))
    except Exception:
        return

    def pick(candidates, fallback):
        for name in candidates:
            if name in installed:
                return name
        return fallback

    _TITLE_FAMILY = pick(_TITLE_CANDIDATES, "Segoe UI")
    _UI_FAMILY = pick(_UI_CANDIDATES, "Segoe UI")
    _MONO_FAMILY = pick(_MONO_CANDIDATES, "Consolas")

    FONT_TITLE = (_TITLE_FAMILY, 20, "bold")
    FONT_SUBTITLE = (_UI_FAMILY, 12)
    FONT_PANEL_TITLE = (_TITLE_FAMILY, 15, "bold")
    FONT_SECTION = (_UI_FAMILY, 11, "bold")
    FONT_UI = (_UI_FAMILY, 13)
    FONT_HEAD = (_UI_FAMILY, 11, "bold")
    FONT_SMALL = (_UI_FAMILY, 11)
    FONT_MONO = (_MONO_FAMILY, 11)


def palette(name):
    """Палитра по имени темы. Неизвестное имя → тёмная."""
    return PALETTES.get(name, DARK)


def names():
    return list(PALETTES.keys())
