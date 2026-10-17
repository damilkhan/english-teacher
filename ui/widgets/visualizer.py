# -*- coding: utf-8 -*-
"""ui.widgets.visualizer — пиксельный эквалайзер «кто говорит».

Особенности:
  * полоски нарисованы КВАДРАТИКАМИ (как LED-матрица) — «пиксельный» вид;
  * цвет зависит от говорящего: Джейн — фиолетово-циан, вы — зелёно-циан;
  * шкала симметричная («горб» к центру), поэтому столбики выглядят живее.

ВАЖНО: виджет только РИСУЕТ. Уровень ему передают снаружи:
    visualizer.update_level(level_0_100, speaker="jane"|"user")
"""

import tkinter as tk

import customtkinter as ctk

from ui import gradient

# Кто говорит → пара цветов градиента (левый край → правый край).
SPEAKER_COLORS = {
    "jane": ("accent", "cyan"),
    "user": ("ok", "cyan"),
}
DEFAULT_SPEAKER = "jane"


class AudioVisualizer(ctk.CTkFrame):
    def __init__(self, parent, palette, height=34, bars=28, bg_key="surface"):
        super().__init__(parent, fg_color="transparent", height=height)
        self.palette = palette
        self.height = height
        self.bars = bars
        self.bg_key = bg_key
        self.cells = []            # [ [(rect_id, y_top), ...], ... ] по столбикам
        self._built_width = 0
        self._gap = 3
        self._bar_width = 4
        self._segment = 4          # высота «пикселя»
        self._seg_gap = 1          # зазор между пикселями
        self._speaker = DEFAULT_SPEAKER
        self._level = 0.0

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

    def _bar_color(self, i):
        """Плавный переход слева направо для текущего говорящего."""
        left, right = self._colors()
        t = 0.9 * (i / max(1, self.bars - 1))
        return gradient.lerp_hex(left, right, t)

    def _dim_color(self):
        """Цвет «погасших» пикселей (видно матрицу даже в тишине)."""
        return self.palette.get("btn", "#222735")

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

        segment = self._segment
        step = segment + self._seg_gap
        count = max(2, (self.height - 2) // step)
        dim = self._dim_color()

        for i in range(self.bars):
            x = gap + i * (bar + gap)
            column = []
            for k in range(count):
                y = self.height - (k + 1) * step
                rect = self.canvas.create_rectangle(
                    x, y, x + bar, y + segment, fill=dim, outline="")
                column.append(rect)
            self.cells.append(column)
        self.update_level(self._level, self._speaker)

    # ---------- анимация ----------
    def update_level(self, level, speaker=None):
        """level 0..100; speaker — 'jane' или 'user' (меняет цвет)."""
        if speaker in SPEAKER_COLORS:
            changed = speaker != self._speaker
            self._speaker = speaker
            if changed:
                self._recolor()
        try:
            self._level = max(0.0, min(100.0, float(level)))
        except (TypeError, ValueError):
            self._level = 0.0

        if not self.cells:
            self._rebuild(self._built_width or 400)
            return

        import math
        count = len(self.cells[0]) if self.cells else 0
        mid = (self.bars - 1) / 2
        for i, column in enumerate(self.cells):
            # симметричный «горб» по центру — выглядит живее линейного роста
            shape = 0.30 + 0.70 * math.sin(math.pi * (i / max(1, self.bars - 1)))
            height_ratio = min(1.0, (self._level / 100.0) * shape * 1.6)
            lit = int(round(count * height_ratio))
            for k, rect in enumerate(column):
                fill = self._bar_color(i) if k < lit else self._dim_color()
                self.canvas.itemconfigure(rect, fill=fill)

    def _recolor(self):
        """Перекрасить видимые пиксели при смене говорящего."""
        self.update_level(self._level, None)

    def reset(self):
        """Погасить все пиксели (звука нет)."""
        self._level = 0.0
        if not self.cells:
            return
        dim = self._dim_color()
        for column in self.cells:
            for rect in column:
                self.canvas.itemconfigure(rect, fill=dim)

    # ---------- тема ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.canvas.configure(bg=palette[self.bg_key])
        self._built_width = 0
        self._rebuild(400)
