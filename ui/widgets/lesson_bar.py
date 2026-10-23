# -*- coding: utf-8 -*-
"""ui.widgets.lesson_bar — полоса идущего ЗАНЯТИЯ над полем ввода.

Показывает: какой урок идёт, его тип, прогресс («4/12») и кнопку «Выйти».
Полоса САМА прячется, когда занятия нет (как InfoBar).

ГДЕ ЖИВЁТ (решение ученика 23.10.2026): ВНУТРИ колонки ввода, над полем.
Раньше она стояла в области чата и, появляясь, отнимала высоту У ЧАТА.
Теперь её высота берётся у поля ввода: поле сжимается на высоту полосы,
а чат не меняется. Для этого родитель — колонка ввода, а before — само
поле (pack отдаёт место раньше упакованным).
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

import theme

ICON_LESSON = "\U0001F393"      # 🎓
EXIT_TEXT = "Выйти"


class LessonBar(ctk.CTkFrame):
    """Полоса урока: «🎓 Урок 1.1 · Hello / Hi · говорение · 4/12  [Выйти]»."""

    def __init__(self, parent, palette, on_exit: Optional[Callable[[], None]] = None,
                 before=None):
        super().__init__(parent, fg_color=palette["accent_soft"],
                         corner_radius=theme.R["block"])
        self.palette = palette
        self._before = before
        self._visible = False

        self.label = ctk.CTkLabel(self, text="", anchor="w", justify="left",
                                  font=theme.FONT_SMALL,
                                  text_color=palette["text"])
        self.label.pack(side="left", fill="x", expand=True, padx=(10, 6), pady=4)

        self.exit_btn = ctk.CTkButton(
            self, text=EXIT_TEXT, command=on_exit, width=76, height=26,
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            text_color=palette["text"], cursor="hand2",
            corner_radius=theme.R["button"], border_width=1,
            border_color=palette["border"], font=theme.FONT_SMALL)
        self.exit_btn.pack(side="right", padx=(0, 8), pady=4)

    # ---------- данные ----------
    def set_lesson(self, label: str, kind: str, progress: str) -> None:
        """Показать полосу: название урока, тип и прогресс."""
        parts = [ICON_LESSON, str(label or "").strip()]
        if kind:
            parts.append("· %s" % kind)
        if progress:
            parts.append("· %s" % progress)
        self.label.configure(text=" ".join(p for p in parts if p))
        self._show()

    def set_progress(self, progress: str) -> None:
        """Обновить только счётчик (без пересборки строки целиком)."""
        text = str(self.label.cget("text") or "")
        head = text.split(" · ")[:3]
        # держим ровно один блок прогресса в конце
        head = [p for p in head if not _looks_like_progress(p)]
        if progress:
            head.append("· %s" % progress)
        self.label.configure(text=" ".join(p for p in head if p).strip())

    def clear(self) -> None:
        """Спрятать полосу (занятие закончилось)."""
        self.label.configure(text="")
        self._hide()

    @property
    def text(self) -> str:
        return str(self.label.cget("text") or "")

    # ---------- видимость ----------
    def _show(self) -> None:
        if self._visible:
            return
        # side="top" — полоса встаёт НАД полем ввода внутри колонки ввода,
        # поэтому её высоту отдаёт поле, а не чат.
        kwargs = dict(side="top", fill="x", padx=0, pady=(0, 6))
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

    @property
    def visible(self) -> bool:
        return self._visible

    # ---------- оформление ----------
    def apply_theme(self, palette) -> None:
        self.palette = palette
        self.configure(fg_color=palette["accent_soft"])
        self.label.configure(text_color=palette["text"])
        self.exit_btn.configure(fg_color=palette["btn"],
                                hover_color=palette["btn_hover"],
                                text_color=palette["text"],
                                border_color=palette["border"])


def _looks_like_progress(text: str) -> bool:
    """Похоже на «4/12»? (для аккуратного обновления счётчика)."""
    body = str(text or "").strip().lstrip("·").strip()
    if not body:
        return False
    left, sep, right = body.partition("/")
    return bool(sep) and left.isdigit() and right.isdigit()
