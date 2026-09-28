# -*- coding: utf-8 -*-
# =========================================================
# UI/GRADIENT.PY — градиенты через Pillow
# =========================================================
# customtkinter не умеет градиенты, поэтому рисуем их сами:
#   * вертикальный градиент страницы — на tk.Canvas полосками (дёшево);
#   * градиент шапки и полоска-разделитель — картинкой PIL, потому что
#     нужны скруглённые углы и диагональ.
#
# Всё возвращается как обычные PIL-картинки: где их показать, решает UI.
# =========================================================

from PIL import Image, ImageDraw

try:  # быстрый ресемплинг в новых Pillow, со страховкой для старых
    _RESAMPLE = Image.Resampling.BILINEAR
except AttributeError:  # pragma: no cover
    _RESAMPLE = Image.BILINEAR


# ---------------------------------------------------------
# Цвета
# ---------------------------------------------------------
def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def lerp_hex(c1, c2, t):
    """Цвет между c1 и c2: t=0 → c1, t=1 → c2."""
    t = max(0.0, min(1.0, t))
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    return rgb_to_hex([a[i] + (b[i] - a[i]) * t for i in range(3)])


def mix(c1, c2, t):
    return lerp_hex(c1, c2, t)


# ---------------------------------------------------------
# Картинки
# ---------------------------------------------------------
def vertical(size, top, bottom):
    """Вертикальный градиент top → bottom."""
    w, h = max(1, int(size[0])), max(1, int(size[1]))
    img = Image.new("RGB", (1, h))
    px = img.load()
    for y in range(h):
        px[0, y] = hex_to_rgb(lerp_hex(top, bottom, y / max(1, h - 1)))
    return img.resize((w, h), _RESAMPLE)


def diagonal(size, c1, c2, angle=35):
    """Мягкий диагональный градиент — для шапки.

    Считаем на сетке 96x96 и растягиваем: так дорогая операция остаётся
    на крошечном холсте, а цвет плавно идёт из левого верхнего угла в
    правый нижний.

    ВАЖНО: раньше здесь линии рисовались только в одном треугольнике
    ([(i,0),(0,i)]), и вторая половина оставалась чёрной — шапка выглядела
    почти чёрной с редкими фиолетовыми пятнами. Теперь заливка сплошная.
    """
    w, h = max(2, int(size[0])), max(2, int(size[1]))
    n = 96
    small = Image.new("RGB", (n, n))
    px = small.load()
    span = float(2 * n - 2)
    for y in range(n):
        for x in range(n):
            t = (x + y) / span              # 0 в левом верхнем, 1 в правом нижнем
            px[x, y] = hex_to_rgb(lerp_hex(c1, c2, t))
    return small.resize((w, h), _RESAMPLE)


def rounded(img, radius, bg):
    """Скругляет углы картинки, подложив под неё цвет bg."""
    w, h = img.size
    radius = max(0, min(int(radius), min(w, h) // 2))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    base = Image.new("RGB", (w, h), hex_to_rgb(bg))
    base.paste(img, (0, 0), mask)
    return base


def hero(width, height, c1, c2, radius, bg, angle=35):
    """Шапка: диагональный градиент со скруглёнными углами."""
    w = max(2, int(width))
    h = max(2, int(height))
    return rounded(diagonal((w, h), c1, c2, angle=angle), radius, bg)


def strip(size, c1, c2):
    """Тонкая градиентная полоска (акцентная линия)."""
    return vertical((max(1, int(size[0])), max(1, int(size[1]))), c1, c2)


# ---------------------------------------------------------
# Фон страницы на tk.Canvas
# ---------------------------------------------------------
def draw_vertical(canvas, width, height, top, bottom, tag="grad", max_steps=420):
    """Рисует вертикальный градиент полосками. Возвращает число полос.

    Полоски шириной в 1 px по высоте окна — это ~400 объектов Canvas,
    что для Tk недорого (и перерисовывается только при изменении размера).
    """
    canvas.delete(tag)
    w, h = int(width), int(height)
    if w <= 1 or h <= 1:
        return 0
    steps = min(h, max_steps)
    for i in range(steps):
        y0 = int(i * h / steps)
        y1 = int((i + 1) * h / steps) + 1
        color = lerp_hex(top, bottom, i / max(1, steps - 1))
        canvas.create_rectangle(0, y0, w, y1, fill=color, outline="", tags=tag)
    return steps
