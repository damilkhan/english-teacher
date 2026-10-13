# -*- coding: utf-8 -*-
"""ui.widgets.info_bar — тонкая строка «учительского» вида.

Показывает разбор Аналитика (что ученик сделал, есть ли ошибки, тема) и фокус
плана урока от Планировщика. Это СЛУЖЕБНАЯ информация для наглядности — в чат
такие строки не пишем (там они мешают). Полоса сама прячется, пока данных нет.
"""

import customtkinter as ctk

import theme

ICON_ANALYSIS = "\U0001F50E"   # 🔎
ICON_PLAN = "\U0001F4CB"       # 📋


class InfoBar(ctk.CTkFrame):
    """Строка над полем ввода: разбор Аналитика и фокус плана урока.

    Виджет САМ управляет своей видимостью: при пустых данных вызывается
    pack_forget(), при появлении текста — pack(side="bottom"). Родитель
    (левая колонка) упаковывает чат через side="top"/expand, поэтому полоса,
    упакованная ПОсле чата, встаёт ровно над полем ввода.
    """

    def __init__(self, parent, palette, before=None):
        super().__init__(parent, fg_color=palette["surface_alt"],
                         corner_radius=theme.R["block"])
        self.palette = palette
        # Виджет, ПЕРЕД которым вставать в порядке упаковки (обычно чат).
        # Без этого полоса, упакованная последней, на низком окне сжималась
        # до нуля — pack отдаёт место раньше стоящим виджетам.
        self._before = before
        self._analysis = ""
        self._plan = ""
        self._visible = False
        self.label = ctk.CTkLabel(self, text="", anchor="w", justify="left",
                                  font=theme.FONT_SMALL, text_color=palette["muted"])
        self.label.pack(side="left", fill="x", expand=True, padx=10, pady=3)

    # ---------- данные ----------
    def set_analysis(self, text):
        """Текст разбора Аналитика (пусто — скрыть эту часть)."""
        self._analysis = str(text or "").strip()
        self._refresh()

    def set_plan(self, text):
        """Фокус плана урока (пусто — скрыть эту часть)."""
        self._plan = str(text or "").strip()
        self._refresh()

    def clear(self):
        """Убрать оба поля и спрятать полосу."""
        self._analysis = ""
        self._plan = ""
        self._refresh()

    @property
    def text(self):
        return self.label.cget("text")

    # ---------- внутреннее ----------
    def _refresh(self):
        parts = []
        if self._analysis:
            parts.append("%s %s" % (ICON_ANALYSIS, self._analysis))
        if self._plan:
            parts.append("%s %s" % (ICON_PLAN, self._plan))
        if parts:
            self.label.configure(text="    ·    ".join(parts))
            self._show()
        else:
            self.label.configure(text="")
            self._hide()

    def _show(self):
        if not self._visible:
            kwargs = dict(side="bottom", fill="x", padx=theme.CARD_PAD, pady=(0, 6))
            if self._before is not None:
                kwargs["before"] = self._before
            self.pack(**kwargs)
            self._visible = True

    def _hide(self):
        if self._visible:
            self.pack_forget()
            self._visible = False

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["surface_alt"])
        self.label.configure(text_color=palette["muted"])
