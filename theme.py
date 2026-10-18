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

    # --- карта прогресса (ui/widgets/map_view) ---
    # Жетоны рисуются ПОВЕРХ картинки карты (песок), поэтому цвета
    # подобраны так, чтобы читаться на тёплом фоне.
    "map_locked":           "#8B223C",   # точка ещё не открыта (бордовый)
    "map_unlocked":         "#4ADE80",   # активная точка (яркий зелёный, пульсирует)
    "map_done":             "#2E9E63",   # точка пройдена (приглушённый зелёный)
    "map_border":           "#FFFFFF",   # белый ободок жетона
    "map_num_outline":      "#0A3D26",   # контур цифры на зелёном
    "map_num_outline_locked": "#3A0814", # контур цифры на бордовом
    "map_bg":               "#14161F",   # фон карты, если картинки нет
    "map_tooltip_bg":       "#1F2331",
    "map_tooltip_text":     "#E7E9F0",
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

    # --- карта прогресса (см. DARK: те же роли, чуть плотнее для светлой темы) ---
    "map_locked":           "#A82847",
    "map_unlocked":         "#22B25E",
    "map_done":             "#1F8A52",
    "map_border":           "#FFFFFF",
    "map_num_outline":      "#06301C",
    "map_num_outline_locked": "#420A1A",
    "map_bg":               "#EFE6D2",
    "map_tooltip_bg":       "#FFFFFF",
    "map_tooltip_text":     "#2C3040",
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
FONT_BODY_DEFAULT = ("Segoe UI Emoji", 14)     # обычное тело чата
FONT_BODY = FONT_BODY_DEFAULT                  # текст в чате (текущий)
# Шрифт чата после resolve_fonts(): либо пиксельный (Undertale), либо Segoe.
# Нужен отдельно, потому что пиксельный может не подключиться — тогда
# остаётся обычный, и приложение работает как раньше.
CHAT_FONT_OK = False                           # пиксельный шрифт включён?
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

    # --- пиксельный шрифт ЧАТА (если подключён и виден Tk) ---
    resolve_chat_font(root)


def resolve_chat_font(root):
    """Включить пиксельный шрифт для ЧАТА, если он доступен.

    Шрифт подключается из файла (ui.fonts, режим FR_PRIVATE) — в систему
    ничего не ставится. Если файла нет, Tk его не видит или настройка
    выключена — чат остаётся на Segoe UI, и ничего не ломается.

    Меняем ТОЛЬКО FONT_BODY (тело реплик): ники, кнопки, панели и мелкие
    подписи остаются на Segoe — там нужны 11 px и жирность, а пиксельный
    на таких размерах размывается.
    """
    global FONT_BODY, CHAT_FONT_OK
    CHAT_FONT_OK = False
    try:
        import config
    except Exception:                          # noqa: BLE001
        return False
    if not getattr(config, "CHAT_PIXEL_FONT", False):
        FONT_BODY = FONT_BODY_DEFAULT          # выключено → обычный шрифт
        return False
    family = str(getattr(config, "CHAT_FONT_FAMILY", "") or "")
    size = int(getattr(config, "CHAT_FONT_SIZE", 16) or 16)
    if not family:
        return False
    try:
        from ui import fonts
        if not fonts.family_available(root, family):
            # пробуем подключить файл сами (на случай, если ещё не подключён)
            fonts.register_font(getattr(config, "CHAT_FONT_FILE", ""))
            if not fonts.family_available(root, family):
                print("ℹ️ Шрифт чата «%s» недоступен — остаётся Segoe UI" % family)
                FONT_BODY = FONT_BODY_DEFAULT
                return False
    except Exception as exc:                   # noqa: BLE001
        print("⚠️ Шрифт чата не подключился (%s) — остаётся Segoe UI" % exc)
        FONT_BODY = FONT_BODY_DEFAULT
        return False
    FONT_BODY = (family, size)
    CHAT_FONT_OK = True
    return True


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
