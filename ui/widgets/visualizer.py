# -*- coding: utf-8 -*-
"""ui.widgets.visualizer — пиксельный эквалайзер «кто говорит».

Особенности:
  * полоски нарисованы КВАДРАТИКАМИ (как LED-матрица) — «пиксельный» вид;
  * цвет зависит от говорящего: Джейн — фиолетово-циан, вы — зелёно-циан;
  * шкала симметричная («горб» к центру), поэтому столбики выглядят живее.

СКОРОСТЬ (важно). Раньше на каждый тик перекрашивались ВСЕ квадратики
(150 вызовов Tk за кадр ~ 5-14 мс) — из-за этого эквалайзер «лагал».
Теперь:
  * цвета и «форма» столбиков считаются один раз (при создании/смене темы);
  * у каждого столбика помним, сколько квадратиков горит, и трогаем ТОЛЬКО
    изменившиеся (обычно 5-25 вместо 150);
  * если уровень почти не изменился — не делаем вообще ничего.

ВАЖНО: виджет только РИСУЕТ. Уровень ему передают снаружи:
    visualizer.update_level(level_0_100, speaker="jane"|"user")
"""

import math
import tkinter as tk

import customtkinter as ctk

from ui import gradient

# Кто говорит → пара цветов градиента (левый край → правый край).
SPEAKER_COLORS = {
    "jane": ("accent", "cyan"),
    "user": ("ok", "cyan"),
}
DEFAULT_SPEAKER = "jane"

# Уровень меняется плавно — незачем перерисовывать отличия меньше этого.
LEVEL_EPSILON = 0.4
# Сглаживание как у настоящего индикатора (VU-метр): вверх — быстро
# (иначе видно «запаздывание» звука), вниз — плавно (без дёрганья).
LEVEL_ATTACK = 0.85      # громче стало — почти мгновенно
LEVEL_RELEASE = 0.32     # тише стало — мягкий спад


class AudioVisualizer(ctk.CTkFrame):
    def __init__(self, parent, palette, height=34, bars=28, bg_key="surface"):
        super().__init__(parent, fg_color="transparent", height=height)
        self.palette = palette
        self.height = height
        self.bars = bars
        self.bg_key = bg_key

        self.cells = []            # [[rect_id, ...], ...] по столбикам
        self._built_width = 0
        self._gap = 3
        self._bar_width = 4
        self._segment = 4          # высота «пикселя»
        self._seg_gap = 1          # зазор между пикселями
        self._speaker = DEFAULT_SPEAKER
        self._level = 0.0

        # --- предвычисленное (обновляется при пересборке/смене цвета) ---
        self._cell_count = 0
        self._shapes = []          # «горб» каждого столбика
        self._lit_colors = []      # цвет горящего квадратика в столбике
        self._dim = palette.get("btn", "#222735")
        self._lit_now = []         # сколько квадратиков горит сейчас

        self.canvas = tk.Canvas(self, height=height, bg=palette[bg_key],
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", expand=True)
        self.bind("<Configure>", self._on_resize)

    # ---------- геометрия ----------
    def _on_resize(self, event):
        if abs(event.width - self._built_width) > 4:
            self._rebuild(event.width)

    def _colors(self):
        """(низкий цвет, высокий цвет) для текущего говорящего."""
        left_key, right_key = SPEAKER_COLORS.get(self._speaker,
                                                 SPEAKER_COLORS[DEFAULT_SPEAKER])
        return (self.palette.get(left_key, self.palette["accent"]),
                self.palette.get(right_key, self.palette["cyan"]))

    def _recompute_colors(self):
        """Цвета столбиков и «форма» горба — один раз на пересборку/тему."""
        left, right = self._colors()
        last = max(1, self.bars - 1)
        self._lit_colors = [gradient.lerp_hex(left, right, 0.9 * (i / last))
                            for i in range(self.bars)]
        self._shapes = [0.30 + 0.70 * math.sin(math.pi * (i / last))
                        for i in range(self.bars)]
        self._dim = self.palette.get("btn", "#222735")

    def _rebuild(self, width):
        width = max(40, int(width))
        if abs(width - (self._built_width or 0)) < 4 and self.cells:
            return
        self.canvas.delete("all")
        self.cells = []
        self._built_width = width

        gap = 3
        bar = max(2, (width - gap * (self.bars + 1)) // self.bars)
        self._gap, self._bar_width = gap, bar

        step = self._segment + self._seg_gap
        count = max(2, (self.height - 2) // step)
        self._cell_count = count

        self._recompute_colors()
        dim = self._dim

        for i in range(self.bars):
            x = gap + i * (bar + gap)
            column = []
            for k in range(count):
                y = self.height - (k + 1) * step
                column.append(self.canvas.create_rectangle(
                    x, y, x + bar, y + self._segment, fill=dim, outline=""))
            self.cells.append(column)

        self._lit_now = [0] * self.bars
        self._paint(force=True)

    # ---------- анимация ----------
    def update_level(self, level, speaker=None):
        """level 0..100; speaker — 'jane' или 'user' (меняет цвет)."""
        if speaker in SPEAKER_COLORS and speaker != self._speaker:
            self._speaker = speaker
            self._recompute_colors()
            self._paint(force=True)          # цвета поменялись — перекрасить всё

        try:
            level = max(0.0, min(100.0, float(level)))
        except (TypeError, ValueError):
            level = 0.0

        if not self.cells:
            self._rebuild(self._built_width or 400)
            return

        # сглаживание: вверх — быстро, вниз — плавно (как VU-метр)
        target = level
        diff = target - self._level
        if abs(diff) < LEVEL_EPSILON:
            return                           # ничего не изменилось — не трогаем Tk
        k = LEVEL_ATTACK if diff > 0 else LEVEL_RELEASE
        self._level += diff * k
        if abs(target - self._level) < LEVEL_EPSILON:
            self._level = target
        self._paint()

    def _paint(self, force=False):
        """Показать текущий уровень: трогаем только изменившиеся квадратики."""
        if not self.cells:
            return
        count = self._cell_count
        level = self._level
        conf = self.canvas.itemconfigure
        lit_colors = self._lit_colors
        cells = self.cells
        lit_now = self._lit_now
        dim = self._dim

        for i, column in enumerate(cells):
            # симметричный «горб» по центру — выглядит живее линейного роста
            ratio = (level / 100.0) * self._shapes[i] * 1.6
            lit = count if ratio >= 1.0 else int(round(count * ratio))

            if force:
                # полная перекраска (смена темы/говорящего): красим ВСЁ —
                # и горящие (новым цветом), и погасшие
                color = lit_colors[i]
                for k in range(count):
                    conf(column[k], fill=color if k < lit else dim)
                lit_now[i] = lit
                continue

            prev = lit_now[i]
            if lit == prev:
                continue
            if lit > prev:                   # зажглись новые
                color = lit_colors[i]
                for k in range(prev, lit):
                    conf(column[k], fill=color)
            else:                            # погасли верхние
                for k in range(lit, prev):
                    conf(column[k], fill=dim)
            lit_now[i] = lit

    def reset(self):
        """Погасить все пиксели (звука нет)."""
        self._level = 0.0
        if not self.cells:
            return
        dim = self._dim
        conf = self.canvas.itemconfigure
        for i, column in enumerate(self.cells):
            if not self._lit_now[i]:
                continue
            for rect in column[:self._lit_now[i]]:
                conf(rect, fill=dim)
            self._lit_now[i] = 0

    # ---------- тема ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.canvas.configure(bg=palette[self.bg_key])
        self._built_width = 0
        self._rebuild(400)
