# -*- coding: utf-8 -*-
"""ui.panels.vocab_panel — окно «Повторение слов».

Ученик видит РУССКОЕ слово и английский пример с пропуском:

    Скажи по-английски:
       ключ
       Open the door with this ___.

Дальше он говорит в микрофон (кнопка «Запись», нажать и держать), а окно
показывает вердикт сверки произношения: «✅ Похоже!», «🟡 Почти» или
«🔁 Попробуй ещё». Уровень карточки двигает контроллер — окно только
показывает (см. controllers/vocabulary_controller.py).

Почему кнопки «Подсказка» нет в главном окне, а здесь есть: в повторении
ученик мог просто забыть слово. Подсказка берётся ИЗ КАРТОЧКИ (модель и
сеть не нужны) и засчитывается как промах — слово не вспомнилось само.

Устроено как BlockPanel: модальное CTkToplevel, transient + grab_set,
центрирование относительно родителя. Модальность не мешает ни микрофону,
ни озвучке — grab_set блокирует только клики по главному окну.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

import theme

WIDTH = 560
HEIGHT = 486

# Подписи кнопок (эмодзи тут текстовые: в кнопках они читаются нормально)
RECORD_TEXT = "🎤  Запись"
RECORD_ACTIVE = "🔴  Отпусти — проверить"
LISTEN_TEXT = "🔊  Послушать"
HINT_TEXT = "💡  Подсказка"
LATER_TEXT = "Позже"
NEXT_TEXT = "Дальше  ▶"


class VocabPanel(ctk.CTkToplevel):
    """Окно повторения: одно слово за раз, вердикт, итог захода."""

    def __init__(self, parent, palette, controller,
                 on_record_start: Optional[Callable[[], None]] = None,
                 on_record_stop: Optional[Callable[[], None]] = None,
                 on_say: Optional[Callable[[str], None]] = None,
                 on_finish: Optional[Callable[[dict], None]] = None):
        super().__init__(parent)
        self.palette = palette
        self.controller = controller
        self._on_record_start = on_record_start
        self._on_record_stop = on_record_stop
        self._on_say = on_say
        self._on_finish = on_finish
        self._open = True
        self._answered = False       # по текущему слову уже показан итог
        self._finished = False

        self.title("Повторение слов")
        self.configure(fg_color=palette["window"])
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._center(parent, WIDTH, HEIGHT)

        self._build()
        self._show_card()

        self.after(80, self._grab)
        self.bind("<Escape>", lambda _e: self._close())

    # -----------------------------------------------------
    # Сборка
    # -----------------------------------------------------
    def _build(self) -> None:
        p = self.palette
        card = ctk.CTkFrame(self, fg_color=p["surface"],
                            corner_radius=theme.R["card"])
        card.pack(fill="both", expand=True, padx=16, pady=16)
        self.card = card

        ctk.CTkLabel(card, text="📚 Повторение слов", anchor="w",
                     font=(theme.FONT_PANEL_TITLE[0], 18, "bold"),
                     text_color=p["text_strong"]).pack(anchor="w", padx=18, pady=(16, 2))
        self.counter_lbl = ctk.CTkLabel(card, text="", anchor="w",
                                        font=theme.FONT_SMALL, text_color=p["muted"])
        self.counter_lbl.pack(anchor="w", padx=18)

        self.bar = ctk.CTkProgressBar(card, height=8, corner_radius=4,
                                      fg_color=p["surface_alt"],
                                      progress_color=p["accent"])
        self.bar.set(0)
        self.bar.pack(fill="x", padx=18, pady=(10, 12))

        # --- задание ---
        body = ctk.CTkFrame(card, fg_color=p["surface_alt"],
                            corner_radius=theme.R["block"])
        body.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        self.prompt_lbl = ctk.CTkLabel(body, text="Скажи по-английски:",
                                       font=theme.FONT_SMALL, text_color=p["muted"])
        self.prompt_lbl.pack(anchor="w", padx=18, pady=(16, 0))

        self.word_lbl = ctk.CTkLabel(body, text="", anchor="w",
                                     font=(theme.FONT_PANEL_TITLE[0], 30, "bold"),
                                     text_color=p["text_strong"])
        self.word_lbl.pack(anchor="w", padx=18, pady=(0, 6))

        self.example_lbl = ctk.CTkLabel(body, text="", anchor="w", justify="left",
                                        wraplength=470, font=theme.FONT_UI,
                                        text_color=p["muted"])
        self.example_lbl.pack(anchor="w", padx=18, pady=(0, 6))

        self.verdict_lbl = ctk.CTkLabel(body, text="", anchor="w", justify="left",
                                        wraplength=470, font=theme.FONT_UI,
                                        text_color=p["text"])
        self.verdict_lbl.pack(anchor="w", padx=18, pady=(0, 14))

        # --- кнопки: главная «Запись» удержанием ---
        self.record_btn = ctk.CTkButton(
            card, text=RECORD_TEXT, height=46, cursor="hand2",
            fg_color=p["accent"], hover_color=p["accent_hover"],
            text_color="#FFFFFF", font=theme.FONT_UI,
            corner_radius=theme.R["button"])
        self.record_btn.pack(fill="x", padx=18, pady=(0, 8))
        # push-to-talk: command не задаём, ловим нажатие и отпускание сами
        self.record_btn.bind("<ButtonPress-1>", lambda _e: self._record(True), add="+")
        self.record_btn.bind("<ButtonRelease-1>", lambda _e: self._record(False), add="+")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 10))
        self.listen_btn = self._small(row, LISTEN_TEXT, self._listen)
        self.listen_btn.pack(side="left")
        self.hint_btn = self._small(row, HINT_TEXT, self._hint)
        self.hint_btn.pack(side="left", padx=(8, 0))
        self.next_btn = self._small(row, NEXT_TEXT, self._next, accent=True)
        self.next_btn.pack(side="right")
        self.later_btn = self._small(row, LATER_TEXT, self._later)
        self.later_btn.pack(side="right", padx=(0, 8))

        self.hint_lbl = ctk.CTkLabel(
            card, text="Зажми «Запись», скажи слово — и отпусти.",
            anchor="w", font=theme.FONT_SMALL, text_color=p["muted"])
        self.hint_lbl.pack(anchor="w", padx=18, pady=(0, 14))

    def _small(self, parent, text, command, accent=False):
        p = self.palette
        return ctk.CTkButton(
            parent, text=text, command=command, width=132, height=38,
            cursor="hand2", font=theme.FONT_SMALL,
            corner_radius=theme.R["button"],
            fg_color=p["accent"] if accent else p["btn"],
            hover_color=p["accent_hover"] if accent else p["btn_hover"],
            text_color="#FFFFFF" if accent else p["text"],
            border_width=0 if accent else 1, border_color=p["border"])

    # -----------------------------------------------------
    # Показ слова
    # -----------------------------------------------------
    def _show_card(self) -> None:
        """Показать текущую карточку (или итог, если заход закончен)."""
        card = self.controller.current()
        if card is None:
            self._show_result()
            return
        self._answered = False
        total = max(1, self.controller.total)
        self.counter_lbl.configure(
            text="Слово %d из %d" % (self.controller.position, total))
        try:
            self.bar.set(min(1.0, (self.controller.position - 1) / float(total)))
        except Exception:
            pass
        self.word_lbl.configure(text=card["word"] or "—", text_color=self.palette["text_strong"])
        example = card.get("gap") or card.get("example") or ""
        self.example_lbl.configure(text=example, text_color=self.palette["muted"])
        self.verdict_lbl.configure(text="", text_color=self.palette["text"])
        self.hint_lbl.configure(text="Зажми «Запись», скажи слово — и отпусти.",
                                text_color=self.palette["muted"])
        self._set_answer_buttons(True)

    def _set_answer_buttons(self, answering: bool) -> None:
        """Пока ответ не дан — «Дальше» не нужна (она закрывает слово)."""
        try:
            self.next_btn.configure(state="normal" if not answering else "disabled")
        except Exception:
            pass

    # -----------------------------------------------------
    # Ответ ученика (текст приходит из распознавания)
    # -----------------------------------------------------
    def accept_text(self, text) -> None:
        """Главный поток: ученик что-то сказал — сверить и показать вердикт."""
        if not self._open or self._finished:
            return
        result = self.controller.answer(text)
        status = result.get("status")
        if status == "no_card":
            return
        if status == "russian":
            language_line = "Ты сказал по-русски: «%s»." % result.get("heard", "")
            self._show_lines(language_line,
                             "По-английски: «%s»" % result.get("en", ""),
                             color_key="muted")
            self.hint_lbl.configure(text="Скажи это по-английски в микрофон.",
                                    text_color=self.palette["muted"])
            return
        if status == "unrelated":
            self.hint_lbl.configure(
                text="Не расслышал слово. Попробуй ещё раз — или нажми 💡 Подсказка.",
                text_color=self.palette["muted"])
            return
        if status == "empty":
            return

        self._answered = True
        self._set_answer_buttons(False)
        if status == "good":
            self._show_good(result)
        else:
            self._show_miss(result, text)

    def _show_good(self, result) -> None:
        """Удачный ответ: «✅ Похоже!» и уровень +1."""
        card = self.controller.current() or {}
        english = card.get("en") or ""
        lines = ["✅ Похоже! «%s»" % english]
        if result.get("learned"):
            lines.append("🌟 Слово выучено — больше не спрошу.")
        elif self._level_changed(result):
            lines.append("Уровень %s → %s." % (result.get("level_from"), result.get("level_to")))
        self._show_lines(lines[0], " ".join(lines[1:]), color_key="ok")
        self.hint_lbl.configure(text="Нажми «Дальше».", text_color=self.palette["muted"])
        if self._on_say is not None:
            # короткая похвала голосом — как в уроке
            try:
                self._on_say("Good!")
            except Exception:
                pass

    def _show_miss(self, result, heard) -> None:
        """Промах: «🟡 Почти» / «🔁 Попробуй» и уровень −1."""
        report = result.get("report")
        message = str(getattr(report, "message", "") or "").strip()
        lines = [message or "🔁 Попробуй ещё"]
        if self._level_changed(result):
            lines.append("Уровень %s → %s." % (result.get("level_from"), result.get("level_to")))
        self._show_lines(lines[0], " ".join(lines[1:]), color_key="warn")
        self.hint_lbl.configure(
            text="Можно повторить: 🔊 послушай и скажи ещё раз, или загляни в 💡 Подсказку.",
            text_color=self.palette["muted"])

    @staticmethod
    def _level_changed(result) -> bool:
        """Уровень реально сдвинулся (0 → 0 — это не сдвиг, писать нечего)."""
        return (bool((result or {}).get("changed"))
                and result.get("level_from") != result.get("level_to"))

    def _show_lines(self, main, extra, color_key="text") -> None:
        text = str(main or "")
        if extra:
            text += "\n" + str(extra)
        self.verdict_lbl.configure(text=text,
                                   text_color=self.palette.get(color_key, self.palette["text"]))

    # -----------------------------------------------------
    # Кнопки
    # -----------------------------------------------------
    def _record(self, pressed: bool) -> None:
        """Запись «нажать и держать» (как в главном окне)."""
        if self._finished:
            return
        callback = self._on_record_start if pressed else self._on_record_stop
        if callback is None:
            return
        try:
            callback()
        except Exception as exc:                       # noqa: BLE001
            print("⚠️ Запись в повторении не сработала: %s" % exc)

    def set_recording(self, recording: bool) -> None:
        """Вид кнопки записи во время записи."""
        p = self.palette
        try:
            if recording:
                self.record_btn.configure(text=RECORD_ACTIVE, fg_color=p["record"],
                                          hover_color=p["record"])
            else:
                self.record_btn.configure(text=RECORD_TEXT, fg_color=p["accent"],
                                          hover_color=p["accent_hover"])
        except Exception:
            pass

    def _listen(self) -> None:
        """🔊 послушать правильный ответ (пример, иначе само слово)."""
        card = self.controller.current() or {}
        text = card.get("example") or card.get("en") or ""
        if text and self._on_say is not None:
            try:
                self._on_say(text)
            except Exception as exc:                   # noqa: BLE001
                print("⚠️ Озвучка в повторении не сработала: %s" % exc)

    def _hint(self) -> None:
        """💡 подсказка из карточки — это промах (слово не вспомнилось само)."""
        result = self.controller.reveal()
        if result.get("status") != "hint":
            return
        self._answered = True
        self._set_answer_buttons(False)
        main = "💡 По-английски: «%s»" % result.get("en", "")
        example = str(result.get("example") or "").strip()
        self._show_lines(main, ("Пример: %s" % example) if example else "", color_key="cyan")
        note = "Подсказка считается промахом: завтра спрошу снова."
        if self._level_changed(result):
            note += " Уровень %s → %s." % (result.get("level_from"), result.get("level_to"))
        self.hint_lbl.configure(text=note, text_color=self.palette["muted"])

    def _later(self) -> None:
        """«Позже»: без изменений, слово вернётся в следующий раз."""
        if self.controller.skip() is not None:
            self._next()

    def _next(self) -> None:
        """Следующее слово или итог захода."""
        if self.controller.next():
            self._show_card()
        else:
            self._show_result()

    # -----------------------------------------------------
    # Итог
    # -----------------------------------------------------
    def _show_result(self) -> None:
        if self._finished:
            return
        self._finished = True
        stats = self.controller.summary()
        p = self.palette
        self._set_answer_buttons(False)
        try:
            self.bar.set(1.0)
        except Exception:
            pass
        self.counter_lbl.configure(text="Заход закончен")
        self.word_lbl.configure(text="Готово!", text_color=p["text_strong"])
        self.example_lbl.configure(text="", text_color=p["muted"])
        self._show_lines(
            "Верно: %d · промахи: %d · отложено: %d"
            % (stats.get("good", 0), stats.get("miss", 0), stats.get("skipped", 0)),
            "Завтра спрошу то, что не получается.", color_key="ok")
        for btn in (self.record_btn, self.hint_btn, self.later_btn, self.listen_btn):
            try:
                btn.configure(state="disabled")
            except Exception:
                pass
        try:
            self.next_btn.configure(text="Готово", state="normal",
                                    command=self._done)
        except Exception:
            pass
        self.hint_lbl.configure(text="Слова повторяются по лестнице: 1 → 3 → 7 → 21 день.",
                                text_color=p["muted"])

    def _done(self) -> None:
        """Кнопка «Готово» на итоговом экране."""
        self._close()

    # -----------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def finished(self) -> bool:
        return self._finished

    def _center(self, parent, w, h):
        try:
            parent.update_idletasks()
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 2)
        except Exception:
            x = y = 140
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, x), max(0, y)))

    def _grab(self):
        try:
            self.grab_set()
            self.lift()
        except Exception:
            pass

    def _close(self) -> None:
        if not self._open:
            return
        self._open = False
        if self._on_finish is not None:
            # отдаём приложению сводку: обновить «Профиль» (и после конца тоже)
            try:
                self._on_finish(self.controller.summary())
            except Exception:
                pass
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
