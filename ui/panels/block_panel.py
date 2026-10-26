# -*- coding: utf-8 -*-
"""ui.panels.block_panel — окно блока уроков (запуск занятия).

Открывается по клику на кружок карты. Показывает заголовок блока
(«Блок 1: Greetings & Hello») и список уроков. Каждый урок можно НАЧАТЬ
кнопкой «▶» — окно закрывается и возвращает id выбранного урока, а
приложение запускает занятие (см. ui/app.py → on_point_click).

Устроено как BootPanel: модальное CTkToplevel, transient + grab_set,
центрирование относительно родителя и classmethod ask() — так его удобно
глушить в тестах (BlockPanel.ask = staticmethod(lambda *a, **k: None)).

Типы уроков: speaking (говорение), chat (текст), listening (аудирование).
mixed в интерфейсе не используется.
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
}

# Значок кнопки запуска (текстовый: ▶ рисуется шрифтом, эмодзи тут не нужны).
START_ICON = "▶"

# Кнопка «повторение слов»: окно закрывается и возвращает метку VOCAB_RESULT.
# id уроков выглядят как «1.1», «2.3», поэтому метку с ними не спутать.
VOCAB_TEXT = "📚  Повторить слова"
VOCAB_RESULT = "__vocab__"

# Урок недоступен (предыдущий не пройден): кнопка серая и не нажимается.
LOCKED_TEXT = "закрыто"

# Состояние урока, при котором начинать нельзя (см. progress_map).
STATE_LOCKED = "locked"

WIDTH = 480
HEIGHT = 440


def block_title(point: Optional[Dict[str, Any]]) -> str:
    """Заголовок окна: «Блок 1: Greetings» (или что есть)."""
    point = point or {}
    number = point.get("number")
    title = str(point.get("block_title") or "").strip()
    head = "Блок %s" % number if number is not None else "Блок"
    return "%s: %s" % (head, title) if title else head


def lesson_items(point: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Список уроков блока: [{"id","title","type","kind","depth"}, …].

    Вложенные `sublessons` идут с depth=1 (показываются с отступом).
    """
    items: List[Dict[str, Any]] = []

    def add(lesson: Dict[str, Any], depth: int) -> None:
        if not isinstance(lesson, dict):
            return
        ltype = str(lesson.get("type") or "")
        items.append({
            "id": str(lesson.get("id") or ""),
            "title": str(lesson.get("title") or ""),
            "type": ltype,
            "kind": TYPE_LABELS.get(ltype, ltype),
            "depth": depth,
        })
        for sub in lesson.get("sublessons") or []:
            add(sub, depth + 1)

    for lesson in (point or {}).get("lessons") or []:
        add(lesson, 0)
    return items


def lesson_rows(point: Optional[Dict[str, Any]]) -> List[tuple]:
    """Совместимость: строки [(id, title, подпись типа)] (см. lesson_items)."""
    return [(it["id"], it["title"], it["kind"]) for it in lesson_items(point)]


