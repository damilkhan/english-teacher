# -*- coding: utf-8 -*-
"""ui.widgets.chat_view — область чата.

Раньше add_message() в gui.py уходил в `pass` (WebView так и не создавался),
и в окне не появлялось ни одного сообщения. Здесь это нормальный метод.
"""

import tkinter as tk
from datetime import datetime

import customtkinter as ctk

import theme

GREETING = ("Джейн: Привет! Я твой преподаватель английского.\n"
            "Я буду запоминать твои ошибки и подстраивать уроки под тебя.\n\n")

USER_SENDERS = ("Вы", "Вы (голос)")


class ChatView(ctk.CTkFrame):
    def __init__(self, parent, palette, height=400, greeting=GREETING):
        super().__init__(parent, fg_color=palette["chat_bg"], corner_radius=12, height=height)
        self.pack_propagate(False)
        self.palette = palette

        self.inner = ctk.CTkFrame(self, fg_color=palette["chat_bg"])
        self.inner.pack(fill="both", expand=True, padx=5, pady=5)

        self.text = tk.Text(
            self.inner,
            wrap="word",
            font=theme.FONT_BODY,
            bg=palette["chat_bg"],
            fg=palette["text"],
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
        )
        self.text.pack(side="left", fill="both", expand=True)

        self.scrollbar = ctk.CTkScrollbar(self.inner, command=self.text.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=self.scrollbar.set)

        self._configure_tags(palette)
        if greeting:
            self.text.insert("0.0", greeting)
        self.text.configure(state="disabled")

    # ---------- API ----------
    def add_message(self, sender, text, stamp=None):
        """Рисует реплику и прокручивает чат вниз."""
        is_user = sender in USER_SENDERS
        stamp = stamp or datetime.now().strftime("%H:%M")
        self.text.configure(state="normal")
        self.text.insert("end", f"{sender}  {stamp}\n", "head_user" if is_user else "head")
        self.text.insert("end", f"{text}\n\n", "body")
        self.text.configure(state="disabled")
        self.text.see("end")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("0.0", "end")
        self.text.configure(state="disabled")

    def get_text(self):
        return self.text.get("0.0", "end")

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["chat_bg"])
        self.inner.configure(fg_color=palette["chat_bg"])
        self.text.configure(bg=palette["chat_bg"], fg=palette["text"])
        self._configure_tags(palette)

    def _configure_tags(self, palette):
        self.text.tag_configure("head", foreground=palette["accent"], font=theme.FONT_HEAD)
        self.text.tag_configure("head_user", foreground=palette["text_strong"], font=theme.FONT_HEAD)
        self.text.tag_configure("body", foreground=palette["text"], font=theme.FONT_BODY)
