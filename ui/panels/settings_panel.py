# -*- coding: utf-8 -*-
"""ui.panels.settings_panel — правая панель: режим, тема, кнопки.

Панель ничего не знает про приложение: наружу отдаёт get_mode() /
get_theme() и зовёт колбэки on_save / on_close.
"""

import customtkinter as ctk

import theme


class SettingsPanel(ctk.CTkFrame):
    def __init__(self, parent, palette, mode="lesson", theme_name="dark",
                 on_save=None, on_close=None):
        super().__init__(parent, width=260, fg_color=palette["surface"], corner_radius=16)
        self.palette = palette

        self.title_label = ctk.CTkLabel(self, text="⚙️ НАСТРОЙКИ",
                                        font=theme.FONT_PANEL_TITLE,
                                        text_color=palette["text_strong"])
        self.title_label.pack(pady=(25, 15))

        # ---------- режим ----------
        self.mode_frame = ctk.CTkFrame(self, fg_color=palette["block"], corner_radius=10)
        self.mode_frame.pack(fill="x", padx=15, pady=5)

        self.mode_label = ctk.CTkLabel(self.mode_frame, text="Режим:",
                                       font=theme.FONT_SMALL, text_color=palette["muted"])
        self.mode_label.pack(anchor="w", padx=15, pady=(10, 5))

        self.mode_var = ctk.StringVar(value=mode)
        self.mode_lesson = ctk.CTkRadioButton(
            self.mode_frame, text="🎓 Урок", variable=self.mode_var, value="lesson",
            cursor="hand2", text_color=palette["text_strong"], fg_color=palette["accent"])
        self.mode_lesson.pack(pady=5, padx=15, anchor="w")

        self.mode_free = ctk.CTkRadioButton(
            self.mode_frame, text="💬 Свободное общение", variable=self.mode_var, value="free",
            cursor="hand2", text_color=palette["text_strong"], fg_color=palette["accent"])
        self.mode_free.pack(pady=5, padx=15, anchor="w")

        # ---------- тема ----------
        self.theme_frame = ctk.CTkFrame(self, fg_color=palette["block"], corner_radius=10)
        self.theme_frame.pack(fill="x", padx=15, pady=5)

        self.theme_label = ctk.CTkLabel(self.theme_frame, text="Тема:",
                                        font=theme.FONT_SMALL, text_color=palette["muted"])
        self.theme_label.pack(anchor="w", padx=15, pady=(10, 5))

        self.theme_var = ctk.StringVar(value=theme_name)
        self.theme_dark = ctk.CTkRadioButton(
            self.theme_frame, text="🌙 Тёмная", variable=self.theme_var, value="dark",
            cursor="hand2", text_color=palette["text_strong"], fg_color=palette["accent"])
        self.theme_dark.pack(pady=5, padx=15, anchor="w")

        self.theme_light = ctk.CTkRadioButton(
            self.theme_frame, text="☀️ Светлая", variable=self.theme_var, value="light",
            cursor="hand2", text_color=palette["text_strong"], fg_color=palette["accent"])
        self.theme_light.pack(pady=5, padx=15, anchor="w")

        # ---------- кнопки ----------
        self.save_btn = ctk.CTkButton(
            self, text="Сохранить", command=on_save,
            fg_color=palette["accent"], hover_color=palette["accent_hover"],
            width=200, height=40, cursor="hand2", text_color="white", corner_radius=8)
        self.save_btn.pack(pady=(20, 10))

        self.close_btn = ctk.CTkButton(
            self, text="✖️ Закрыть", command=on_close,
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            width=200, height=40, cursor="hand2", text_color=palette["text_strong"],
            corner_radius=8, border_width=1, border_color=palette["border"])
        self.close_btn.pack(pady=(0, 20))

    # ---------- API ----------
    def get_mode(self):
        return self.mode_var.get()

    def get_theme(self):
        return self.theme_var.get()

    def set_values(self, mode=None, theme_name=None):
        if mode is not None:
            self.mode_var.set(mode)
        if theme_name is not None:
            self.theme_var.set(theme_name)

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["surface"])
        self.title_label.configure(text_color=palette["text_strong"])

        for block in (self.mode_frame, self.theme_frame):
            block.configure(fg_color=palette["block"])
        for label in (self.mode_label, self.theme_label):
            label.configure(text_color=palette["muted"])
        for radio in (self.mode_lesson, self.mode_free, self.theme_dark, self.theme_light):
            radio.configure(text_color=palette["text_strong"], fg_color=palette["accent"])

        self.save_btn.configure(fg_color=palette["accent"], hover_color=palette["accent_hover"])
        self.close_btn.configure(fg_color=palette["btn"], hover_color=palette["btn_hover"],
                                 text_color=palette["text_strong"], border_color=palette["border"])