class BlockPanel(ctk.CTkToplevel):
    """Модальное окно блока: заголовок + список уроков с кнопками запуска."""

    def __init__(self, parent, palette, point=None, location_title="",
                 exams=None, states=None):
        super().__init__(parent)
        self.palette = palette
        self.point = point or {}
        # баллы экзаменов {id урока: плашка} — из profile_store.exam_badges
        self.exams = dict(exams or {})
        # состояния уроков {id урока: completed/unlocked/locked} — из карты
        self.states = dict(states or {})
        self.result = None            # id выбранного урока (или None)
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
        items = lesson_items(self.point)
        subtitle = " · ".join(x for x in (
            str(location_title or "").strip(),
            "%d %s" % (len(items), _lessons_word(len(items)))) if x)

        ctk.CTkLabel(card, text=head, anchor="w",
                     font=(theme.FONT_PANEL_TITLE[0], 17, "bold"),
                     text_color=p["text_strong"]).pack(anchor="w", padx=16, pady=(14, 0))
        ctk.CTkLabel(card, text=subtitle, anchor="w",
                     font=theme.FONT_SMALL,
                     text_color=p["muted"]).pack(anchor="w", padx=16, pady=(2, 10))

        # --- уроки блока (можно начать любой) ---
        box = ctk.CTkFrame(card, fg_color=p["surface_alt"],
                           corner_radius=theme.R["block"])
        box.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        if items:
            for item in items:
                self._lesson_row(box, item, p)
        else:
            ctk.CTkLabel(box, text="Содержание появится позже.",
                         font=theme.FONT_UI, text_color=p["muted"]).pack(pady=22)

        ctk.CTkLabel(card, text="Выбери урок — занятие начнётся в чате.",
                     anchor="w", font=theme.FONT_SMALL,
                     text_color=p["muted"]).pack(anchor="w", padx=16, pady=(0, 8))

        # --- нижний ряд: повторение слов + закрыть ---
        # Повторение не привязано к конкретному уроку, поэтому кнопка ОДНА
        # на весь блок. Её смысл — открыть окно «Повторение» в любой момент
        # (проверить, как оно выглядит), даже если сегодня уже повторяли:
        # тогда окно само скажет «повторять нечего».
        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkButton(bottom, text="Закрыть", command=self._close,
                      width=110, height=38,
                      fg_color=p["btn"], hover_color=p["btn_hover"],
                      text_color=p["text"], cursor="hand2",
                      font=theme.FONT_UI, corner_radius=theme.R["button"],
                      border_width=1, border_color=p["border"]
                      ).pack(side="right")

        ctk.CTkButton(bottom, text=VOCAB_TEXT, command=self._pick_vocab,
                      height=38, fg_color=p["btn"], hover_color=p["btn_hover"],
                      text_color=p["text"], cursor="hand2",
                      font=theme.FONT_UI, corner_radius=theme.R["button"],
                      border_width=1, border_color=p["border"]
                      ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.after(80, self._grab)
        self.bind("<Escape>", lambda _e: self._close())

    # -----------------------------------------------------
    def _lesson_row(self, parent, item: Dict[str, Any], p) -> None:
        """Строка одного урока: название · тип · балл · кнопка «Начать».

        Закрытый урок (предыдущий не пройден) начать НЕЛЬЗЯ: кнопка серая,
        без нажатия. Балл экзамена пишется рядом с кнопкой.
        """
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=3)

        locked = self.states.get(item["id"]) == STATE_LOCKED
        start_btn = ctk.CTkButton(
            row, text=LOCKED_TEXT if locked else ("%s  Начать" % START_ICON),
            width=104, height=28,
            fg_color=p["btn"] if locked else p["accent"],
            hover_color=p["btn_hover"] if locked else p["accent_hover"],
            text_color=p["muted"] if locked else "#FFFFFF",
            cursor="arrow" if locked else "hand2",
            border_width=1 if locked else 0, border_color=p["border"],
            corner_radius=theme.R["button"], font=theme.FONT_SMALL,
            state="disabled" if locked else "normal",
            command=lambda lid=item["id"]: self._pick(lid))
        start_btn.pack(side="right", padx=(8, 0))

        badge = self.exams.get(item["id"]) or ""
        if badge:
            ctk.CTkLabel(row, text=badge, anchor="e", width=64,
                         font=theme.FONT_SMALL,
                         text_color=(p.get("map_done") or p["cyan"])
                         if "\u2713" in badge else p["warn"]
                         ).pack(side="right", padx=(8, 0))

        if item.get("kind"):
            ctk.CTkLabel(row, text=item["kind"], anchor="e",
                         font=theme.FONT_SMALL,
                         text_color=p["cyan"]).pack(side="right", padx=(8, 0))

        title_lbl = ctk.CTkLabel(row, text=item.get("title") or "", anchor="w",
                                 font=theme.FONT_UI, text_color=p["text"])
        title_lbl.pack(side="left", padx=(4 + 14 * int(item.get("depth") or 0), 0))

    # -----------------------------------------------------
    def _pick(self, lesson_id: str) -> None:
        """Выбран урок: запомнить и закрыть окно."""
        self.result = str(lesson_id or "") or None
        self._close()

    def _pick_vocab(self) -> None:
        """«Повторить слова»: окно закроется и вернёт метку VOCAB_RESULT."""
        self.result = VOCAB_RESULT
        self._close()

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
    def ask(cls, parent, palette, point=None, location_title="",
            exams=None, states=None):
        """Показать окно и дождаться закрытия.

        Возвращает id выбранного урока, VOCAB_RESULT (нажали «Повторить
        слова») или None (окно закрыли).
        """
        panel = cls(parent, palette, point=point, location_title=location_title,
                    exams=exams, states=states)
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
