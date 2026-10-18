# -*- coding: utf-8 -*-
"""ui.widgets.map_view — интерактивная карта прогресса (вкладка «Карта»).

Карта — это картинка локации (assets/map/desert.jpg), поверх которой лежат
КРУЖКИ-ЖЕТОНЫ по числу точек (блоков) из curriculum.json. Жетон показывает
номер точки и её состояние:

    * пройдено    — приглушённый зелёный + цифра;
    * активная    — яркий зелёный, плавно «дышит» (пульсирует) + цифра;
    * закрыто     — бордовый + цифра.

Цифры — белые с тёмным контуром (на цветной заливке иначе теряются).

Что важно помнить (грабли проекта):
  * картинку держим ссылкой (ImageTk.PhotoImage), иначе Tk её «съест»;
  * пересчёт картинки — только при изменении размера и с задержкой
    (debounce), чтобы не тормозить чат;
  * когда вкладка не видна, её размер ~1x1: рисовать «по событию» нельзя,
    поэтому отрисовка «ленивая» — по set_active(True);
  * жетоны рисуются Pillow-ом в 3x и уменьшаются (сглаживание краёв).

Чистые функции (масштаб, попадание, тексты, цвета) вынесены НАРУЖУ класса —
их удобно проверять тестами без живого Tk (см. tests/test_map_view.py).
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import customtkinter as ctk

import theme
from progress_map import ProgressMap, LOCKED, UNLOCKED, COMPLETED

_log = logging.getLogger(__name__)

# ---------- геометрия (в пикселях ИСХОДНОЙ картинки) ----------
TOKEN_RADIUS = 26          # радиус жетона на исходной карте (перекрывает белый кружок)
TOKEN_MIN_RADIUS = 8       # минимальный радиус в окне (чтобы жетон был виден)
PULSE_AMPLITUDE = 0.10     # «дыхание» активного жетона: ±10% радиуса
PULSE_PERIOD_MS = 1500     # полный цикл пульсации
PULSE_FRAME_MS = 45        # кадр анимации (~22 кадра в секунду)
RESIZE_DEBOUNCE_MS = 90    # задержка перерисовки при изменении размера
TOOLTIP_DELAY_MS = 220     # задержка перед показом подсказки
SS = 3                     # супер-сэмплинг для сглаживания жетонов

ARROW_STUB = "скоро"


# =========================================================
# Чистые функции (тестируются без Tk)
# =========================================================
def display_size(src_size: Sequence[int],
                 box_size: Sequence[int]) -> Tuple[int, int]:
    """Размер картинки, вписанной в рамку С СОХРАНЕНИЕМ пропорций.

    Возвращает (ширина, высота) в пикселях окна; картинка целиком
    помещается в box_size (letterbox по большей стороне).
    """
    sw, sh = max(1, int(src_size[0])), max(1, int(src_size[1]))
    bw, bh = max(1, int(box_size[0])), max(1, int(box_size[1]))
    scale = min(bw / float(sw), bh / float(sh))
    return (max(1, int(round(sw * scale))), max(1, int(round(sh * scale))))


def fit_scale(src_size: Sequence[int], box_size: Sequence[int]) -> float:
    """Коэффициент масштаба картинки под рамку (см. display_size)."""
    sw, sh = max(1, int(src_size[0])), max(1, int(src_size[1]))
    bw, bh = max(1, int(box_size[0])), max(1, int(box_size[1]))
    return min(bw / float(sw), bh / float(sh))


def scale_point(point: Sequence[int], scale: float,
                offset: Sequence[int] = (0, 0)) -> Tuple[int, int]:
    """Точка исходной картинки → координаты на экране (с учётом отступа)."""
    return (int(round(float(point[0]) * scale + float(offset[0]))),
            int(round(float(point[1]) * scale + float(offset[1]))))


def scaled_radius(radius: float, scale: float,
                  minimum: int = TOKEN_MIN_RADIUS) -> int:
    """Радиус жетона в окне (не меньше минимума)."""
    return max(int(minimum), int(round(float(radius) * float(scale))))


def hit_test(x: float, y: float, tokens: Sequence[Dict[str, Any]],
             radius: float) -> Optional[str]:
    """id точки под курсором (ближайшая в пределах radius) либо None.

    tokens: [{"id": ..., "x": ..., "y": ...}, ...] в координатах экрана.
    """
    best_id, best_d2 = None, float(radius) ** 2
    for tok in tokens or []:
        dx = float(x) - float(tok.get("x", 0))
        dy = float(y) - float(tok.get("y", 0))
        d2 = dx * dx + dy * dy
        if d2 <= best_d2:
            best_id, best_d2 = tok.get("id"), d2
    return best_id


def plural_ru(count: int, one: str = "урок", few: str = "урока",
              many: str = "уроков") -> str:
    """Русское склонение: 1 урок, 2 урока, 5 уроков."""
    n = abs(int(count))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return few
    return many


def tooltip_text(number: Any, title: str, lessons: int) -> str:
    """Текст подсказки жетона: «Блок 1: Greetings — 3 урока»."""
    head = "Блок %s" % number
    title = str(title or "").strip()
    if title:
        head += ": %s" % title
    return "%s — %d %s" % (head, int(lessons), plural_ru(lessons))


def state_colors(state: str, palette: Dict[str, Any]) -> Tuple[str, str]:
    """(заливка, контур цифры) для состояния жетона — из палитры темы.

    Неизвестное состояние трактуем как «закрыто».
    """
    if state == COMPLETED:
        return (palette.get("map_done", "#2E9E63"),
                palette.get("map_num_outline", "#0A3D26"))
    if state == UNLOCKED:
        return (palette.get("map_unlocked", "#4ADE80"),
                palette.get("map_num_outline", "#0A3D26"))
    return (palette.get("map_locked", "#8B223C"),
            palette.get("map_num_outline_locked", "#3A0814"))


def clamp_box(x: float, y: float, w: float, h: float,
              area_w: float, area_h: float,
              margin: int = 6) -> Tuple[int, int]:
    """Зажать прямоугольник подсказки внутри области (чтобы не уезжала)."""
    x = max(margin, min(float(x), float(area_w) - float(w) - margin))
    y = max(margin, min(float(y), float(area_h) - float(h) - margin))
    return (int(round(x)), int(round(y)))


def point_state_from(profile: Optional[Dict[str, Any]],
                     map_obj: ProgressMap, point_id: str) -> str:
    """Состояние точки по профилю (обёртка над ProgressMap, для удобства)."""
    return map_obj.get_point_state(point_id, profile)


# =========================================================
# Вспомогательное: шрифты и картинка-жетон
# =========================================================
_FONT_CACHE: Dict[Tuple[int, bool], Any] = {}


def _font(size: int, bold: bool = True):
    """Pillow-шрифт с кэшем. Если системного шрифта нет — встроенный."""
    key = (int(size), bool(bold))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    try:
        from PIL import ImageFont
    except Exception:
        return None
    names = ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "segoeui.ttf", "arial.ttf") \
        if bold else ("segoeui.ttf", "arial.ttf")
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    font = None
    for name in names:
        try:
            font = ImageFont.truetype(os.path.join(fonts_dir, name), size)
            break
        except Exception:
            continue
    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
    _FONT_CACHE[key] = font
    return font


def render_token(number: Any, state: str, radius: int,
                 palette: Dict[str, Any], glow: bool = False):
    """Нарисовать жетон (PIL.Image RGBA) с антиалиасингом.

    radius — радиус жетона в пикселях ОКНА (картинка рисуется в SS раз
    крупнее и уменьшается).
    """
    from PIL import Image, ImageDraw

    fill, outline = state_colors(state, palette)
    border = palette.get("map_border", "#FFFFFF")

    radius = max(3, int(radius))
    pad = int(radius * 0.55) + 6
    size = (radius + pad) * 2
    big = size * SS
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = big // 2
    rr = radius * SS

    # мягкое свечение у активной точки
    if glow:
        for k in range(9, 0, -1):
            alpha = int(70 * (k / 9.0))
            d.ellipse([c - rr - k * 4, c - rr - k * 4, c + rr + k * 4, c + rr + k * 4],
                      outline=_hex_rgb(fill) + (alpha,), width=4)

    # тень
    d.ellipse([c - rr + 3, c - rr + 4, c + rr + 3, c + rr + 4], fill=(0, 0, 0, 95))
    # белый ободок
    d.ellipse([c - rr - 5, c - rr - 5, c + rr + 5, c + rr + 5], fill=border)
    # заливка
    d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=fill)
    # блик сверху (лёгкий объём)
    try:
        hi = tuple(min(255, int(ch) + 34) for ch in _hex_rgb(fill))
        d.ellipse([c - rr + rr * 0.14, c - rr + rr * 0.10,
                   c + rr - rr * 0.14, c + rr - rr * 0.72], fill=hi + (78,))
    except Exception:
        pass

    # цифра
    if number is not None:
        f = _font(max(6, int(rr * 1.10)))
        text = str(number)
        stroke = max(2, int(rr * 0.14))
        if f is not None:
            box = d.textbbox((0, 0), text, font=f, stroke_width=stroke)
            d.text((c - (box[2] - box[0]) / 2.0 - box[0],
                    c - (box[3] - box[1]) / 2.0 - box[1]),
                   text, font=f, fill=(255, 255, 255, 255),
                   stroke_width=stroke, stroke_fill=_hex_rgb(outline))

    return im.resize((size, size), Image.LANCZOS)


def _hex_rgb(value: str) -> Tuple[int, int, int]:
    """'#RRGGBB' → (r, g, b). На плохом вводе — серый."""
    try:
        v = str(value).lstrip("#")
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except Exception:
        return (128, 128, 128)


# =========================================================
# Виджет
# =========================================================
class MapView(ctk.CTkFrame):
    """Карта локации: картинка + жетоны точек + подсказки + легенда."""

    def __init__(self, parent, palette, base_path: str = "knowledge_base",
                 location_id: str = "desert",
                 on_point_click: Optional[Callable[[str], None]] = None,
                 map_obj: Optional[ProgressMap] = None):
        super().__init__(parent, fg_color=palette.get("chat_bg", palette["surface"]),
                         corner_radius=theme.R["card"],
                         border_width=1, border_color=palette["border"])
        self.palette = palette
        self._on_point_click = on_point_click
        self.location_id = location_id

        # карту (ProgressMap) можно передать готовой — чтобы не читать
        # curriculum.json дважды, если её уже загрузил вызывающий код
        self.map = map_obj if map_obj is not None else ProgressMap(base_path)
        self._location = self.map.get_location(location_id) or {}

        self._active = False          # видна ли вкладка (анимация/отрисовка)
        self._scale = 1.0
        self._offset = (0, 0)
        self._map_photo = None        # держим ссылку на картинку карты
        self._token_photos: Dict[str, Any] = {}
        # ключ кэша: состояние + радиус + НОМЕР точки. Без номера все жетоны
        # одного состояния получали картинку ПЕРВОГО нарисованного (на карте
        # все точки были под «2» — грабли №36).
        self._token_cache: Dict[Tuple[str, int, Any], Any] = {}
        self._tokens: List[Dict[str, Any]] = []
        self._states: Dict[str, str] = {}
        self._item_map = None
        self._tip_job = None
        self._pulse_job = None
        self._phase = 0.0
        self._resize_job = None
        self._last_size = (0, 0)

        self._build()
        self.refresh(None)

    # ---------- сборка ----------
    def _build(self) -> None:
        p = self.palette
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(side="top", fill="x", padx=10, pady=(10, 4))
        self.title = ctk.CTkLabel(self.header, text="", anchor="w",
                                  font=(theme.FONT_PANEL_TITLE[0], 15, "bold"),
                                  text_color=p["text_strong"])
        self.title.pack(side="left")

        self.canvas = tk_canvas = _make_canvas(self, p)
        self.canvas.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 4))
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self._hide_tooltip())
        self.canvas.bind("<Button-1>", self._on_click)

        self.legend = ctk.CTkFrame(self, fg_color="transparent")
        self.legend.pack(side="bottom", fill="x", padx=10, pady=(0, 2))
        self._legend_photos: List[Any] = []

        self.nav = ctk.CTkFrame(self, fg_color="transparent")
        self.nav.pack(side="bottom", fill="x", padx=10, pady=(0, 8))
        self.prev_btn = ctk.CTkButton(self.nav, text="◀", width=44, height=30,
                                      state="disabled", font=theme.FONT_UI,
                                      fg_color=p["btn"], text_color=p["muted"],
                                      corner_radius=theme.R["button"],
                                      border_width=1, border_color=p["border"])
        self.prev_btn.pack(side="left")
        self.next_btn = ctk.CTkButton(self.nav, text="▶", width=44, height=30,
                                      state="disabled", font=theme.FONT_UI,
                                      fg_color=p["btn"], text_color=p["muted"],
                                      corner_radius=theme.R["button"],
                                      border_width=1, border_color=p["border"])
        self.next_btn.pack(side="left", padx=(8, 0))
        self.nav_hint = ctk.CTkLabel(self.nav, text="Другие локации — " + ARROW_STUB,
                                     font=theme.FONT_SMALL, text_color=p["muted"])
        self.nav_hint.pack(side="left", padx=(12, 0))

    # =====================================================
    # Данные / состояния
    # =====================================================
    def refresh(self, profile: Optional[Dict[str, Any]]) -> None:
        """Пересчитать состояния точек по профилю и перерисовать карту."""
        loc = self._location or {}
        points = self.map.points_of(self.location_id)
        self._states = {str(p.get("id")): self.map.get_point_state(p.get("id"), profile)
                        for p in points}
        done, total = self.map.get_location_progress(self.location_id, profile)
        title = loc.get("title") or "—"
        level = loc.get("level") or ""
        head = "%s · %s · %d/%d" % (title, level, done, total) if level \
            else "%s · %d/%d" % (title, done, total)
        try:
            self.title.configure(text=head)
        except Exception:
            pass
        self._build_legend()
        if self._active:
            self._redraw_map()
            self._restart_pulse()

    def apply_theme(self, palette: Dict[str, Any]) -> None:
        """Смена темы: перекрасить фон/тексты и перерисовать жетоны."""
        self.palette = palette
        p = palette
        self.configure(fg_color=p.get("chat_bg", p["surface"]),
                       border_color=p["border"])
        self.title.configure(text_color=p["text_strong"])
        self.canvas.configure(bg=p.get("map_bg", p["chat_bg"]))
        for btn in (self.prev_btn, self.next_btn):
            btn.configure(fg_color=p["btn"], text_color=p["muted"], border_color=p["border"])
        self.nav_hint.configure(text_color=p["muted"])
        self._token_cache.clear()
        self._map_photo = None
        self._hide_tooltip()
        self._build_legend()
        if self._active:
            self._redraw_map()

    def set_active(self, active: bool) -> None:
        """Вкладка видима? Отрисовка и пульсация — только когда видима."""
        active = bool(active)
        if active == self._active:
            return
        self._active = active
        if active:
            # вкладку Tk показывает с задержкой (~100 мс), поэтому одного
            # after_idle мало: canvas может быть ещё 1x1 — рисуем ещё раз
            self.after_idle(self._redraw_map)
            self.after(200, self._late_draw)
            self._restart_pulse()
        else:
            self._stop_pulse()
            self._hide_tooltip()

    # =====================================================
    # Отрисовка
    # =====================================================
    def _on_resize(self, _event=None) -> None:
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(RESIZE_DEBOUNCE_MS, self._resize_done)

    def _resize_done(self) -> None:
        self._resize_job = None
        if self._active:
            self._redraw_map()

    def _redraw_map(self) -> None:
        """Полная перерисовка: карта + все жетоны."""
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 40 or h < 40:
            return
        self._last_size = (w, h)
        self._hide_tooltip()
        self.canvas.delete("all")

        src = self._location.get("size") or [1248, 832]
        scale = fit_scale(src, (w, h))
        disp = display_size(src, (w, h))
        ox = (w - disp[0]) // 2
        oy = (h - disp[1]) // 2
        self._scale = scale
        self._offset = (ox, oy)

        photo = self._map_photo_image(disp)
        if photo is not None:
            self._map_photo = photo          # ссылку держим, иначе Tk заберёт
            self._item_map = self.canvas.create_image(ox, oy, anchor="nw", image=photo)

        # ---------- жетоны ----------
        self._tokens = []
        self._token_photos = {}
        radius = scaled_radius(TOKEN_RADIUS, scale)
        points = self.map.points_of(self.location_id)
        for point in points:
            pid = str(point.get("id"))
            px, py = scale_point(point.get("point") or [0, 0], scale, (ox, oy))
            state = self._states.get(pid, LOCKED)
            tk_id = self.canvas.create_image(px, py, anchor="center")
            self._tokens.append({"id": pid, "x": px, "y": py, "number": point.get("number"),
                                 "item": tk_id, "radius": radius,
                                 "title": point.get("block_title") or "",
                                 "lessons": len(self.map.lessons_of(pid))})
            self._paint_token(pid, radius, state)
        self._restart_pulse()

    def _map_photo_image(self, disp: Tuple[int, int]):
        """Картинка карты (со скруглением) как PhotoImage под размер окна."""
        from PIL import Image, ImageDraw, ImageTk
        w, h = max(1, disp[0]), max(1, disp[1])
        path = self._image_path()
        im = None
        if path:
            try:
                im = Image.open(path).convert("RGBA")
            except Exception as exc:
                _log.warning("Карта: не удалось открыть %s (%s)", path, exc)
                im = None
        if im is None:
            # картинки нет — нейтральный фон (карта не должна падать)
            im = Image.new("RGBA", (w, h), _hex_rgb(self.palette.get("map_bg", "#14161F")))
        else:
            im = im.resize((w, h), Image.LANCZOS)
            # скруглённые углы: маска по альфе
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1],
                                                   radius=theme.R["card"], fill=255)
            im.putalpha(mask)
        try:
            return ImageTk.PhotoImage(im)
        except Exception as exc:
            _log.warning("Карта: PhotoImage не создан (%s)", exc)
            return None

    def _image_path(self) -> str:
        """Путь к картинке локации (от корня проекта), либо пустая строка."""
        rel = str(self._location.get("image") or "")
        if not rel:
            return ""
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base, rel.replace("/", os.sep))

    def _paint_token(self, pid: str, radius: int, state: str) -> None:
        """Обновить картинку жетона (с кэшем по состоянию и радиусу)."""
        token = next((t for t in self._tokens if t["id"] == pid), None)
        if token is None:
            return
        key = (state, int(radius), token.get("number"))
        photo = self._token_cache.get(key)
        if photo is None:
            try:
                from PIL import ImageTk
            except Exception:
                return
            try:
                img = render_token(token.get("number"), state, radius, self.palette,
                                   glow=(state == UNLOCKED))
                photo = ImageTk.PhotoImage(img)
            except Exception as exc:
                _log.warning("Карта: жетон не нарисован (%s)", exc)
                return
            self._token_cache[key] = photo
        self._token_photos[pid] = photo      # держим ссылки на все жетоны
        try:
            self.canvas.itemconfigure(token["item"], image=photo)
        except Exception:
            pass

    def _late_draw(self) -> None:
        """Повторная отрисовка после показа вкладки (см. set_active)."""
        if self._active:
            self._redraw_map()

    # ---------- пульсация ----------
    def _restart_pulse(self) -> None:
        self._stop_pulse()
        if not self._active:
            return
        if not any(s == UNLOCKED for s in self._states.values()):
            return
        self._pulse_job = self.after(PULSE_FRAME_MS, self._pulse_tick)

    def _stop_pulse(self) -> None:
        if self._pulse_job is not None:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None

    def _pulse_tick(self) -> None:
        self._pulse_job = None
        if not self._active:
            return
        self._phase += (2.0 * math.pi * PULSE_FRAME_MS) / float(PULSE_PERIOD_MS)
        k = 1.0 + PULSE_AMPLITUDE * math.sin(self._phase)
        base = scaled_radius(TOKEN_RADIUS, self._scale)
        for pid, state in self._states.items():
            if state != UNLOCKED:
                continue
            radius = max(TOKEN_MIN_RADIUS, int(round(base * k)))
            self._paint_token(pid, radius, state)
        self._pulse_job = self.after(PULSE_FRAME_MS, self._pulse_tick)

    # ---------- tooltip ----------
    def _on_motion(self, event) -> None:
        pid = hit_test(event.x, event.y, self._tokens,
                       (self._tokens[0]["radius"] * 1.4) if self._tokens else 14)
        if pid:
            self._show_tooltip(pid)
        else:
            self._hide_tooltip()

    def _show_tooltip(self, pid: str) -> None:
        token = next((t for t in self._tokens if t["id"] == pid), None)
        if token is None:
            return
        text = tooltip_text(token.get("number"), token.get("title"), token.get("lessons", 0))
        f = _font(13, bold=False)
        p = self.palette
        self.canvas.delete("tooltip")
        # измерим текст «временным» элементом
        tmp = self.canvas.create_text(-1000, -1000, text=text, font=theme.FONT_SMALL)
        box = self.canvas.bbox(tmp)
        self.canvas.delete(tmp)
        tw = (box[2] - box[0]) if box else 120
        th = (box[3] - box[1]) if box else 18
        pad_x, pad_y = 12, 8
        w, h = tw + 2 * pad_x, th + 2 * pad_y
        x = token["x"] + 18
        y = token["y"] - h - 12
        cx, cy = clamp_box(x, y, w, h, self.canvas.winfo_width(), self.canvas.winfo_height())
        pts = _rounded_rect_points(cx, cy, cx + w, cy + h, 8)
        self.canvas.create_polygon(pts, smooth=True,
                                   fill=p.get("map_tooltip_bg", p["surface_alt"]),
                                   outline=p["border"], width=1, tags="tooltip")
        self.canvas.create_text(cx + w / 2.0, cy + h / 2.0, text=text,
                                font=theme.FONT_SMALL,
                                fill=p.get("map_tooltip_text", p["text"]), tags="tooltip")

    def _hide_tooltip(self) -> None:
        try:
            self.canvas.delete("tooltip")
        except Exception:
            pass

    # ---------- клик ----------
    def _on_click(self, event) -> None:
        pid = hit_test(event.x, event.y, self._tokens,
                       (self._tokens[0]["radius"] * 1.4) if self._tokens else 14)
        if not pid:
            return
        if self._on_point_click:
            try:
                self._on_point_click(pid)
            except Exception as exc:
                _log.warning("Карта: ошибка обработчика клика (%s)", exc)

    # ---------- легенда ----------
    def _build_legend(self) -> None:
        for child in self.legend.winfo_children():
            child.destroy()
        self._legend_photos = []
        p = self.palette
        items = [(COMPLETED, "пройдено"), (UNLOCKED, "активный"), (LOCKED, "закрыто")]
        for state, label in items:
            row = ctk.CTkFrame(self.legend, fg_color="transparent")
            row.pack(side="left", padx=(0, 16))
            try:
                # для CTkLabel нужен именно CTkImage (иначе предупреждение
                # и «замыленная» картинка на HiDPI)
                img = render_token(1, state, 11, p, glow=False)
                photo = ctk.CTkImage(light_image=img, dark_image=img,
                                     size=(img.width, img.height))
                self._legend_photos.append(photo)
                icon = ctk.CTkLabel(row, text="", image=photo)
                icon.pack(side="left", padx=(0, 6))
            except Exception:
                pass
            ctk.CTkLabel(row, text=label, font=theme.FONT_SMALL,
                         text_color=p["muted"]).pack(side="left")

    # ---------- жизненный цикл ----------
    def destroy(self) -> None:
        self._stop_pulse()
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
            self._resize_job = None
        self._token_cache.clear()
        self._token_photos.clear()
        super().destroy()


# =========================================================
# Мелочи Tk
# =========================================================
def _make_canvas(parent, palette):
    """Canvas без рамки, фон — под карточку (скруглённые углы не «бьют»)."""
    import tkinter as tk
    return tk.Canvas(parent, highlightthickness=0, bd=0,
                     bg=palette.get("map_bg", palette.get("chat_bg", "#14161F")))


def _rounded_rect_points(x1: float, y1: float, x2: float, y2: float,
                         r: float) -> List[float]:
    """Точки для create_polygon(smooth=True) — «скруглённый» прямоугольник."""
    r = max(0.0, min(float(r), (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
