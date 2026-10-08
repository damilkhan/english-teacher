# -*- coding: utf-8 -*-
"""ui.panels.settings_panel — правая панель настроек.

Редизайн: секции с подписями-капсом, переключатели акцентом, кнопки
«Сохранить» (акцент) и «Закрыть» (стеклянная), тонкая рамка карточки.
"""

import customtkinter as ctk

import theme


class SettingsPanel(ctk.CTkFrame):
    def __init__(self, parent, palette, mode="lesson", theme_name="dark",
                 on_save=None, on_close=None, models=None, model=None):
        super().__init__(parent, fg_color=palette["surface"],
                         corner_radius=theme.R["card"],
                         border_width=1, border_color=palette["border"])
        self.palette = palette

        self.title_label = ctk.CTkLabel(self, text="НАСТРОЙКИ",
                                        font=theme.FONT_PANEL_TITLE,
                                        text_color=palette["text_strong"])
        self.title_label.pack(anchor="w", padx=20, pady=(20, 4))

        # ---------- режим ----------
        self.mode_frame = self._section("РЕЖИМ РАБОТЫ")
        self.mode_var = ctk.StringVar(value=mode)
        self.mode_lesson = self._radio(self.mode_frame, "🎓  Урок", self.mode_var, "lesson")
        self.mode_free = self._radio(self.mode_frame, "💬  Свободное общение", self.mode_var, "free")

        # ---------- тема ----------
        self.theme_frame = self._section("ОФОРМЛЕНИЕ")
        self.theme_var = ctk.StringVar(value=theme_name)
        self.theme_dark = self._radio(self.theme_frame, "🌙  Тёмная", self.theme_var, "dark")
        self.theme_light = self._radio(self.theme_frame, "☀️  Светлая", self.theme_var, "light")

        # ---------- модель ----------
        # Выбор хранится в settings.json, а применяется перезапуском сервера.
        self.model_frame = self._section("МОДЕЛЬ (при смене сервер перезапустится)")
        self._model_labels = {m["label"]: m["id"] for m in (models or [])}
        values = list(self._model_labels) or ["—"]
        current = next((lb for lb, mid in self._model_labels.items() if mid == model),
                       values[0])
        self.model_var = ctk.StringVar(value=current)
        self.model_menu = ctk.CTkOptionMenu(
            self.model_frame, values=values, variable=self.model_var,
            font=theme.FONT_UI, height=36, corner_radius=theme.R["button"],
            fg_color=palette["btn"], button_color=palette["accent"],
            button_hover_color=palette["accent_hover"], text_color=palette["text"],
            dropdown_fg_color=palette["surface_alt"], dropdown_text_color=palette["text"])
        self.model_menu.pack(fill="x", padx=16, pady=(6, 14))

        # ---------- подсказка про голосовые команды ----------
        self.hint = ctk.CTkLabel(
            self,
            text="Скажи или напиши «урок» либо «перерыв» —\nрежим переключится сам.",
            font=theme.FONT_SMALL,
            text_color=palette["muted"],
            justify="left",
        )
        self.hint.pack(anchor="w", padx=20, pady=(14, 0))

        # ---------- кнопки ----------
        self.save_btn = ctk.CTkButton(
            self, text="Сохранить", command=on_save,
            fg_color=palette["accent"], hover_color=palette["accent_hover"],
            width=200, height=42, cursor="hand2", text_color="#FFFFFF",
            corner_radius=theme.R["button"], font=theme.FONT_UI)
        self.save_btn.pack(side="bottom", pady=(0, 16), padx=20, fill="x")

        self.close_btn = ctk.CTkButton(
            self, text="Закрыть", command=on_close,
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            width=200, height=42, cursor="hand2", text_color=palette["text"],
            corner_radius=theme.R["button"], border_width=1,
            border_color=palette["border"], font=theme.FONT_UI)
        self.close_btn.pack(side="bottom", pady=(0, 10), padx=20, fill="x")

    # ---------- строительные блоки ----------
    def _section(self, caption):
        frame = ctk.CTkFrame(self, fg_color=self.palette["surface_alt"],
                             corner_radius=theme.R["block"])
        frame.pack(fill="x", padx=20, pady=(14, 0))
        cap = ctk.CTkLabel(frame, text=caption, font=theme.FONT_SECTION,
                           text_color=self.palette["muted"])
        cap.pack(anchor="w", padx=16, pady=(12, 2))
        frame.caption = cap          # запомним, чтобы перекрашивать
        return frame

    def _radio(self, parent, text, variable, value):
        radio = ctk.CTkRadioButton(
            parent, text=text, variable=variable, value=value,
            cursor="hand2",
            text_color=self.palette["text"],
            fg_color=self.palette["accent"],
            hover_color=self.palette["accent_hover"],
            border_color=self.palette["muted"],
            font=theme.FONT_UI,
        )
        radio.pack(pady=5, padx=16, anchor="w")
        return radio

    # ---------- API ----------
    def get_mode(self):
        return self.mode_var.get()

    def get_theme(self):
        return self.theme_var.get()

    def get_model(self):
        """id выбранной модели (или None, если список пуст)."""
        return self._model_labels.get(self.model_var.get())

    def set_values(self, mode=None, theme_name=None):
        if mode is not None:
            self.mode_var.set(mode)
        if theme_name is not None:
            self.theme_var.set(theme_name)

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["surface"], border_color=palette["border"])
        self.title_label.configure(text_color=palette["text_strong"])
        self.hint.configure(text_color=palette["muted"])

        for block in (self.mode_frame, self.theme_frame, self.model_frame):
            block.configure(fg_color=palette["surface_alt"])
            block.caption.configure(text_color=palette["muted"])
        for radio in (self.mode_lesson, self.mode_free, self.theme_dark, self.theme_light):
            radio.configure(text_color=palette["text"], fg_color=palette["accent"],
                            hover_color=palette["accent_hover"],
                            border_color=palette["muted"])
        self.model_menu.configure(fg_color=palette["btn"], button_color=palette["accent"],
                                  button_hover_color=palette["accent_hover"],
                                  text_color=palette["text"],
                                  dropdown_fg_color=palette["surface_alt"],
                                  dropdown_text_color=palette["text"])

        self.save_btn.configure(fg_color=palette["accent"],
                                hover_color=palette["accent_hover"])
        self.close_btn.configure(fg_color=palette["btn"],
                                 hover_color=palette["btn_hover"],
                                 text_color=palette["text"],
                                 border_color=palette["border"])
