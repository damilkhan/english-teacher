# -*- coding: utf-8 -*-
"""ui.widgets.visualizer — полоски-эквалайзер.

Особенности после редизайна:
  * полоски окрашены градиентом акцент → циан (было — одним цветом);
  * ширина подстраивается под карточку (раньше была жёстко 400 px,
    поэтому на широком окне эквалайзер обрывался посередине).
"""

import tkinter as tk

import customtkinter as ctk

from ui import gradient


class AudioVisualizer(ctk.CTkFrame):
    def __init__(self, parent, palette, height=34, bars=28, bg_key="surface"):
        super().__init__(parent, fg_color="transparent", height=height)
        self.palette = palette
        self.height = height
        self.bars = bars
        self.bg_key = bg_key
        self.rects = []
        self._built_width = 0
        self._gap = 3
        self._bar_width = 4

        self.canvas = tk.Canvas(self, height=height, bg=palette[bg_key],
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", expand=True)
        self.bind("<Configure>", self._on_resize)

    # ---------- геометрия ----------
    def _on_resize(self, event):
        if abs(event.width - self._built_width) > 4:
            self._rebuild(event.width)

    def _bar_color(self, i):
        """Плавный переход акцент → циан слева направо."""
        t = 0.9 * (i / max(1, self.bars - 1))
        return gradient.lerp_hex(self.palette["accent"], self.palette["cyan"], t)

    def _rebuild(self, width):
        width = max(40, int(width))
        self.canvas.delete("all")
        self.rects = []
        self._built_width = width

        gap = 3
        bar = max(1, (width - gap * (self.bars + 1)) // self.bars)
        self._gap, self._bar_width = gap, bar

        for i in range(self.bars):
            x = gap + i * (bar + gap)
            rect = self.canvas.create_rectangle(
                x, self.height, x + bar, self.height,
                fill=self._bar_color(i), outline="")
            self.rects.append(rect)

    # ---------- анимация ----------
    def update_level(self, level):
        """level 0..100 — «громкость»; полоски растут от краёв к центру."""
        if not self.rects:
            self._rebuild(self._built_width or 400)
        import math
        h = self.height
        mid = (self.bars - 1) / 2
        for i, rect in enumerate(self.rects):
            # симметричный «горб» по центру — выглядит живее линейного роста
            shape = 0.30 + 0.70 * math.sin(math.pi * (i / max(1, self.bars - 1)))
            bar_height = int((level / 100) * (h - 2) * shape)
            bar_height = max(3, min(h, bar_height))
            x = self._gap + i * (self._bar_width + self._gap)
            self.canvas.coords(rect, x, h - bar_height,
                               x + self._bar_width, h)

    def reset(self):
        for i, rect in enumerate(self.rects):
            x = self._gap + i * (self._bar_width + self._gap)
            self.canvas.coords(rect, x, self.height, x + self._bar_width, self.height)

    # ---------- тема ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.canvas.configure(bg=palette[self.bg_key])
        self._rebuild(self._built_width or 400)
