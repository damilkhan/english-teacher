# -*- coding: utf-8 -*-
"""ui.panels.block_panel — окно блока уроков (заглушка Этапа 1).

Открывается по клику на кружок карты. Показывает заголовок блока
(«Блок 1: Greetings») и ПРЕДПРОСМОТР уроков из curriculum.json.
Интерактивное дерево уроков (запуск/фильтры/ветвление) — следующий этап,
поэтому список здесь только для чтения.

Устроено как BootPanel: модальное CTkToplevel, transient + grab_set,
центрирование относительно родителя и classmethod ask() — так его удобно
глушить в тестах (BlockPanel.ask = staticmethod(lambda *a, **k: None)).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import customtkinter as ctk

import theme

# Тип урока → подпись для человека.
TYPE_LABELS = {
    "speaking": "говорение",
    "chat": "текст",
    "listening": "аудирование",
    "mixed": "смешанный",
}

WIDTH = 470
HEIGHT = 430


def block_title(point: Optional[Dict[str, Any]]) -> str:
    """Заголовок окна: «Блок 1: Greetings» (или что есть)."""
    point = point or {}
    number = point.get("number")
    title = str(point.get("block_title") or "").strip()
    head = "Блок %s" % number if number is not None else "Блок"
    return "%s: %s" % (head, title) if title else head


def lesson_rows(point: Optional[Dict[str, Any]]) -> List[tuple]:
    """Строки предпросмотра уроков: [(номер, название, подпись типа)].

    Вложенные `sublessons` показываются с отступом в номере (1.1.1).
    """
    rows: List[tuple] = []
    for lesson in (point or {}).get("lessons") or []:
        if not isinstance(lesson, dict):
            continue
        rows.append((str(lesson.get("id") or ""),
                     str(lesson.get("title") or ""),
                     TYPE_LABELS.get(str(lesson.get("type") or ""),
                                     str(lesson.get("type") or ""))))
        for sub in lesson.get("sublessons") or []:
            if not isinstance(sub, dict):
                continue
            rows.append((str(sub.get("id") or ""),
                         str(sub.get("title") or ""),
                         TYPE_LABELS.get(str(sub.get("type") or ""),
                                         str(sub.get("type") or ""))))
    return rows


class BlockPanel(ctk.CTkToplevel):
    """Модальное окно блока: заголовок + предпросмотр уроков."""

    def __init__(self, parent, palette, point=None, location_title=""):
        super().__init__(parent)
        self.palette = palette
        self.point = point or {}
        self.result = None
        self._closed = False

        self.title(block_title(self.point))
        self.configure(fg_color=palette["window"])
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._center(parent, WIDTH, HEIGHT)

        p = palette
        card = ctk.CTkFrame(self, fg_color=p["surface"], corner_radius=theme.R["card"])
        card.pack(fill="both", expand=True, padx=16, pady=16)

        head = block_title(self.point)
        subtitle = str(location_title or "").strip()
        rows = lesson_rows(self.point)
        subtitle = " · ".join(x for x in (subtitle, "%d %s" % (
            len(rows), _lessons_word(len(rows)))) if x)

        ctk.CTkLabel(card, text=head, anchor="w",
                     font=(theme.FONT_PANEL_TITLE[0], 17, "bold"),
                     text_color=p["text_strong"]).pack(anchor="w", padx=16, pady=(14, 0))
        ctk.CTkLabel(card, text=subtitle, anchor="w",
                     font=theme.FONT_SMALL,
                     text_color=p["muted"]).pack(anchor="w", padx=16, pady=(2, 10))

        # --- предпросмотр уроков (только чтение) ---
        box = ctk.CTkFrame(card, fg_color=p["surface_alt"],
                           corner_radius=theme.R["block"])
        box.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        if rows:
            for num, title, kind in rows:
                row = ctk.CTkFrame(box, fg_color="transparent")
                row.pack(fill="x", padx=12, pady=3)
                ctk.CTkLabel(row, text=num, width=54, anchor="w",
                             font=theme.FONT_SMALL,
                             text_color=p["muted"]).pack(side="left")
                ctk.CTkLabel(row, text=title, anchor="w",
                             font=theme.FONT_UI,
                             text_color=p["text"]).pack(side="left", padx=(4, 0))
                if kind:
                    ctk.CTkLabel(row, text=kind, anchor="e",
                                 font=theme.FONT_SMALL,
                                 text_color=p["cyan"]).pack(side="right")
        else:
            ctk.CTkLabel(box, text="Содержание появится позже.",
                         font=theme.FONT_UI, text_color=p["muted"]).pack(pady=22)

        ctk.CTkLabel(card, text="Скоро: интерактивное дерево уроков и запуск занятия.",
                     anchor="w", font=theme.FONT_SMALL,
                     text_color=p["muted"]).pack(anchor="w", padx=16, pady=(0, 8))

        ctk.CTkButton(card, text="Понятно", command=self._close,
                      fg_color=p["accent"], hover_color=p["accent_hover"],
                      text_color="#FFFFFF", height=38, cursor="hand2",
                      font=theme.FONT_UI, corner_radius=theme.R["button"]
                      ).pack(fill="x", padx=16, pady=(0, 16))

        self.after(80, self._grab)
        self.bind("<Escape>", lambda _e: self._close())

    # -----------------------------------------------------
    def _center(self, parent, w, h):
        try:
            parent.update_idletasks()
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 3)
        except Exception:
            x = y = 140
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, x), max(0, y)))

    def _grab(self):
        try:
            self.grab_set()
            self.lift()
        except Exception:
            pass

    def _close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    # -----------------------------------------------------
    @classmethod
    def ask(cls, parent, palette, point=None, location_title=""):
        """Показать окно блока и дождаться закрытия. Возвращает None."""
        panel = cls(parent, palette, point=point, location_title=location_title)
        try:
            parent.wait_window(panel)
        except Exception:
            pass
        return panel.result


def _lessons_word(n: int) -> str:
    """1 урок / 2 урока / 5 уроков."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return "урок"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "урока"
    return "уроков"
