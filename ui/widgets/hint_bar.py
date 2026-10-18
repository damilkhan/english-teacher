# -*- coding: utf-8 -*-
"""ui.widgets.hint_bar — ЭКСПРЕСС-ПЕРЕВОДЧИК над полем ввода.

Ученик не знает, как сказать по-английски, и пишет по-русски (слово или
фразу) — здесь появляется английский вариант. Это НЕ отправка сообщения:
ученик сам решает, что делать дальше.

Кнопки:
  🔊 — послушать, как это звучит (голос Джейн);
  ↺  — вставить перевод В ПОЛЕ ВВОДА в место курсора (чтобы можно было
       продолжить писать по-английски, не набирая всё заново);
  ✕  — закрыть подсказку.

Почему без кнопки «Отправить»: у нас есть микрофон — естественный шаг после
подсказки не «отправить», а СКАЗАТЬ фразу вслух. Кнопка отправки подталкивала
читать, а цель проекта — говорение.

Полоса САМА прячется, когда подсказки нет (как info_bar и lesson_bar).
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

import theme

ICON_HINT = "\U0001F4A1"     # 💡
LISTEN_TEXT = "🔊"
INSERT_TEXT = "↺"
INSERT_TIP = "Вставить в поле ввода"
LISTEN_TIP = "Послушать, как это звучит"

MAX_LINES = 3                # сколько значений слова показываем


class HintBar(ctk.CTkFrame):
    """Строка-подсказка: «💡 key — Open the door with this key.  🔊 ↺ ✕»."""

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

        self.listen_btn = ctk.CTkButton(
            self, text=LISTEN_TEXT, command=self._listen, width=36, height=28,
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            text_color=palette["text"], cursor="hand2",
            corner_radius=theme.R["button"], border_width=1,
            border_color=palette["border"], font=theme.FONT_SMALL)
        self.listen_btn.pack(side="right", padx=(0, 6), pady=5)

        self.label = ctk.CTkLabel(self, text="", anchor="w", justify="left",
                                  font=theme.FONT_UI,
                                  text_color=palette["text"])
        self.label.pack(side="left", fill="x", expand=True, padx=(10, 6), pady=5)

    # ---------- данные ----------
    def show_translation(self, english: str, source: str = "") -> None:
        """Показать перевод одной строкой (фраза)."""
        english = str(english or "").strip()
        if not english:
            self.clear()
            return
        self._english = english
        text = "%s %s" % (ICON_HINT, english)
        source = str(source or "").strip()
        if source:
            text += "\n   «%s»" % source
        self.label.configure(text=text)
        self._show()

    def show_meanings(self, meanings, source: str = "") -> None:
        """Показать до трёх значений СЛОВА с примерами."""
        lines = [str(m).strip() for m in (meanings or []) if str(m).strip()]
        if not lines:
            self.clear()
            return
        lines = lines[:MAX_LINES]
        self._english = lines[0]
        text = "%s «%s»\n" % (ICON_HINT, str(source or "").strip()) \
            if source else "%s\n" % ICON_HINT
        text += "\n".join("   • %s" % line for line in lines)
        self.label.configure(text=text)
        self._show()

    def show_status(self, text: str) -> None:
        """Служебное сообщение (например, «перевожу…»)."""
        self._english = ""
        self.label.configure(text=str(text or ""))
        self._show()

    def show_note(self, text: str, english: str = "") -> None:
        """Показать пояснение (например, вердикт сверки произношения).

        english — фраза, которую по-прежнему можно послушать кнопкой 🔊:
        ученику важно услышать правильный вариант, а не только прочитать его.
        """
        self._english = str(english or "")
        self.label.configure(text=str(text or ""))
        self._show()

    def clear(self) -> None:
        self._english = ""
        self.label.configure(text="")
        self._hide()

    @property
    def english(self) -> str:
        return self._english

    @property
    def text(self) -> str:
        return str(self.label.cget("text") or "")

    @property
    def visible(self) -> bool:
        return self._visible

    # ---------- видимость ----------
    def _show(self) -> None:
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

    def _hide(self) -> None:
        if not self._visible:
            return
        try:
            self.pack_forget()
        except Exception:
            pass
        self._visible = False

    # ---------- кнопки ----------
    def _close(self) -> None:
        """Кнопка ✕: убрать подсказку и сообщить об этом приложению."""
        self.clear()
        if self._on_close is not None:
            try:
                self._on_close()
            except Exception:                          # noqa: BLE001
                pass

    def _insert(self) -> None:
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

    def _listen(self) -> None:
        if not self._english or self._on_listen is None:
            return
        try:
            self._on_listen(self._english)
        except Exception:                              # noqa: BLE001
            pass

    # ---------- оформление ----------
    def apply_theme(self, palette) -> None:
        self.palette = palette
        self.configure(fg_color=palette["surface_alt"])
        self.label.configure(text_color=palette["text"])
        for btn in (self.listen_btn, self.insert_btn):
            btn.configure(fg_color=palette["btn"],
                          hover_color=palette["btn_hover"],
                          text_color=palette["text"],
                          border_color=palette["border"])
        self.close_btn.configure(hover_color=palette["btn_hover"],
                                 text_color=palette["muted"])
