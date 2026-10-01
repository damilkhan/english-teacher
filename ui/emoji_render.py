# -*- coding: utf-8 -*-
# =========================================================
# UI/EMOJI_RENDER.PY — цветные эмодзи для tk.Text
# =========================================================
# Почему понадобился модуль:
#   Tk умеет рисовать текст ТОЛЬКО одним цветом, поэтому цветной глиф из
#   seguiemj.ttf он выводит однотонным контуром. На тёмной теме такие эмодзи
#   почти не видны, а Джейн по промпту (prompt_builder.EMOJIS) сыпет их
#   в каждой реплике — чат выглядел бледным.
#
# Что делает:
#   рисует каждый эмодзи Pillow'ом (embedded_color=True берёт цветные глифы
#   COLR из seguiemj.ttf) и отдаёт картинку с ПРОЗРАЧНЫМ фоном. chat_view
#   вставляет её в tk.Text командой image_create: картинка ложится в строку
#   как обычный символ и одинаково смотрится и на тёмной, и на светлой теме.
#
# Модуль ничего не знает про виджеты: он отдаёт PIL-картинки и кэширует их
# как tk.PhotoImage. Если Pillow или эмодзи-шрифта нет — chat_view просто
# пишет текст, как раньше. Составные эмодзи (👍🏽, 👨‍👩‍👧) без libraqm
# рисуются по базовому символу — подробности в _simplify().
#
# Не всякий значок становится картинкой. Текстом остаются значки, которые
# шрифт отдаёт однотонными (💬 🗑 ▪) или которые сольются с фоном чата
# (🖤 🌑 🤍 💀) — за это отвечают _has_color() и _visible(). В обоих случаях
# проигрыша нет: Tk нарисует символ цветом темы, и он читается.
# =========================================================

import os
import re

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_READY = True
except Exception:          # нет Pillow — эмодзи останутся текстом
    Image = ImageDraw = ImageFont = None
    _PIL_READY = False

try:
    # Raqm умеет «склеивать» составные эмодзи (👨‍👩‍👧, 👍🏽). В сборке Pillow
    # для Windows её обычно НЕТ — тогда рисуем по базовому символу, см. _simplify().
    from PIL import features as _pil_features
    _SHAPING = bool(_pil_features.check("raqm"))
except Exception:
    _SHAPING = False


# ---------------------------------------------------------
# Размеры
# ---------------------------------------------------------
DEFAULT_PX = 18            # запасной размер, если метрики шрифта не спросить
MIN_PX = 12
MAX_PX = 48

# Как картинка выравнивается по строке. «baseline» — низ эмодзи стоит на
# базовой линии, как у заглавной буквы: так он выглядит частью текста,
# а не приклеенным к строке значком.
ALIGN = "baseline"


def size_from_font(points, scaling=1.0):
    """Размер картинки-эмодзи по шрифту чата: примерно «em» этого шрифта.

    Важно брать именно em, а не высоту строки: linespace у Segoe UI Emoji
    14 pt — это 26 px (вместе с межстрочным интервалом), и эмодзи такого
    размера распухал бы каждую реплику по высоте.
    """
    try:
        px = int(round(float(points) * float(scaling)))
    except (TypeError, ValueError):
        return DEFAULT_PX
    return max(MIN_PX, min(MAX_PX, px))


# ---------------------------------------------------------
# Что считать эмодзи
# ---------------------------------------------------------
# Основные «эмодзи-пласты» Unicode. Диапазоны взяты с запасом: если символ
# окажется обычным (текстовым) глифом, его отсеет проверка цвета — см.
# _has_color().
_RANGES = (
    "\U0001F000-\U0001FAFF"    # 😀👍🎉🚀🇷🇺🫶 — весь основной пласт эмодзи
    "\U00002600-\U000027BF"    # ☀✔✨✅ — «прочие символы» и дингбаты
    "\U00002B00-\U00002BFF"    # ⭐⬅⬆➡
    "\U0000231A-\U000023FA"    # ⌚⏳⏩ — время и кнопки плеера («⏳» есть в app.py)
    "\U000025AA-\U000025AB\U000025B6\U000025C0\U000025FB-\U000025FE"  # ▪▫▶◀◻◼
    "\U00002934\U00002935"     # ⤴⤵
    "\U0000203C\U00002049"     # ‼⁉
    "\U00002122\U00002139"     # ™ℹ
    "\U000024C2"               # Ⓜ
    "\U00003030\U0000303D\U00003297\U00003299"   # 〰〽㊗㊙
)

