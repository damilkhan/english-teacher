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


# ---------------------------------------------------------
# Измерение «чернил» текста
# ---------------------------------------------------------
_PAD = 4      # отступ при измерении на временном холсте


def _ink(text, font, embedded=False, fill=(255, 255, 255, 255)):
    """Возвращает (картинка_чернил, bbox) для текста или эмодзи.

    Нужно потому, что Pillow считает ширину по РАМКЕ глифа, а не по
    видимым пикселям: у эмодзи 🎙️ textlength() даёт 58 px, тогда как
    сами чернила занимают 15 px (слева пусто 7 px, справа 36 px).
    Из-за этого между значком и заголовком возникал отступ 48 px.
    """
    if font is None or not text:
        return None, None
    side = max(24, getattr(font, "size", 16))
    tmp = Image.new("RGBA", (side * (len(text) + 4), side * 4), (0, 0, 0, 0))
    drawer = ImageDraw.Draw(tmp)
    try:
        drawer.text((_PAD, _PAD), text, font=font, fill=fill, embedded_color=embedded)
    except TypeError:                      # старая Pillow без embedded_color
        drawer.text((_PAD, _PAD), text, font=font, fill=fill)
    bbox = tmp.getbbox()
    if bbox is None:
        return None, None
    return tmp.crop(bbox), bbox


def _ink_center_offset(text, font):
    """На сколько центр чернил текста ниже точки отрисовки draw.text().

    У эмодзи и у текста разные базовые линии, поэтому одинаковые координаты
    дают сдвиг по вертикали (значок уезжал на 8.5 px вверх).
    """
    _, bbox = _ink(text, font)
    if bbox is None:
        return getattr(font, "size", 14) / 2.0
    return (bbox[1] + bbox[3]) / 2.0 - _PAD


# ---------------------------------------------------------
# Шапка целиком
# ---------------------------------------------------------
def hero_full(size, pal, emoji="", title="", subtitle="", badge=None,
              badge_text_color=None, badge_bg=None, fonts=None,
              title_pos=(22, 17), subtitle_pos=(24, 50), badge_margin=18,
              radius=16, title_color="#FFFFFF", subtitle_color="#DAD3FF",
              badge_pad_x=14, badge_pill_h=30, emoji_gap=8):
    """Собирает шапку полностью: градиент, скругление, эмодзи, заголовок,
    подпись и пилюлю статуса.

    Текст вписывается ПРЯМО в картинку, потому что виджеты поверх градиента
    красят под собой прямоугольник цвета родителя: у строк заголовка получался
    тёмный фон вплотную к буквам, а у круглой пилюли «Готов» — тёмный квадрат.
    """
    w, h = max(2, int(size[0])), max(2, int(size[1]))
    img = rounded(diagonal((w, h), pal["hero_a"], pal["hero_b"]), radius, pal["surface"])
    draw = ImageDraw.Draw(img)
    fonts = fonts or {}

    # --- заголовок: значок + текст ---
    x, y = title_pos
    t_font = fonts.get("title")
    e_font = fonts.get("emoji")

    if emoji and e_font is not None:
        # рисуем значок отдельной картинкой и вставляем по ЧЕРНИЛАМ, а не по
        # рамке глифа: так отступ равен ровно emoji_gap, а не «emoji_gap + 36»
        glyph, _ = _ink(emoji, e_font, embedded=True)
        if glyph is not None:
            # вертикаль: центруем чернила значка по чернилам заголовка
            center = y + _ink_center_offset(title, t_font)
            img.paste(glyph, (int(x), int(round(center - glyph.height / 2.0))),
                      glyph.split()[3])
            x += glyph.width + emoji_gap
        else:
            print("⚠️ Значок шапки не нарисовался — пропускаю")

    if title and t_font is not None:
        draw.text((x, y), title, font=t_font, fill=title_color)

    # подпись
    s_font = fonts.get("subtitle")
    if subtitle and s_font is not None:
        draw.text(subtitle_pos, subtitle, font=s_font, fill=subtitle_color)

    # пилюля статуса у правого края
    b_font = fonts.get("badge")
    if badge and b_font is not None and badge_bg:
        try:
            tw = draw.textlength(badge, font=b_font)
        except Exception:
            tw = len(badge) * 7
        x1 = w - badge_margin
        x0 = max(badge_margin, x1 - tw - 2 * badge_pad_x)
        y0 = max(0, (h - badge_pill_h) // 2)
        y1 = y0 + badge_pill_h
        draw.rounded_rectangle([x0, y0, x1, y1], radius=badge_pill_h // 2, fill=badge_bg)
        draw.text(((x0 + x1) / 2.0, (y0 + y1) / 2.0), badge, font=b_font,
                  fill=badge_text_color or "#FFFFFF", anchor="mm")
    return img


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
