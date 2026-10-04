# -*- coding: utf-8 -*-
"""ui.widgets.control_bar — кнопки управления приложением.

Внешний вид: «стеклянные» кнопки (тон кнопки + тонкая рамка), запись —
акцентная при включении.

Иконки рисуем Pillow-ом (ui.emoji_render) и кладём картинкой: Tk выводит
эмодзи ОДНИМ тоном (с цветной каймой ClearType), из-за чего значки выглядели
сломанными. Цветной глиф из Segoe UI Emoji + CTkImage даёт ровный значок.
Если цветных эмодзи нет — откатываемся на прежний текст со значком.
"""

import customtkinter as ctk

import theme

try:
    from ui import emoji_render
except Exception:
    emoji_render = None

RECORD_LABEL = "Запись"
RECORD_ACTIVE_LABEL = "Идёт запись"

# Значки. 🗑️ и 👥 в Segoe UI Emoji идут ОДНОТОННЫМИ (emoji_render их
# отбрасывает), поэтому берём цветные аналоги: метла и группа людей.
ICON_RECORD = "🎤"
ICON_CLEAR = "🧹"
ICON_USERS = "👪"
ICON_SETTINGS = "⚙️"

# Запасной текст, если цветные эмодзи недоступны.
FALLBACK = {
    "record": "🎤  Запись",
    "record_active": "🔴  Идёт запись",
    "clear": "🗑️  Очистить",
    "users": "👥  Пользователи",
    "settings": "⚙️  Настройки",
}

ICON_PX = 18
BTN_W, BTN_H = 124, 42
USERS_W = 158


class ControlBar(ctk.CTkFrame):
    def __init__(self, parent, palette, on_record=None, on_settings=None,
                 on_clear=None, on_users=None):
        super().__init__(parent, fg_color="transparent")
        self.palette = palette
        self._images = {}                    # символ -> CTkImage (держит ссылки)
        self._use_images = bool(emoji_render and emoji_render.available())

        self.record_btn = self._button("record", RECORD_LABEL, ICON_RECORD, on_record)
        self.record_btn.pack(side="left")

        self.settings_btn = self._button("settings", "Настройки", ICON_SETTINGS, on_settings)
        self.settings_btn.pack(side="right")

        self.users_btn = self._button("users", "Пользователи", ICON_USERS, on_users,
                                      width=USERS_W)
        self.users_btn.pack(side="right", padx=(0, 10))

        self.clear_btn = self._button("clear", "Очистить", ICON_CLEAR, on_clear)
        self.clear_btn.pack(side="right", padx=(0, 10))

    # ---------- иконки ----------
    def _icon(self, token):
        """Цветная картинка-иконка (CTkImage) или None, если рисовать нечем."""
        if not self._use_images or not token:
            return None
        if token in self._images:
            return self._images[token]
        image = None
        ink = emoji_render.render(token, ICON_PX)
        if ink is not None:
            try:
                image = ctk.CTkImage(light_image=ink, dark_image=ink,
                                     size=(ink.width, ink.height))
            except Exception:
                image = None
        self._images[token] = image
        return image

    def _button(self, key, label, icon_token, command, width=BTN_W):
        p = self.palette
        image = self._icon(icon_token)
        button = ctk.CTkButton(
            self, text=(label if image is not None else FALLBACK.get(key, label)),
            command=command,
            fg_color=p["btn"], hover_color=p["btn_hover"],
            text_color=p["text"],
            width=width, height=BTN_H, cursor="hand2",
            corner_radius=theme.R["button"],
            border_width=1, border_color=p["border"],
            font=theme.FONT_UI,
        )
        if image is not None:
            button.configure(image=image, compound="left")
        return button

    # ---------- API ----------
    def set_recording(self, recording):
        if recording:
            # на акцентной кнопке значок не нужен (🔴 был бы красным на красном)
            self.record_btn.configure(state="normal", fg_color=self.palette["record"],
                                      hover_color=self.palette["record"],
                                      text_color="#FFFFFF",
                                      border_color=self.palette["record"],
                                      text=FALLBACK["record_active"] if not self._use_images
                                      else RECORD_ACTIVE_LABEL)
            if self._use_images:
                try:
                    self.record_btn.configure(image=None)
                except Exception:
                    pass
        else:
            image = self._icon(ICON_RECORD)
            self.record_btn.configure(state="normal", fg_color=self.palette["btn"],
                                      hover_color=self.palette["btn_hover"],
                                      text_color=self.palette["text"],
                                      border_color=self.palette["border"],
                                      text=(RECORD_LABEL if image is not None
                                            else FALLBACK["record"]))
            if image is not None:
                self.record_btn.configure(image=image, compound="left")

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        for btn in (self.settings_btn, self.clear_btn, self.users_btn):
            btn.configure(fg_color=palette["btn"], hover_color=palette["btn_hover"],
                          text_color=palette["text"], border_color=palette["border"])
        self.set_recording(False)
