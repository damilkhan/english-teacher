# -*- coding: utf-8 -*-
"""ui.widgets.chip_builder — КОНСТРУКТОР ПРЕДЛОЖЕНИЯ НА РУССКОМ (решение 101).

Панель под чатом. Чипы ТОЛЬКО на русском: ученик собирает русское
предложение, В ГОЛОВЕ переводит его и говорит по-английски в микрофон.
Английский на экран не попадает НИКОГДА — у чипа есть поле en, но оно
служит только движку реакций и в окне не показывается.

Набор чипов зависит от слота ТЕКУЩЕГО вопроса сцены (scene_chips.py).
Панель САМА прячется, когда сцены нет (как lesson_bar / hint_bar).

Кнопок в панели всего ДВЕ, и обе — про собранное предложение:
  • «✕»       — снять выбор (подсказка при наведении «Очистить»);
  • «Отправить» — общая кнопка окна, ниже панели.
Микрофон и 🔊 не дублируем (решение ученика 03.11.2026): «Запись» уже есть
внизу окна, а 🔊 живёт в облачке каждой реплики Вербота.
"""

from __future__ import annotations

from typing import List

import customtkinter as ctk

import scene_chips
import theme

try:
    from ui.widgets import tooltip as _tooltip
except Exception:                                      # pragma: no cover
    _tooltip = None

CLEAR_TEXT = "✕"
CLEAR_TIP = "Очистить"
EMPTY_TEXT = "Ты собрал: —"

# Ширина на «одну букву» и добавка на отступы кнопки: Tk не сообщает ширину
# до отрисовки, поэтому строки разбиваем по оценке (точность ±10 % — хватает).
CHAR_PX = 8.0
CHIP_PAD = 34
ROW_BUDGET = 980


class ChipBuilder(ctk.CTkFrame):
    """Панель-конструктор: чипы по-русски → строка «Ты собрал» → ✕."""

    def __init__(self, parent, palette, before=None):
        super().__init__(parent, fg_color=palette["surface_alt"],
                         corner_radius=theme.R["block"])
        self.palette = palette
        self._before = before
        self._visible = False
        self._slot = ""
        self._picked: List[dict] = []
        self._buttons: List[tuple] = []      # [(кнопка, чип)]

        # ---- чипы (строки создаются заново на каждый вопрос) ----
        self._chips_box = ctk.CTkFrame(self, fg_color="transparent")
        self._chips_box.pack(side="top", fill="x", padx=10, pady=(6, 0))

        # ---- низ панели: что собрано + одна кнопка «Очистить» ----
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(side="top", fill="x", padx=10, pady=(4, 6))

        self.clear_btn = ctk.CTkButton(
            bottom, text=CLEAR_TEXT, width=32, height=30,
            fg_color="transparent", hover_color=palette["btn_hover"],
            text_color=palette["muted"], cursor="hand2",
            corner_radius=theme.R["button"], border_width=1,
            border_color=palette["border"], font=theme.FONT_SMALL,
            command=self.reset)
        self.clear_btn.pack(side="right", padx=(8, 0))
        if _tooltip is not None:
            try:
                _tooltip.ToolTip(self.clear_btn, CLEAR_TIP, palette)
            except Exception:
                pass

        self.picked_label = ctk.CTkLabel(
            bottom, text=EMPTY_TEXT, anchor="w", justify="left", height=0,
            text_color=palette["text"], font=theme.FONT_SMALL)
        self.picked_label.pack(side="left", fill="x", expand=True)

    # ---------- данные ----------
    def show_slot(self, slot):
        """Построить чипы под слот текущего вопроса и показать панель."""
        slot = str(slot or "")
        if not slot or not scene_chips.has(slot):
            self.clear()
            return False
        self._slot = slot
        self.reset()
        rows = scene_chips.groups(slot)
        self._build_chips(rows)
        self._show()
        return True

    def reset(self):
        """Снять выбор (кнопка ✕ «Очистить»)."""
        self._picked = []
        self._paint()
        try:
            self.picked_label.configure(text=EMPTY_TEXT)
        except Exception:
            pass

    def clear(self):
        """Панель не нужна (сцена кончилась): убрать всё и спрятаться."""
        self._slot = ""
        self._picked = []
        self._clear_chips()
        self._hide()

    # ---------- чипы ----------
    def _clear_chips(self):
        for child in self._chips_box.winfo_children():
            child.destroy()
        self._buttons = []

    def _build_chips(self, rows):
        """Разложить чипы по строкам (оценка ширины) и создать кнопки."""
        self._clear_chips()
        lines: List[List[dict]] = [[]]
        width = 0
        for group in rows:
            for item in group["items"]:
                chip = {"group": group["key"], "ru": item["ru"], "en": item["en"]}
                need = CHIP_PAD + len(chip["ru"]) * CHAR_PX
                if lines[-1] and width + need > ROW_BUDGET:
                    lines.append([])
                    width = 0
                lines[-1].append(chip)
                width += need
        for line in lines:
            if not line:
                continue
            row = ctk.CTkFrame(self._chips_box, fg_color="transparent")
            row.pack(side="top", fill="x", pady=(0, 4))
            for chip in line:
                btn = ctk.CTkButton(
                    row, text=chip["ru"], width=int(CHIP_PAD + len(chip["ru"]) * CHAR_PX),
                    height=28, fg_color=self.palette["btn"],
                    hover_color=self.palette["btn_hover"],
                    text_color=self.palette["text"], cursor="hand2",
                    corner_radius=theme.R["button"], border_width=1,
                    border_color=self.palette["border"], font=theme.FONT_SMALL,
                    command=lambda c=chip: self._toggle(c))
                btn.pack(side="left", padx=(0, 6))
                self._buttons.append((btn, chip))

    def _toggle(self, chip):
        """Нажать чип: добавить к предложению; повторное нажатие — убрать."""
        if chip in self._picked:
            self._picked = [row for row in self._picked if row != chip]
        else:
            self._picked.append(chip)
        self._paint()

    def _paint(self):
        """Покрасить нажатые чипы и обновить строку «Ты собрал»."""
        for btn, chip in list(self._buttons):
            on = chip in self._picked
            try:
                btn.configure(fg_color=(self.palette["accent"] if on
                                        else self.palette["btn"]),
                              text_color=(self.palette["text_strong"] if on
                                          else self.palette["text"]))
            except Exception:
                pass
        text = scene_chips.compose(self._picked)["ru"]
        try:
            self.picked_label.configure(
                text=("Ты собрал: «%s»" % text) if text else EMPTY_TEXT)
        except Exception:
            pass

    @property
    def collected_ru(self):
        """Собранное предложение по-русски (для проверок)."""
        return scene_chips.compose(self._picked)["ru"]

    @property
    def collected_en(self):
        """Английский эквивалент собранного — ТОЛЬКО для движка реакций."""
        return scene_chips.compose(self._picked)["en"]

    @property
    def slot(self):
        return self._slot

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

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["surface_alt"])
        self.clear_btn.configure(hover_color=palette["btn_hover"],
                                 text_color=palette["muted"],
                                 border_color=palette["border"])
        self.picked_label.configure(text_color=palette["text"])
        self._paint()
        for btn, _chip in list(self._buttons):
            try:
                btn.configure(border_color=palette["border"])
            except Exception:
                pass
