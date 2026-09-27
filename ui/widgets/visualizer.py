# -*- coding: utf-8 -*-
"""ui.widgets.visualizer — полоски-эквалайзер под заголовком."""

import tkinter as tk

import customtkinter as ctk


class AudioVisualizer(ctk.CTkFrame):
    def __init__(self, parent, palette, width=400, height=80, bars=20):
        super().__init__(parent, fg_color="transparent")
        self.palette = palette
        self.width = width
        self.height = height
        self.bars = bars
        self.bar_width = max(2, width // self.bars - 2)

        self.canvas = tk.Canvas(self, width=width, height=height,
                                bg=palette["chat_bg"], highlightthickness=0)
        self.canvas.pack()
        self.rects = []
        self.create_bars()

    def create_bars(self):
        for i in range(self.bars):
            x = i * (self.bar_width + 2) + 2
            rect = self.canvas.create_rectangle(
                x, self.height, x + self.bar_width, self.height,
                fill=self.palette["accent"], outline="")
            self.rects.append(rect)

    def update_level(self, level):
        h = self.height
        for i, rect in enumerate(self.rects):
            bar_height = int((level / 100) * h * ((i + 1) / self.bars))
            bar_height = max(2, min(h, bar_height))
            x = i * (self.bar_width + 2) + 2
            self.canvas.coords(rect, x, h - bar_height, x + self.bar_width, h)

    def reset(self):
        for i, rect in enumerate(self.rects):
            x = i * (self.bar_width + 2) + 2
            self.canvas.coords(rect, x, self.height, x + self.bar_width, self.height)

    def apply_theme(self, palette):
        self.palette = palette
        self.canvas.configure(bg=palette["chat_bg"])
        for rect in self.rects:
            self.canvas.itemconfig(rect, fill=palette["accent"])
