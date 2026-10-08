# -*- coding: utf-8 -*-
"""ui.widgets.input_bar — поле ввода и кнопка отправки.

Что нового:
  * рамка поля подсвечивается акцентом при фокусе (подсказка, что можно писать);
  * подсказка-плейсхолдер, которая сама исчезает при вводе;
  * Enter отправляет, Shift+Enter переносит строку.

ВАЖНО про подсказку.
Подсказка лежит в поле ОБЫЧНЫМ ТЕКСТОМ, поэтому за ней нужно следить особенно
внимательно. Раньше «в фокусе ли поле» проверялось так:
self.textbox.focus_get() == self.textbox. Но CTkTextbox — это фрейм, а фокус
получает его ВНУТРЕННИЙ tk.Text (customtkinter.windows.widgets.ctk_textbox
создаёт _textbox внутри себя). Сравнение всегда было ложным, поэтому после
первой отправки подсказка вставлялась обратно, хотя курсор оставался в поле:
набранный текст приписывался к «Напиши сообщение…», get_text() отдавал пустую
строку — и сообщение молча не отправлялось.

Как исправлено:
  * _is_focused() спрашивает и фрейм, и внутренний tk.Text;
  * ЛЮБОЕ реальное действие — нажатие «печатающей» клавиши или клик по полю —
    снимает подсказку ДО вставки символа, поэтому ввод никогда не «прилипает»
    к подсказке (обработчик события срабатывает раньше класса Text, который
    вставляет символ);
  * get_text() дополнительно считает подсказку пустым полем, даже если флаг
    состояния почему-то разошёлся с содержимым: молча потерять сообщение
    пользователя хуже, чем один раз показать пустое поле.
"""

import customtkinter as ctk

import theme

PLACEHOLDER = "Напиши сообщение…"
SEND_TEXT = "Отправить"

# Клавиши, после которых подсказка обязана уйти: печатающие символы плюс те,
# что меняют содержимое (Backspace/Delete) и вставку из буфера (Ctrl+V).
_INPUT_KEYS = ("BackSpace", "Delete", "Return", "KP_Enter")
_CTRL_MASK = 0x0004


class InputBar(ctk.CTkFrame):
    def __init__(self, parent, palette, on_send=None):
        super().__init__(parent, fg_color="transparent")
        self.palette = palette
        self.on_send = on_send
        self._placeholder_on = False
        self._enabled = True      # разрешена ли отправка (профиль/сервер)
        self._busy = False        # идёт ответ Джейн
        self._hint = ""           # почему отправка недоступна

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

        # --- поведение ---
        # CTkTextbox.bind() прокидывает событие во внутренний tk.Text, поэтому
        # привязываемся к нему напрямую: так обработчик гарантированно идёт
        # раньше класса Text, который вставляет набранный символ.
        self._field = getattr(self.textbox, "_textbox", self.textbox)
        self._field.bind("<FocusIn>", self._on_focus_in, add="+")
        self._field.bind("<FocusOut>", self._on_focus_out, add="+")
        self._field.bind("<KeyPress>", self._on_key_press, add="+")
        self._field.bind("<Button-1>", self._on_click_in_field, add="+")
        self.textbox.bind("<Return>", self._on_return)
        self._show_placeholder()

    # ---------- API ----------
    def get_text(self):
        if self._placeholder_on:
            return ""
        return self._real_text().strip()

    def clear_text(self):
        self._placeholder_on = False
        self.textbox.delete("0.0", "end")
        # если поле не в фокусе — снова показываем подсказку
        if not self._is_focused():
            self._show_placeholder()

    def set_text(self, text):
        self._placeholder_on = False
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", text)
        self.textbox.configure(text_color=self.palette["text"])

    def set_busy(self, busy):
        self._busy = bool(busy)
        self._apply_state()

    def set_enabled(self, enabled, hint=""):
        """Включить/выключить отправку.

        hint — короткая причина, которую видно НА кнопке (например,
        «Заполни профиль» или «Загружаю модель…»).
        """
        self._enabled = bool(enabled)
        self._hint = hint or ""
        self._apply_state()

    def _apply_state(self):
        """Кнопка отправки: «Думаю…» > причина блокировки > норма."""
        if self._busy:
            self.send_btn.configure(state="disabled", text="Думаю…")
        elif not self._enabled:
            self.send_btn.configure(state="disabled", text=(self._hint or "Недоступно"))
        else:
            self.send_btn.configure(state="normal", text=SEND_TEXT)

    def focus_input(self):
        try:
            self.textbox.focus_set()
        except Exception:
            pass

    # ---------- подсказка ----------
    def _real_text(self):
        """Содержимое поля, но подсказка — это пустота, а не текст."""
        text = self.textbox.get("0.0", "end-1c")
        return "" if text == PLACEHOLDER else text

    def _is_focused(self):
        """Фокус в поле ввода?

        Спрашиваем оба виджета: у CTkTextbox (фрейма) и у его внутреннего
        tk.Text. Достаточно одного совпадения — важно лишь то, что курсор
        стоит в поле, а не то, какой из двух виджетов «главный».
        """
        try:
            focused = self.textbox.focus_get()
        except Exception:
            return False
        return focused in (self.textbox, self._field)

    def _show_placeholder(self):
        if self._placeholder_on:
            return
        self._placeholder_on = True
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", PLACEHOLDER)
        self.textbox.configure(text_color=self.palette["muted"])

    def _drop_placeholder(self):
        """Убирает подсказку, если она сейчас на экране.

        Возвращает True, если подсказку и вправду убрали. Убирать её надо
        ДО вставки символа: если сделать это после, набранная буква успеет
        приписаться к тексту подсказки — ровно тот сбой, из-за которого
        сообщения переставали отправляться.
        """
        if not self._placeholder_on:
            return False
        self._placeholder_on = False
        self.textbox.delete("0.0", "end")
        self.textbox.configure(text_color=self.palette["text"])
        return True

    # ---------- события ----------
    def _on_focus_in(self, _event=None):
        self.textbox.configure(border_color=self.palette["accent"])
        self._drop_placeholder()

    def _on_focus_out(self, _event=None):
        self.textbox.configure(border_color=self.palette["border"])
        if not self._real_text().strip():
            self._show_placeholder()

    def _on_key_press(self, event=None):
        if not self._placeholder_on:
            return None
        # Shift и стрелки подсказку не трогают: иначе она пропадала бы от
        # одного нажатия модификатора, а поле при этом оставалось пустым
        char = getattr(event, "char", "") or ""
        keysym = getattr(event, "keysym", "") or ""
        state = getattr(event, "state", 0) or 0
        if char or keysym in _INPUT_KEYS or state & _CTRL_MASK:
            self._drop_placeholder()
        return None

    def _on_click_in_field(self, _event=None):
        # клик по полю с подсказкой: поле должно стать обычным пустым полем,
        # курсор встанет в начало — клик дальше Tk обработает сам
        self._drop_placeholder()
        return None

    def _on_return(self, event):
        if event.state & 0x0001:      # Shift+Enter — обычный перенос строки
            return None
        self._on_click()
        return "break"

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        border = palette["accent"] if self._is_focused() else palette["border"]
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
