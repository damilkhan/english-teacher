# -*- coding: utf-8 -*-
"""ui.widgets.input_bar — поле ввода и кнопка отправки.

Что нового:
  * рамка поля подсвечивается акцентом при фокусе (подсказка, что можно писать);
  * подсказка-плейсхолдер, которая сама исчезает при вводе;
  * Enter отправляет, Shift+Enter переносит строку.
"""

import customtkinter as ctk

import theme

PLACEHOLDER = "Напиши сообщение…"
SEND_TEXT = "Отправить"


class InputBar(ctk.CTkFrame):
    def __init__(self, parent, palette, on_send=None):
        super().__init__(parent, fg_color="transparent")
        self.palette = palette
        self.on_send = on_send
        self._placeholder_on = False

        self.textbox = ctk.CTkTextbox(
            self,
            height=52,
            wrap="word",
            fg_color=palette["input_bg"],
            border_width=1,
            border_color=palette["border"],
            corner_radius=theme.R["input"],
            font=theme.FONT_UI,
            text_color=palette["text"],
            scrollbar_button_color=palette["btn"],
            scrollbar_button_hover_color=palette["btn_hover"],
        )
        self.textbox.pack(side="left", fill="both", expand=True)

        self.send_btn = ctk.CTkButton(
            self,
            text=SEND_TEXT,
            fg_color=palette["accent"],
            hover_color=palette["accent_hover"],
            command=self._on_click,
            width=118,
            height=44,
            cursor="hand2",
            text_color="#FFFFFF",
            corner_radius=theme.R["button"],
            font=theme.FONT_UI,
        )
        self.send_btn.pack(side="right", padx=(10, 0))

        # поведение
        self.textbox.bind("<FocusIn>", self._on_focus_in)
        self.textbox.bind("<FocusOut>", self._on_focus_out)
        self.textbox.bind("<Return>", self._on_return)
        self._show_placeholder()

    # ---------- API ----------
    def get_text(self):
        if self._placeholder_on:
            return ""
        return self.textbox.get("0.0", "end").strip()

    def clear_text(self):
        self._placeholder_on = False
        self.textbox.delete("0.0", "end")
        # если поле не в фокусе — снова показываем подсказку
        try:
            focused = self.textbox.focus_get() == self.textbox
        except Exception:
            focused = False
        if not focused:
            self._show_placeholder()

    def set_text(self, text):
        self._placeholder_on = False
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", text)

    def set_busy(self, busy):
        if busy:
            self.send_btn.configure(state="disabled", text="Думаю…")
        else:
            self.send_btn.configure(state="normal", text=SEND_TEXT)

    def focus_input(self):
        try:
            self.textbox.focus_set()
        except Exception:
            pass

    # ---------- плейсхолдер ----------
    def _show_placeholder(self):
        self._placeholder_on = True
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", PLACEHOLDER)
        self.textbox.configure(text_color=self.palette["muted"])

    def _hide_placeholder(self):
        self._placeholder_on = False
        self.textbox.delete("0.0", "end")
        self.textbox.configure(text_color=self.palette["text"])

    # ---------- события ----------
    def _on_focus_in(self, _event=None):
        self.textbox.configure(border_color=self.palette["accent"])
        if self._placeholder_on:
            self._hide_placeholder()

    def _on_focus_out(self, _event=None):
        self.textbox.configure(border_color=self.palette["border"])
        if not self.textbox.get("0.0", "end").strip():
            self._show_placeholder()

    def _on_return(self, event):
        if event.state & 0x0001:      # Shift+Enter — обычный перенос строки
            return None
        self._on_click()
        return "break"

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        border = palette["accent"] if _is_focused(self.textbox) else palette["border"]
        self.textbox.configure(
            fg_color=palette["input_bg"],
            border_color=border,
            text_color=palette["muted"] if self._placeholder_on else palette["text"],
            scrollbar_button_color=palette["btn"],
            scrollbar_button_hover_color=palette["btn_hover"],
        )
        self.send_btn.configure(fg_color=palette["accent"],
                                hover_color=palette["accent_hover"])

    def _on_click(self):
        if self.on_send:
            self.on_send()


def _is_focused(widget):
    try:
        return widget.focus_get() == widget
    except Exception:
        return False