_ZWJ = "\u200D"                         # склейка последовательностей (👨‍👩‍👧)
_SELECTORS = "\uFE0E\uFE0F"             # «эмодзи-вид» / «тексто-вид»
_SKIN = "\U0001F3FB-\U0001F3FF"         # оттенки кожи 👍🏻
_SKIN_RE = re.compile("[" + _SKIN + "]")
_KEYCAP = "[\u0023\u002A0-9]\uFE0F?\u20E3"      # 1️⃣ #️⃣ *️⃣
_FLAGS = "[\U0001F1E6-\U0001F1FF]{2}"           # 🇷🇺 — пара региональных индикаторов

_BASE = "[" + _RANGES + "]"
_MOD = "[" + _SELECTORS + _SKIN + "]"
# база + модификаторы + любые «склейки» через ZWJ: 😀, 😀️, 👍🏽, 👨‍👩‍👧
_CLUSTER = _BASE + "(?:" + _MOD + "|" + _ZWJ + _BASE + _MOD + "?)*"

EMOJI_RE = re.compile("(?:" + _KEYCAP + ")|(?:" + _FLAGS + ")|(?:" + _CLUSTER + ")")


def split(text):
    """Делит строку на куски: [(True, "😊"), (False, "Привет "), …].

    Нужна потому, что эмодзи в tk.Text вставляется картинкой, а обычный
    текст — как текст: смешанную строку приходится резать на части.
    """
    if not text:
        return []
    parts = []
    last = 0
    for match in EMOJI_RE.finditer(text):
        if match.start() > last:
            parts.append((False, text[last:match.start()]))
        parts.append((True, match.group(0)))
        last = match.end()
    if last < len(text):
        parts.append((False, text[last:]))
    return parts


def has_emoji(text):
    """Есть ли в строке эмодзи (по тем же правилам, что и split)."""
    return bool(text) and EMOJI_RE.search(text) is not None


# ---------------------------------------------------------
# Шрифт
# ---------------------------------------------------------
# Ищем первым делом цветной шрифт Windows: только он даёт цветные глифы.
_FONT_FILES = (
    "seguiemj.ttf",          # Windows: Segoe UI Emoji
    "SegoeUIEmoji.ttf",
    "NotoColorEmoji.ttf",    # Linux
    "AppleColorEmoji.ttc",   # macOS
    "NotoEmoji-Regular.ttf", # чёрно-белые, но лучше, чем ничего
    "Symbola.ttf",
)

_FONT_PATH = False           # False = «ещё не искали», None = «не нашли»
_FONTS = {}                  # размер → ImageFont (шрифт грузится недёшево)


def _font_dirs():
    dirs = []
    win = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if win:
        dirs.append(os.path.join(win, "Fonts"))
    local = os.environ.get("LOCALAPPDATA")
    if local:                # шрифты, поставленные «для пользователя»
        dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    dirs += [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.local/share/fonts"),
        "/System/Library/Fonts",
    ]
    return dirs


def _find_font():
    # Явный путь из окружения: удобно, если шрифт лежит не в системе
    env = os.environ.get("ENGLISH_TEACHER_EMOJI_FONT")
    if env and os.path.exists(env):
        return env
    for folder in _font_dirs():
        for name in _FONT_FILES:
            path = os.path.join(folder, name)
            if os.path.exists(path):
                return path
        # Linux часто раскладывает шрифты по подпапкам (truetype/noto/…)
        for sub in ("truetype/noto", "truetype", "noto", "TTF"):
            for name in _FONT_FILES:
                path = os.path.join(folder, sub, name)
                if os.path.exists(path):
                    return path
    return None


