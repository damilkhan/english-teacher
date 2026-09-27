# -*- coding: utf-8 -*-
"""ui.widgets.input_bar — поле ввода и кнопка «Отправить»."""

import customtkinter as ctk


class InputBar(ctk.CTkFrame):
    def __init__(self, parent, palette, on_send=None):
        super().__init__(parent, fg_color=palette["surface"], corner_radius=12)
        self.palette = palette
        self.on_send = on_send

        self.textbox = ctk.CTkTextbox(
            self,
            height=50,
            wrap="word",
            fg_color=palette["input_bg"],
            border_width=0,
            corner_radius=8,
            font=ctk.CTkFont(size=14),
            text_color=palette["text"],
        )
        self.textbox.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=5)

        self.send_btn = ctk.CTkButton(
            self,
            text="📎 Отправить",
            fg_color=palette["accent"],
            hover_color=palette["accent_hover"],
            command=self._on_click,
            width=100,
            height=40,
            cursor="hand2",
            text_color="white",
            corner_radius=8,
        )
        self.send_btn.pack(side="right", padx=5, pady=5)

    # ---------- API ----------
    def get_text(self):
        return self.textbox.get("0.0", "end").strip()

    def clear_text(self):
        self.textbox.delete("0.0", "end")

    def set_text(self, text):
        self.clear_text()
        self.textbox.insert("0.0", text)

    def set_busy(self, busy):
        if busy:
            self.send_btn.configure(state="disabled", text="⏳ Думаю...")
        else:
            self.send_btn.configure(state="normal", text="📎 Отправить")

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["surface"])
        self.textbox.configure(fg_color=palette["input_bg"], text_color=palette["text"])
        self.send_btn.configure(fg_color=palette["accent"],
                                hover_color=palette["accent_hover"],
                                text_color="white")

    def _on_click(self):
        if self.on_send:
            self.on_send()
