# -*- coding: utf-8 -*-
# =========================================================
# THEME.PY — единственный источник цветов, шрифтов и радиусов
# =========================================================
# Дизайн: «парящие карточки на градиенте». Тексты шапки рисуются прямо
# в изображении (см. ui/gradient.hero_full) — виджеты поверх градиента
# в customtkinter подкрашиваются цветом родителя и дают тёмные прямоугольники.
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

# Светлая палитра специально МЯГКАЯ: без чистой белизны (#FFFFFF) и почти
# чёрного текста. Прежние #FFFFFF рядом с #0F1117 давали резкий контраст, а
# углы скруглённых карточек на белом выглядели «грязными»/чёрными пятнами.
# Здесь фон глубже, поверхности чуть тонированы, текст — тёмно-серый,
# акценты и статусы приглушены.
LIGHT = {
    "window":        "#EDEFF7",
    "grad_top":      "#F7F8FC",
    "grad_bottom":   "#E3E5F2",
    "surface":       "#FCFCFE",
    "surface_alt":   "#F1F2F9",
    "chat_bg":       "#F4F5FB",
    "input_bg":      "#FAFBFE",
    "text":          "#2C3040",
    "text_strong":   "#1A1D28",
    "muted":         "#707689",
    "accent":        "#7C6BF0",
    "accent_hover":  "#6A59E6",
    "accent_soft":   "#ECE9FE",
    "cyan":          "#3FA7C4",
    "hero_a":        "#7C6BF0",
    "hero_b":        "#A99EFB",
    "btn":           "#EAECF6",
    "btn_hover":     "#DFE2F0",
    "border":        "#DADFEC",
    "ok":            "#2FA37A",
    "ok_soft":       "#E4F4EC",
    "warn":          "#C07A2B",
    "warn_soft":     "#FBF1E2",
    "err":           "#E15C77",
    "err_soft":      "#FCE9EF",
    "muted_soft":    "#EBEDF6",
    "record":        "#E15C77",
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

FONT_PANEL_TITLE = (_TITLE_FAMILY, 15, "bold") # «Настройки»
FONT_SECTION = (_UI_FAMILY, 11, "bold")        # подписи секций (РЕЖИМ, ТЕМА)
FONT_UI = (_UI_FAMILY, 13)                     # кнопки, обычные подписи
FONT_BODY = ("Segoe UI Emoji", 14)             # текст в чате (умеет эмодзи)
FONT_HEAD = (_UI_FAMILY, 11, "bold")           # ники и время в чате
FONT_SMALL = (_UI_FAMILY, 11)                  # подписи-секции

# Кандидаты: берём первый установленный
_TITLE_CANDIDATES = ("Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Arial")
_UI_CANDIDATES = ("Segoe UI Variable Text", "Segoe UI", "Arial")


def resolve_fonts(root):
    """Подбирает шрифты по факту (вызывать после создания окна Tk)."""
    global _TITLE_FAMILY, _UI_FAMILY
    global FONT_PANEL_TITLE, FONT_SECTION
    global FONT_UI, FONT_HEAD, FONT_SMALL

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

    FONT_PANEL_TITLE = (_TITLE_FAMILY, 15, "bold")
    FONT_SECTION = (_UI_FAMILY, 11, "bold")
    FONT_UI = (_UI_FAMILY, 13)
    FONT_HEAD = (_UI_FAMILY, 11, "bold")
    FONT_SMALL = (_UI_FAMILY, 11)


# ---------------------------------------------------------
# Шрифты для Pillow (шапка рисуется прямо в картинке)
# ---------------------------------------------------------
# Виджеты поверх градиента не годятся: customtkinter красит под ними
# прямоугольник цвета родителя. Поэтому текст шапки вписываем в изображение.
HERO_FONT_SIZES = {"title": 21, "subtitle": 12, "badge": 11, "emoji": 21}

_FONT_FILES = {
    "title":    ("seguisb.ttf", "segoeuib.ttf", "segoeui.ttf"),
    "subtitle": ("segoeui.ttf", "arial.ttf"),
    "badge":    ("segoeui.ttf", "arial.ttf"),
    "emoji":    ("seguiemj.ttf",),
}


def _fonts_dir():
    import os
    return os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def pillow_fonts(sizes=None):
    """Загружает шрифты для Pillow. Если файла нет — берём встроенный."""
    import os
    try:
        from PIL import ImageFont
    except Exception:
        return {}
    sizes = sizes or HERO_FONT_SIZES
    out = {}
    for kind, size in sizes.items():
        font = None
        for name in _FONT_FILES.get(kind, ()):
            try:
                font = ImageFont.truetype(os.path.join(_fonts_dir(), name), size)
                break
            except Exception:
                continue
        if font is None:
            try:
                font = ImageFont.load_default(size)
            except Exception:
                font = None
        if font is not None:
            out[kind] = font
    return out


def palette(name):
    """Палитра по имени темы. Неизвестное имя → тёмная."""
    return PALETTES.get(name, DARK)


def names():
    return list(PALETTES.keys())
