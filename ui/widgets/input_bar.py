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

import re
import tkinter as tk

import customtkinter as ctk

import picture_task
import theme

PLACEHOLDER = "Напиши сообщение…"
SEND_TEXT = "Отправить"
# Подсказка в поле во время урока «только голосом». ВАЖНО: печатать МОЖНО —
# нельзя ОТПРАВЛЯТЬ английский. Русское слово уходит в переводчик: ученик
# видит вариант, произносит его вслух и только так отвечает преподавателю.
LOCK_HINT = "🎤 Говори в микрофон · слово по-русски → перевод"
# Подпись кнопки отправки, пока текст заблокирован занятием.
LOCK_BUTTON_TEXT = "🎤 Голосом"
# Подпись кнопки, когда в поле есть русские буквы: это запрос перевода.
TRANSLATE_TEXT = "💡 Перевести"

# Русские буквы (кириллица) — признак «ученик просит перевода», а не ответа.
_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")


def has_cyrillic(text):
    """Есть ли в тексте русские буквы (быстро, без модели и сети)."""
    return bool(_CYRILLIC.search(str(text or "")))


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
        self._locked = False      # занятие запрещает текстовый ввод (урок «голосом»)
        self._lock_hint = LOCK_HINT
        self._dict_ok = True      # словарь-подсказка (на экзамене False)
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

        # ---- счётчик букв задания «опиши фото» ----
        # Живёт ВНУТРИ поля ввода (решение ученика): серым справа внизу,
        # зеленеет, когда порог набран. Пока задания нет — не виден.
        self._counter_total = 0
        self.counter_lbl = tk.Label(self.textbox, text="", bd=0,
                                    highlightthickness=0,
                                    bg=palette["input_bg"],
                                    fg=palette["muted"],
                                    font=theme.FONT_HEAD)

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
        # кнопка «💡 Перевести» включается, как только в поле появилась кириллица
        self._field.bind("<KeyRelease>", self._on_key_release, add="+")
        self.textbox.bind("<Return>", self._on_return)
        self._show_placeholder()

    # ---------- API ----------
    def get_text(self):
        if self._placeholder_on:
            return ""
        return self._real_text().strip()

    def clear_text(self):
        self._placeholder_on = False
        self._replace_field_text("", self.palette["text"])
        self._apply_state()      # подсказка и подпись кнопки — по обстановке

    def insert_at_cursor(self, text):
        """Вставить текст В МЕСТО КУРСОРА, не стирая уже набранное.

        Нужно экспресс-переводчику: ученик начал писать "I want to ",
        перевёл слово и вставляет его посреди фразы. Каретка (insert mark)
        сохраняется, даже когда фокус ушёл на кнопку подсказки, поэтому
        вставка попадает именно туда, где ученик остановился.

        Возвращает True, если вставка удалась.
        """
        text = str(text or "")
        if not text:
            return False
        try:
            if self._placeholder_on:
                self._drop_placeholder()          # подсказку убираем ДО вставки
            content = self._real_text()
            # ВАЖНО: считаем позицию по ВНУТРЕННЕМУ tk.Text — у CTkTextbox
            # (обёртки) нет метода count(), из-за чего вставка уходила в конец.
            field = self._field
            try:
                index = field.index("insert")
            except Exception:
                index = "end-1c"
            try:
                offset = int(field.count("1.0", index, "chars")[0])
            except Exception:
                offset = len(content)
            offset = max(0, min(len(content), offset))
            before, after = content[:offset], content[offset:]
            prefix = "" if (not before or before[-1].isspace()) else " "
            suffix = "" if (not after or after[0].isspace()) else " "
            new_text = before + prefix + text + suffix + after
            self.textbox.delete("1.0", "end")
            self.textbox.insert("1.0", new_text)
            caret = len(before) + len(prefix) + len(text)
            field.mark_set("insert", "1.0+%dc" % caret)
            self._placeholder_on = False
            self.textbox.configure(text_color=self.palette["text"])
            self._apply_state()      # вставили английское — кнопка снова «голосом»
            self.focus_input()
            return True
        except Exception as exc:
            print("⚠️ Вставка в поле не удалась: %s" % exc)
            return False

    def set_text(self, text):
        self._placeholder_on = False
        self._replace_field_text(str(text), self.palette["text"])
        self._apply_state()

    # ---------- счётчик букв (задание с картинкой) ----------
    def set_counter(self, total):
        """Показать счётчик букв: «N из total» внутри поля. total=0 — скрыть."""
        try:
            self._counter_total = max(0, int(total or 0))
        except (TypeError, ValueError):
            self._counter_total = 0
        self._update_counter()

    def clear_counter(self):
        """Убрать счётчик (задание закончилось)."""
        self.set_counter(0)

    def counter_text(self):
        """Текст счётчика — удобно проверкам."""
        try:
            return str(self.counter_lbl.cget("text"))
        except Exception:
            return ""

    def _update_counter(self):
        """Пересчитать буквы и показать «N из total» нужным цветом."""
        label = getattr(self, "counter_lbl", None)
        if label is None:
            return
        if not self._counter_total:
            try:
                label.configure(text="")
                label.place_forget()
            except Exception:
                pass
            return
        count = picture_task.letters(self.get_text())
        color = (self.palette["ok"] if count >= self._counter_total
                 else self.palette["muted"])
        try:
            label.configure(text="%d из %d" % (count, self._counter_total),
                            fg=color)
            label.place(relx=1.0, rely=1.0, anchor="se", x=-16, y=-8)
            label.lift()
        except Exception:
            pass

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

    def set_locked(self, locked, hint="", allow_dictionary=True):
        """Мягко заблокировать ТЕКСТОВЫЙ ввод (урок «только голосом»).

        Не выключаем виджет насовсем: поле показывает подсказку-замок и не
        принимает символы, но остаётся на месте (плейсхолдер и фокус не
        ломаются). Гейт «профиль/сервер» живёт отдельно — состояния
        сводятся вместе в _apply_state, поэтому они не «перетирают» друг друга.
        """
        self._locked = bool(locked)
        self._lock_hint = hint or LOCK_HINT
        # ЭКЗАМЕН: словарь выключен совсем — кириллица не делает кнопку
        # «💡 Перевести», поле остаётся замком (решение ученика 24.10.2026).
        self._dict_ok = bool(allow_dictionary)
        self._apply_state()

    @property
    def is_locked(self):
        return self._locked

    def _apply_state(self):
        """Единая точка состояния поля и кнопки.

        Приоритет: гейт (нет профиля/сервера) > «Думаю…» > блокировка урока.

        ВАЖНО (решение ученика, 23.10.2026): урок «только голосом» больше НЕ
        отключает клавиатуру. Ученик вправе написать слово по-русски и получить
        перевод — смысл подсказки в том, чтобы ПРОИЗНЕСТИ английский вариант
        вслух, а не вставить его в чат. Поэтому замок урока отнимает ОТПРАВКУ
        английского текста, а не ввод, и остаётся такой, пока в поле нет
        кириллицы.
        """
        if not self._enabled:
            self.send_btn.configure(state="disabled", text=(self._hint or "Недоступно"))
        elif self._busy:
            self.send_btn.configure(state="disabled", text="Думаю…")
        elif self._locked:
            if self._dict_ok and has_cyrillic(self._real_text()):
                # «ключ» — это не ответ, а просьба о переводе: кнопка живая
                self.send_btn.configure(state="normal", text=TRANSLATE_TEXT)
            else:
                self.send_btn.configure(state="disabled", text=LOCK_BUTTON_TEXT)
        elif has_cyrillic(self._real_text()):
            # ОБЫЧНЫЙ урок (текст разрешён): русское слово в поле — тоже
            # просьба о переводе, а не ответ учителю. Кнопка обязана это
            # показать, иначе ученик видит «Отправить» и не нажимает вовсе
            # (живая жалоба 26.10.2026: набрал «примерн» и не стал слать).
            self.send_btn.configure(state="normal", text=TRANSLATE_TEXT)
        else:
            self.send_btn.configure(state="normal", text=SEND_TEXT)

        self._refresh_placeholder()

    def _refresh_placeholder(self):
        """Показать подсказку по обстановке (обычную, «замок» или ничего).
        """
        if self._locked:
            if not self._real_text().strip():
                self._show_placeholder(self._lock_hint)
            return
        if self._placeholder_on:
            self._show_placeholder()
        elif not self._real_text().strip() and not self._is_focused():
            self._show_placeholder()

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

    def _replace_field_text(self, text, color):
        """Записать текст в поле, ВРЕМЕННО снимая «disabled».

        ГРАБЛЯ Tk: у выключенного текстового виджета команды delete/insert
        молча НИЧЕГО не делают (без исключения!) — поэтому подсказку-замок
        иначе не поставить. Включаем, пишем, возвращаем состояние обратно.
        """
        state = None
        try:
            state = str(self._field.cget("state"))
            if state == "disabled":
                self._field.configure(state="normal")
            self.textbox.delete("0.0", "end")
            self.textbox.insert("0.0", text)
            self.textbox.configure(text_color=color)
        except Exception:
            pass
        finally:
            if state == "disabled":
                try:
                    self._field.configure(state="disabled")
                except Exception:
                    pass

    def _show_placeholder(self, text=None):
        """Показать подсказку (обычную или «замок»)."""
        text = PLACEHOLDER if text is None else str(text)
        self._placeholder_on = True
        self._replace_field_text(text, self.palette["muted"])

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
        self._replace_field_text("", self.palette["text"])
        return True

    # ---------- события ----------
    def _on_focus_in(self, _event=None):
        self.textbox.configure(border_color=self.palette["accent"])
        self._drop_placeholder()

    def _on_focus_out(self, _event=None):
        self.textbox.configure(border_color=self.palette["border"])
        if not self._real_text().strip():
            # в уроке подсказка другая: печатать можно, отправлять — нет
            self._show_placeholder(self._lock_hint if self._locked else None)

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
        # курсор встанет в начало — клик дальше Tk обработает сам.
        self._drop_placeholder()
        return None

    def _on_key_release(self, _event=None):
        """Кнопка следит за кириллицей: есть русское слово — «💡 Перевести».

        Работает в ЛЮБОМ режиме поля: и в уроке «только голосом», и в обычном
        (там подпись раньше вообще не пересчитывалась — живой баг 26.10.2026).
        """
        self._update_counter()
        # Пересчитываем подпись ВСЕГДА: в обычном уроке кнопка тоже обязана
        # меняться на «💡 Перевести», как только появилась кириллица.
        self._apply_state()
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
        label = getattr(self, "counter_lbl", None)
        if label is not None:
            try:
                label.configure(bg=palette["input_bg"])
            except Exception:
                pass
            self._update_counter()

    def _on_click(self):
        if self.on_send:
            self.on_send()
