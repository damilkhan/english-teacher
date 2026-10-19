# -*- coding: utf-8 -*-
"""ui.widgets.hint_bar — ЭКСПРЕСС-ПЕРЕВОДЧИК над полем ввода.

Ученик не знает, как сказать по-английски, и пишет по-русски (слово или
фразу) — здесь появляется английский вариант. Это НЕ отправка сообщения:
ученик сам решает, что делать дальше.

Как послушать произношение
--------------------------
Отдельной кнопки-динамика БОЛЬШЕ НЕТ (решение ученика): раньше 🔊 читал
только первое значение, и второе послушать было нельзя. Теперь КЛИК по
самому слову или по его примеру озвучивает ровно этот текст, а при
наведении мыши слово подсвечивается — видно, что на него можно нажать.

Кнопки:
  ↺  — вставить перевод В ПОЛЕ ВВОДА в место курсора (чтобы можно было
       продолжить писать по-английски, не набирая всё заново);
  ✕  — закрыть подсказку.

Почему без кнопки «Отправить»: у нас есть микрофон — естественный шаг после
подсказки не «отправить», а СКАЗАТЬ фразу вслух. Кнопка отправки подталкивала
читать, а цель проекта — говорение.

Полоса САМА прячется, когда подсказки нет (как info_bar и lesson_bar).
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

import customtkinter as ctk

import theme

ICON_HINT = "\U0001F4A1"     # 💡
BULLET = "\u2022"            # •
INSERT_TEXT = "↺"

MAX_LINES = 3                # сколько значений слова показываем


# Разделитель «слово — пример» в строке значения (translate.py отдаёт его
# длинным тире; на всякий случай принимаем и короткое).
_MEANING_SPLIT = re.compile(r"\s+[\u2014\u2013-]\s+")


def split_meaning(line):
    """«key — Open the door.» → ('key', 'Open the door.'); без тире → (строка, '')."""
    parts = _MEANING_SPLIT.split(str(line or "").strip(), maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return str(line or "").strip(), ""


class HintBar(ctk.CTkFrame):
    """Строка-подсказка: «💡 key — Open the door with this key.  ↺ ✕»."""

    def __init__(self, parent, palette,
                 on_insert: Optional[Callable[[str], None]] = None,
                 on_listen: Optional[Callable[[str], None]] = None,
                 before=None, on_close: Optional[Callable[[], None]] = None):
        super().__init__(parent, fg_color=palette["surface_alt"],
                         corner_radius=theme.R["block"])
        self.palette = palette
        self._on_insert = on_insert
        self._on_listen = on_listen
        self._before = before
        self._on_close = on_close
        self._visible = False
        self._english = ""
        # [(подпись, ключ палитры)] — по ключу восстанавливаем цвет при смене темы
        self._items: List[tuple] = []

        # КНОПКИ создаём ПЕРВЫМИ и упаковываем справа: тогда текст занимает
        # остаток и не выдавливает их, даже если строка длинная.
        self.close_btn = ctk.CTkButton(
            self, text="✕", command=self._close, width=28, height=28,
            fg_color="transparent", hover_color=palette["btn_hover"],
            text_color=palette["muted"], cursor="hand2",
            corner_radius=theme.R["button"], font=theme.FONT_SMALL)
        self.close_btn.pack(side="right", padx=(0, 6), pady=5)

        self.insert_btn = ctk.CTkButton(
            self, text=INSERT_TEXT, command=self._insert, width=36, height=28,
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            text_color=palette["text"], cursor="hand2",
            corner_radius=theme.R["button"], border_width=1,
            border_color=palette["border"], font=theme.FONT_UI)
        self.insert_btn.pack(side="right", padx=(0, 6), pady=5)

        # Текст подсказки — не одна надпись, а НАБОР строк: каждое значение
        # (и даже отдельно слово с примером) озвучивается по клику.
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(side="left", fill="both", expand=True,
                        padx=(10, 6), pady=5)

    # ---------- сборка содержимого ----------
    def _clear_body(self) -> None:
        for child in self._body.winfo_children():
            child.destroy()
        self._items = []
        self._grid_row = 0

    def _make_label(self, text, color_key="text", speak="", font=None):
        """Подпись. Если задан speak — по ней можно нажать и услышать текст.

        Подсветка при наведении есть ТОЛЬКО у нажимаемых подписей: так видно,
        что именно читается голосом.
        """
        # height=0: у CTkLabel по умолчанию 28 px, и на четыре строки полоса
        # вырастала (78 → 122 px). С нулём высоту задаёт сам текст (замер:
        # 4 строки = 78 px, ровно как у прежней единой надписи, без обрезки).
        label = ctk.CTkLabel(self._body, text=text, anchor="w", justify="left",
                             font=font or theme.FONT_UI, height=0,
                             text_color=self.palette[color_key],
                             fg_color="transparent", corner_radius=6,
                             cursor="hand2" if speak else "arrow")
        self._items.append((label, color_key))
        if speak:
            # CTkLabel.bind переадресует вызов своей внутренней подписи —
            # поэтому настоящий клик мышью до обработчика доходит.
            label.bind("<Enter>", lambda _e, l=label: self._hover(l, True), add="+")
            label.bind("<Leave>", lambda _e, l=label: self._hover(l, False), add="+")
            label.bind("<Button-1>", lambda _e, s=speak: self._listen(s), add="+")
        return label

    def _line(self, parts):
        """Одна строка подсказки: parts — [(текст, ключ цвета, что озвучить, шрифт)].

        Раскладка через grid БЕЗ отдельного фрейма на строку: с фреймом полоса
        вырастала на ~10 px на каждую строку (замер: 78 px → 122 px).
        """
        for col, part in enumerate(parts):
            text, color_key, speak = part[0], part[1], part[2]
            font = part[3] if len(part) > 3 else None
            label = self._make_label(text, color_key, speak, font)
            label.grid(row=self._grid_row, column=col, sticky="w",
                       padx=(0 if col == 0 else 6, 6))
        self._grid_row += 1

    def _hover(self, label, on: bool) -> None:
        """Подсветить нажимаемую подпись под курсором (и снять подсветку)."""
        if self._on_listen is None:
            return
        key = dict(self._items).get(label, "text")
        try:
            if on:
                label.configure(fg_color=self.palette["btn_hover"],
                                text_color=self.palette["text_strong"])
            else:
                label.configure(fg_color="transparent",
                                text_color=self.palette[key])
        except Exception:                              # noqa: BLE001
            pass

    # ---------- данные ----------
    def show_translation(self, english, source=""):
        """Показать перевод одной строкой (фраза)."""
        english = str(english or "").strip()
        if not english:
            self.clear()
            return
        self._english = english
        self._clear_body()
        self._line([("%s %s" % (ICON_HINT, english), "text", english)])
        source = str(source or "").strip()
        if source:
            self._line([("   «%s»" % source, "muted", "", theme.FONT_SMALL)])
        self._show()

    def show_meanings(self, meanings, source=""):
        """Показать до трёх значений СЛОВА с примерами.

        Каждое значение нажимается отдельно: клик по английскому слову читает
        слово, клик по примеру — пример. Раньше 🔊 читал только первое
        значение, остальные послушать было нельзя.
        """
        lines = [str(m).strip() for m in (meanings or []) if str(m).strip()]
        if not lines:
            self.clear()
            return
        lines = lines[:MAX_LINES]
        self._english = lines[0]
        self._clear_body()
        source = str(source or "").strip()
        header = "%s «%s»" % (ICON_HINT, source) if source else ICON_HINT
        self._line([(header, "text", "")])
        for line in lines:
            word, example = split_meaning(line)
            if example:
                self._line([("   %s %s" % (BULLET, word), "text", word),
                            ("— %s" % example, "muted", example)])
            else:
                self._line([("   %s %s" % (BULLET, line), "text", line)])
        self._show()

    def show_status(self, text):
        """Служебное сообщение (например, «перевожу…»)."""
        self._english = ""
        self._clear_body()
        self._line([(str(text or ""), "text", "")])
        self._show()

    def show_note(self, text, english=""):
        """Показать пояснение (например, вердикт сверки произношения).

        english — фраза, которую можно послушать: нажатие на подпись читает
        именно её (отдельной кнопки 🔊, как раньше, больше нет).
        """
        self._english = str(english or "")
        self._clear_body()
        self._line([(str(text or ""), "text", self._english)])
        self._show()

    def clear(self):
        self._english = ""
        self._clear_body()
        self._hide()

    @property
    def english(self):
        return self._english

    @property
    def text(self):
        """Весь текст подсказки одной строкой (для проверок и подсказок)."""
        parts = []
        for label, _key in list(self._items):
            try:
                parts.append(str(label.cget("text") or ""))
            except Exception:                          # noqa: BLE001
                pass
        return "\n".join(parts)

    @property
    def visible(self):
        return self._visible

    # ---------- видимость ----------
    def _show(self):
        if self._visible:
            return
        kwargs = dict(side="bottom", fill="x", padx=6, pady=(0, 6))
        if self._before is not None:
            kwargs["before"] = self._before
        try:
            self.pack(**kwargs)
            self._visible = True
        except Exception:
            pass

    def _hide(self):
        if not self._visible:
            return
        try:
            self.pack_forget()
        except Exception:
            pass
        self._visible = False

    # ---------- кнопки ----------
    def _close(self):
        """Кнопка ✕: убрать подсказку и сообщить об этом приложению."""
        self.clear()
        if self._on_close is not None:
            try:
                self._on_close()
            except Exception:                          # noqa: BLE001
                pass

    def _insert(self):
        """Вставить перевод в поле ввода (в место курсора)."""
        if not self._english or self._on_insert is None:
            return
        try:
            ok = self._on_insert(self._english)
        except Exception as exc:                       # noqa: BLE001
            print("⚠️ Не удалось вставить перевод: %s" % exc)
            return
        # вставили → подсказка больше не нужна (русский текст убираем)
        if ok is not False:
            self.clear()

    def _listen(self, text):
        """Нажатие на слово/пример/фразу — озвучить ИМЕННО этот текст."""
        if not text or self._on_listen is None:
            return
        try:
            self._on_listen(text)
        except Exception:                              # noqa: BLE001
            pass

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["surface_alt"])
        for label, key in list(self._items):
            try:
                label.configure(text_color=palette[key])
            except Exception:                          # noqa: BLE001
                pass
        self.insert_btn.configure(fg_color=palette["btn"],
                                  hover_color=palette["btn_hover"],
                                  text_color=palette["text"],
                                  border_color=palette["border"])
        self.close_btn.configure(hover_color=palette["btn_hover"],
                                 text_color=palette["muted"])
