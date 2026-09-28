# -*- coding: utf-8 -*-
"""ui.widgets.control_bar — кнопки управления приложением.

Редизайн: «стеклянные» кнопки (полупрозрачный вид за счёт тона кнопки
и тонкой рамки), запись — акцентная при включении, заметный отступ.
"""

import customtkinter as ctk

import theme

RECORD_IDLE = "🎤  Запись"
RECORD_ACTIVE = "🔴  Идёт запись"
BTN_W, BTN_H = 132, 42


class ControlBar(ctk.CTkFrame):
    def __init__(self, parent, palette, on_record=None, on_settings=None, on_clear=None):
        super().__init__(parent, fg_color="transparent")
        self.palette = palette

        self.record_btn = self._button(RECORD_IDLE, on_record, width=BTN_W)
        self.record_btn.pack(side="left")

        self.settings_btn = self._button("⚙️  Настройки", on_settings)
        self.settings_btn.pack(side="right")

        self.clear_btn = self._button("🗑️  Очистить", on_clear)
        self.clear_btn.pack(side="right", padx=(0, 10))

    def _button(self, text, command, width=BTN_W):
        p = self.palette
        return ctk.CTkButton(
            self, text=text, command=command,
            fg_color=p["btn"], hover_color=p["btn_hover"],
            text_color=p["text"],
            width=width, height=BTN_H, cursor="hand2",
            corner_radius=theme.R["button"],
            border_width=1, border_color=p["border"],
            font=theme.FONT_UI,
        )

    # ---------- API ----------
    def set_recording(self, recording):
        if recording:
            self.record_btn.configure(state="normal", text=RECORD_ACTIVE,
                                      fg_color=self.palette["record"],
                                      hover_color=self.palette["record"],
                                      text_color="#FFFFFF",
                                      border_color=self.palette["record"])
        else:
            self.record_btn.configure(state="normal", text=RECORD_IDLE,
                                      fg_color=self.palette["btn"],
                                      hover_color=self.palette["btn_hover"],
                                      text_color=self.palette["text"],
                                      border_color=self.palette["border"])

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        for btn in (self.settings_btn, self.clear_btn):
            btn.configure(fg_color=palette["btn"], hover_color=palette["btn_hover"],
                          text_color=palette["text"], border_color=palette["border"])
        self.set_recording(False)