def emoji_font_path():
    """Путь к эмодзи-шрифту или None. Ищем один раз за запуск."""
    global _FONT_PATH
    if _FONT_PATH is False:
        _FONT_PATH = _find_font()
    return _FONT_PATH


def load_font(size, cache=None):
    """ImageFont нужного размера (с кэшем: truetype открывается медленно)."""
    if not _PIL_READY:
        return None
    try:
        size = int(size)
    except (TypeError, ValueError):
        return None
    if size <= 0:
        return None
    cache = _FONTS if cache is None else cache
    font = cache.get(size)
    if font is None:
        path = emoji_font_path()
        if path is None:
            return None
        try:
            font = ImageFont.truetype(path, size)
        except Exception as exc:
            print(f"⚠️ Шрифт эмодзи не открылся ({path}): {exc}")
            return None
        cache[size] = font
    return font


def available():
    """Есть ли чем рисовать цветные эмодзи (для журнала при старте)."""
    return _PIL_READY and emoji_font_path() is not None


# ---------------------------------------------------------
# Проверки «годится ли картинка»
# ---------------------------------------------------------
def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _linear(channel):
    """Канал 0-255 → линейная яркость (как в формуле контраста WCAG)."""
    value = channel / 255.0
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def _rel_luminance(rgb):
    r, g, b = (_linear(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(color, background):
    a, b = _rel_luminance(color), _rel_luminance(background)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# Фоны чата, на которых эмодзи обязан читаться. Значения берём из theme.py
# (единственный источник цветов), с запасным вариантом на случай, если модуль
# применили отдельно от проекта. Картинки кэшируются без привязки к теме,
# поэтому проверяем сразу обе палитры.
_BG_FALLBACK = ("#14161F", "#FAFBFE")


def _backgrounds():
    try:
        import theme
        return tuple(theme.palette(name)["chat_bg"] for name in ("dark", "light"))
    except Exception:
        return _BG_FALLBACK


def _has_color(ink, threshold=20):
    """True, если в картинке есть цветные пиксели.

    Segoe UI Emoji часть значков отдаёт однотонными: одни приходят оттенками
    серого (💬 🗑 ▪▫), другие рисуются простым контуром. На тёмной теме серый
    значок — то же невидимое пятно, что и до модуля, поэтому такие лучше
    оставить текстом: Tk покрасит их в цвет темы.
    """
    colors = ink.convert("RGB").getcolors(maxcolors=1 << 12)
    if colors is None:               # цветов больше лимита → точно цветной
        return True
    for _count, (r, g, b) in colors:
        if max(r, g, b) - min(r, g, b) > threshold:
            return True
    return False


def _visible(ink, need=1.9):
    """Читается ли значок на ФОНЕ ЧАТА — и на тёмной, и на светлой теме.

    Есть эмодзи, которые не видны на одном из фонов: 🖤 🌑 🎓 тёмные,
    🤍 💀 светлые. На тёмной теме чёрный глиф становится невидимым пятном —
    то есть ровно той проблемой, из-за которой этот модуль и появился. Такие
    значки отдаём текстом: Tk нарисует их цветом темы.

    Считаем не яркость, а КОНТРАСТ с фоном: насыщенный красный ❌ на тёмном
    фоне имеет низкую яркость, но виден отлично — по порогу яркости он
    отсеивался бы зря.

    Порог намеренно низкий (1.9): золотая звезда ⭐ на почти белом фоне даёт
    всего ~2.0, но глазом различима. Отсекаются значки с контрастом около
    1.0-1.6 — те, что действительно сливаются.
    """
    try:
        from PIL import ImageStat
        mean = ImageStat.Stat(ink.convert("RGB"), ink.split()[-1]).mean
        color = tuple(mean)
        return all(_contrast(color, hex_to_rgb(bg)) >= need
                   for bg in _backgrounds())
    except Exception:
        return True                      # не смогли посчитать — не мешаем


def _simplify(token):
    """Упрощает последовательность, если Pillow не умеет склеивать эмодзи.

    Без libraqm (её нет в windows-сборке Pillow) составные эмодзи не
    собираются в один глиф: 👍🏽 нарисовался бы как «👍 + коричневый
    квадратик», а 👨‍👩‍👧 — как три человечка подряд шириной 70 px, что
    вылезает из строки. Поэтому рисуем базовый символ: картинка выходит
    одна и аккуратная.

    Исходный символ при этом НЕ теряется: chat_view помнит его отдельно
    (self._image_tokens) и возвращает в get_text() строку целиком.
    """
    if _SHAPING:
        return token
    base = token.split(_ZWJ)[0]
    return _SKIN_RE.sub("", base) or base


# ---------------------------------------------------------
# Отрисовка
# ---------------------------------------------------------
def render(token, size, fonts=None):
    """Рисует один эмодзи в RGBA-картинку, обрезанную по «чернилам».

    None означает «рисуй текстом»: нет Pillow или шрифта, глиф не нарисовался,
    вышел однотонным или сольётся с фоном чата. Вызывающий код обязан уметь
    обойтись без картинки.
    """
    if not _PIL_READY or not token:
        return None
    font = load_font(size, fonts)
    if font is None:
        return None
    size = max(MIN_PX, int(size))
    pad = max(2, size // 4)
    # холст берём с запасом: ZWJ-последовательность (👨‍👩‍👧) шире одного глифа,
    # лишнее отрежет crop по чернилам
    canvas = Image.new("RGBA", ((len(token) + 2) * size * 2, size * 3), (0, 0, 0, 0))
    try:
        ImageDraw.Draw(canvas).text((pad, pad), _simplify(token),
                                    font=font, embedded_color=True)
    except TypeError:                # Pillow без поддержки цветных шрифтов
        return None
    except Exception as exc:
        print(f"⚠️ Эмодзи {token!r} не нарисовался: {exc}")
        return None
    box = canvas.getbbox()
    if box is None:                  # пусто: шрифт не знает такой значок
        return None
    ink = canvas.crop(box)
    if not _has_color(ink) or not _visible(ink):
        return None                  # однотонный или сольётся с фоном
    return ink


# ---------------------------------------------------------
# Кэш картинок для tk.Text
# ---------------------------------------------------------
class EmojiImages:
    """Эмодзи → tk.PhotoImage, с кэшем по символу.

    Кэш обязателен по двум причинам: рисовать один и тот же 😊 на каждое
    сообщение — лишние миллисекунды, и, что важнее, Tk НЕ держит ссылку на
    PhotoImage: если её не сохранить, сборщик мусора съест картинку и в чате
    останутся пустые места.
    """

    def __init__(self, size=DEFAULT_PX, master=None):
        self.size = int(size)
        self.master = master
        self._photos = {}            # символ → PhotoImage
        self._fonts = {}             # размер → ImageFont
        self._missing = set()        # символы, которые рисовать нечем
        self.stats = {"render": 0, "reuse": 0, "miss": 0}

    def set_size(self, size):
        """Сменить размер картинок (нужен другой шрифт чата)."""
        size = int(size)
        if size != self.size:
            self.size = size
            self._missing.clear()    # у другого размера проверки те же,
            self.clear()             # но пусть решает сам render()

    def clear(self):
        """Забыть картинки (текст чата стёрли). Кэш шрифтов не трогаем.

        Список «не рисуется» оставляем: причина (нет цветного глифа, не
        хватает контраста) от содержимого чата не зависит, а повторная
        отрисовка на каждое сообщение — только лишняя работа.
        """
        self._photos.clear()

    def photo(self, token, master=None):
        """PhotoImage для эмодзи или None, если рисовать нечем."""
        photo = self._photos.get(token)
        if photo is not None:
            self.stats["reuse"] += 1
            return photo
        if token in self._missing:
            self.stats["miss"] += 1
            return None

        ink = render(token, self.size, self._fonts)
        if ink is None:
            self._missing.add(token)
            self.stats["miss"] += 1
            return None
        try:
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(ink, master=master or self.master)
        except Exception as exc:
            self._missing.add(token)
            self.stats["miss"] += 1
            print(f"⚠️ Эмодзи {token!r} не удалось показать в Tk: {exc}")
            return None
        self._photos[token] = photo
        self.stats["render"] += 1
        return photo
