# -*- coding: utf-8 -*-
"""ui.widgets.control_bar — три кнопки: запись, настройки, очистка."""

import customtkinter as ctk


class ControlBar(ctk.CTkFrame):
    def __init__(self, parent, palette, on_record=None, on_settings=None, on_clear=None):
        super().__init__(parent, fg_color=palette["surface"], corner_radius=12)
        self.palette = palette

        self.record_btn = ctk.CTkButton(
            self, text="🎤 Запись",
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            command=on_record, width=120, height=40, cursor="hand2",
            text_color=palette["text_strong"], corner_radius=8,
            border_width=1, border_color=palette["border"],
        )
        self.record_btn.pack(side="left", padx=10, pady=10)

        self.settings_btn = ctk.CTkButton(
            self, text="⚙️ Настройки",
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            command=on_settings, width=120, height=40, cursor="hand2",
            text_color=palette["text_strong"], corner_radius=8,
            border_width=1, border_color=palette["border"],
        )
        self.settings_btn.pack(side="right", padx=10, pady=10)

        self.clear_btn = ctk.CTkButton(
            self, text="🗑️ Очистить",
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            command=on_clear, width=120, height=40, cursor="hand2",
            text_color=palette["text_strong"], corner_radius=8,
            border_width=1, border_color=palette["border"],
        )
        self.clear_btn.pack(side="right", padx=10, pady=10)

    # ---------- API ----------
    def set_recording(self, recording):
        """Идёт запись → красная кнопка «🔴 Запись...» (по ней же можно остановить)."""
        if recording:
            self.record_btn.configure(state="normal", text="🔴 Запись...",
                                      fg_color=self.palette["record"])
        else:
            self.record_btn.configure(state="normal", text="🎤 Запись",
                                      fg_color=self.palette["btn"])

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["surface"])
        for btn in (self.record_btn, self.settings_btn, self.clear_btn):
            btn.configure(fg_color=palette["btn"], hover_color=palette["btn_hover"],
                          text_color=palette["text_strong"], border_color=palette["border"])
