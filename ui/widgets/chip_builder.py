# -*- coding: utf-8 -*-
"""ui.widgets.chip_builder — КОНСТРУКТОР ПРЕДЛОЖЕНИЯ НА РУССКОМ (решение 101).

Панель под чатом. Чипы ТОЛЬКО на русском: ученик собирает русское
предложение, В ГОЛОВЕ переводит его и говорит по-английски в микрофон.
Английский на экран не попадает НИКОГДА — у чипа есть поле en, но оно
служит только движку реакций и в окне не показывается.

Набор чипов зависит от слота ТЕКУЩЕГО вопроса сцены (scene_chips.py).
Панель САМА прячется, когда сцены нет (как lesson_bar / hint_bar).

Раскладка: чипы в 1–2 строки (перенос по оценке ширины — Tk не умеет
flow-раскладку), ниже строка «Ты собрал: «…»» и кнопки 🔊 / ↺ / 🎤.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import customtkinter as ctk

import scene_chips
import theme

MIC_TEXT = "🎤 сказать"
REPLAY_TEXT = "🔊"
RESET_TEXT = "↺"
EMPTY_TEXT = "Ты собрал: —"

# Ширина на «одну букву» и добавка на отступы кнопки: Tk не сообщает ширину
# до отрисовки, поэтому строки разбиваем по оценке (точность ±10 % — хватает).
CHAR_PX = 8.0
CHIP_PAD = 34
ROW_BUDGET = 980


class ChipBuilder(ctk.CTkFrame):
    """Панель-конструктор: чипы по-русски → «Ты собрал» → 🎤 сказать."""

    def __init__(self, parent, palette,
                 on_record: Optional[Callable[[], None]] = None,
                 on_record_release: Optional[Callable[[], None]] = None,
                 on_replay: Optional[Callable[[], None]] = None,
                 before=None):
        super().__init__(parent, fg_color=palette["surface_alt"],
                         corner_radius=theme.R["block"])
        self.palette = palette
        self._on_record = on_record
        self._on_record_release = on_record_release
        self._on_replay = on_replay
        self._before = before
        self._visible = False
        self._slot = ""
        self._replay_text = ""
        self._picked: List[dict] = []
        self._buttons: List[tuple] = []      # [(кнопка, чип)]

        # ---- чипы (строки создаются заново на каждый вопрос) ----
        self._chips_box = ctk.CTkFrame(self, fg_color="transparent")
        self._chips_box.pack(side="top", fill="x", padx=10, pady=(6, 0))

        # ---- низ панели: что собрано + кнопки ----
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(side="top", fill="x", padx=10, pady=(4, 6))

        self.mic_btn = ctk.CTkButton(
            bottom, text=MIC_TEXT, width=120, height=30,
            fg_color=palette["accent"], hover_color=palette["accent_hover"],
            text_color=palette["text"], cursor="hand2",
            corner_radius=theme.R["button"], font=theme.FONT_SMALL)
        self.mic_btn.pack(side="right", padx=(8, 0))
        # Микрофон — «нажми и держи», как кнопка «Запись» внизу окна.
        self.mic_btn.bind("<ButtonPress-1>", lambda _e: self._record(True), add="+")
        self.mic_btn.bind("<ButtonRelease-1>", lambda _e: self._record(False), add="+")

        self.replay_btn = ctk.CTkButton(
            bottom, text=REPLAY_TEXT, width=36, height=30,
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            text_color=palette["text"], cursor="hand2",
            corner_radius=theme.R["button"], border_width=1,
            border_color=palette["border"], font=theme.FONT_SMALL,
            command=self._replay)
        self.replay_btn.pack(side="right", padx=(8, 0))

        self.reset_btn = ctk.CTkButton(
            bottom, text=RESET_TEXT, width=36, height=30,
            fg_color="transparent", hover_color=palette["btn_hover"],
            text_color=palette["muted"], cursor="hand2",
            corner_radius=theme.R["button"], font=theme.FONT_SMALL,
            command=self.reset)
        self.reset_btn.pack(side="right", padx=(8, 0))

        self.picked_label = ctk.CTkLabel(
            bottom, text=EMPTY_TEXT, anchor="w", justify="left", height=0,
            text_color=palette["text"], font=theme.FONT_SMALL)
        self.picked_label.pack(side="left", fill="x", expand=True)

    # ---------- данные ----------
    def show_slot(self, slot, replay_text="", title=""):
        """Построить чипы под слот текущего вопроса и показать панель.

        replay_text — английский вопрос: он НЕ показывается, а только
        запоминается, чтобы 🔊 прочитал его ещё раз.
        """
        slot = str(slot or "")
        if not slot or not scene_chips.has(slot):
            self.clear()
            return False
        self._slot = slot
        self._replay_text = str(replay_text or "")
        self.reset()
        rows = scene_chips.groups(slot)
        self._build_chips(rows)
        self._show()
        return True

    def reset(self):
        """Снять выбор (кнопка ↺)."""
        self._picked = []
        self._paint()
        try:
            self.picked_label.configure(text=EMPTY_TEXT)
        except Exception:
            pass

    def clear(self):
        """Панель не нужна (сцена кончилась): убрать всё и спрятаться."""
        self._slot = ""
        self._replay_text = ""
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

    # ---------- кнопки ----------
    def _replay(self):
        if self._on_replay is None or not self._replay_text:
            return
        try:
            self._on_replay(self._replay_text)
        except Exception as exc:                       # noqa: BLE001
            print("⚠️ Вопрос не озвучен повторно: %s" % exc)

    def _record(self, start: bool):
        cb = self._on_record if start else self._on_record_release
        if cb is None:
            return
        try:
            cb()
        except Exception as exc:                       # noqa: BLE001
            print("⚠️ Микрофон панели: %s" % exc)

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
        self.mic_btn.configure(fg_color=palette["accent"],
                               hover_color=palette["accent_hover"],
                               text_color=palette["text"])
        self.replay_btn.configure(fg_color=palette["btn"],
                                  hover_color=palette["btn_hover"],
                                  text_color=palette["text"],
                                  border_color=palette["border"])
        self.reset_btn.configure(hover_color=palette["btn_hover"],
                                 text_color=palette["muted"])
        self.picked_label.configure(text_color=palette["text"])
        self._paint()
        for btn, _chip in list(self._buttons):
            try:
                btn.configure(border_color=palette["border"])
            except Exception:
                pass
