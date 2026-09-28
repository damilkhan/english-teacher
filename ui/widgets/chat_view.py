# -*- coding: utf-8 -*-
"""ui.widgets.chat_view — область чата.

Редизайн: сообщения получили отступы (lmargin), воздух между репликами
(spacing1/spacing3), ник окрашен по роли — Джейн акцентом, «Вы» цианом.
"""

import tkinter as tk
from datetime import datetime

import customtkinter as ctk

import theme

USER_SENDERS = ("Вы", "Вы (голос)")
DOT = "·"


class ChatView(ctk.CTkFrame):
    def __init__(self, parent, palette, greeting=None, corner_radius=None):
        super().__init__(parent, fg_color=palette["chat_bg"],
                         corner_radius=corner_radius or theme.R["card"],
                         border_width=1, border_color=palette["border"])
        self.palette = palette

        # область текста внутри карточки
        self.text = tk.Text(
            self,
            wrap="word",
            font=theme.FONT_BODY,
            bg=palette["chat_bg"],
            fg=palette["text"],
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            padx=10,
            pady=10,
            insertbackground=palette["accent"],
            selectbackground=palette["accent_soft"],
            selectforeground=palette["text_strong"],
            cursor="arrow",
        )
        self.text.pack(side="left", fill="both", expand=True)

        self.scrollbar = ctk.CTkScrollbar(
            self, command=self.text.yview, width=8,
            fg_color="transparent",
            button_color=palette["btn"],
            button_hover_color=palette["btn_hover"],
        )
        self.scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=6)
        self.text.configure(yscrollcommand=self.scrollbar.set)

        self._configure_tags(palette)
        if greeting:
            sender, text = greeting
            self.add_message(sender, text, stamp=None)
        self.text.configure(state="disabled")

    # ---------- API ----------
    def add_message(self, sender, text, stamp=None):
        """Рисует реплику и прокручивает чат вниз."""
        is_user = sender in USER_SENDERS
        head_tag = "head_user" if is_user else "head"
        body_tag = "body_user" if is_user else "body"

        header = f"{sender}  {DOT}  {stamp}" if stamp else sender

        self.text.configure(state="normal")
        self.text.insert("end", header + "\n", head_tag)
        self.text.insert("end", f"{text}\n", body_tag)
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
        self.configure(fg_color=palette["chat_bg"], border_color=palette["border"])
        self.text.configure(bg=palette["chat_bg"], fg=palette["text"],
                            insertbackground=palette["accent"],
                            selectbackground=palette["accent_soft"],
                            selectforeground=palette["text_strong"])
        self.scrollbar.configure(button_color=palette["btn"],
                                 button_hover_color=palette["btn_hover"])
        self._configure_tags(palette)

    def _configure_tags(self, palette):
        common = dict(lmargin1=14, lmargin2=14, rmargin=14)
        self.text.tag_configure("head", foreground=palette["accent"],
                                font=theme.FONT_HEAD, spacing1=8, **common)
        self.text.tag_configure("head_user", foreground=palette["cyan"],
                                font=theme.FONT_HEAD, spacing1=8, **common)
        self.text.tag_configure("body", foreground=palette["text"],
                                font=theme.FONT_BODY, spacing3=10, **common)
        self.text.tag_configure("body_user", foreground=palette["text_strong"],
                                font=theme.FONT_BODY, spacing3=10, **common)
