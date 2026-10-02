# -*- coding: utf-8 -*-
# =========================================================
# UI/PANELS/LEVEL_TEST_PANEL.PY — окно адаптивного теста уровня
# =========================================================
# Модальное окно (как FirstRunForm): один вопрос и 4 варианта ответа,
# прогресс, обратная связь по каждому ответу и финальный экран с уровнем.
#
# Логику теста панель НЕ знает — она дергает LevelTestController, а тот
# уже гоняет level_test в фоновом потоке и возвращает всё через dispatch.
#
# РЕШЕНИЕ B — ждём готовности модели:
#   Если передан ready_probe (callable), панель НЕ начинает тест сразу, а
#   показывает экран «⏳ Модель загружается…» и опрашивает пробу. Варианты
#   и прогресс в это время скрыты, доступна только кнопка «Прервать тест».
#   Как только проба вернёт "ready" (ready) — вызывается _begin().
#   Так первые вопросы не уходят молча в резервный банк и уровень точнее.
#
# Закрытие окна = прерывание: подтверждаем, зовём controller.cancel(),
# и в профиль НИЧЕГО не пишем (уровень сохраняется только в get_result).
#
# Возвращает строку уровня ("A1".."C1") или None, если тест прервали.
# =========================================================

from tkinter import messagebox

import customtkinter as ctk

import level_test
import theme

# как часто спрашиваем у пробы, готова ли модель (мс)
POLL_MS = 700


class LevelTestPanel(ctk.CTkToplevel):
    def __init__(self, parent, palette, controller, user_id, ready_probe=None):
        super().__init__(parent)
        self.palette = palette
        self.controller = controller
        self.user_id = int(user_id)
        self.ready_probe = ready_probe     # callable → ждём готовности (решение B)
        self.result_level = None
        self._finished = False
        self._aborted = False
        self._wait_job = None

        self.title("Тест уровня английского")
        self.configure(fg_color=palette["window"])
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center(parent, 580, 560)

        self._build_quiz()
        self._build_wait()
        self._build_result()

        self.after(80, self._grab)
        self.after(150, self._start_flow)

    # -----------------------------------------------------
    # Переключение экранов (вопрос / ожидание / результат)
    # -----------------------------------------------------
    def _show(self, frame):
        """Показать ровно один из трёх экранов."""
        for other in (self.quiz_frame, self.wait_frame, self.result_frame):
            if other is not frame:
                try:
                    other.pack_forget()
                except Exception:
                    pass
        try:
            if not frame.winfo_ismapped():
                frame.pack(fill="both", expand=True)
        except Exception:
            frame.pack(fill="both", expand=True)

    def _show_quiz(self):
        self._stop_spinner()
        self._show(self.quiz_frame)

    def _show_wait(self):
        self._start_spinner()
        self._show(self.wait_frame)

    # -----------------------------------------------------
    # Сборка: экран вопросов
    # -----------------------------------------------------
    def _build_quiz(self):
        p = self.palette
        self.quiz_frame = ctk.CTkFrame(self, fg_color="transparent")
        # не pack'аем здесь: экран покажет _start_flow (quiz / wait)

        head = ctk.CTkFrame(self.quiz_frame, fg_color=p["surface"],
                            corner_radius=theme.R["card"])
        head.pack(fill="x", padx=18, pady=(18, 12))
        ctk.CTkLabel(head, text="Тест уровня", font=(theme.FONT_PANEL_TITLE[0], 18, "bold"),
                     text_color=p["text_strong"]).pack(anchor="w", padx=18, pady=(16, 2))
        self.progress_lbl = ctk.CTkLabel(
            head, text="Определяю уровень A1–C1 — отвечай на вопросы.",
            font=theme.FONT_SMALL, text_color=p["muted"], justify="left")
        self.progress_lbl.pack(anchor="w", padx=18, pady=(0, 8))

        # прогресс-бар: «вопрос N / ≤15»
        self.progress_bar = ctk.CTkProgressBar(
            head, height=8, corner_radius=4,
            fg_color=p["surface_alt"], progress_color=p["accent"])
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=18, pady=(0, 16))

        body = ctk.CTkFrame(self.quiz_frame, fg_color=p["surface_alt"],
                            corner_radius=theme.R["block"])
        body.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        self.question_lbl = ctk.CTkLabel(
            body, text="⏳ Готовлю первый вопрос…", wraplength=500, justify="left",
            font=(theme.FONT_UI[0], 15), text_color=p["text_strong"])
        self.question_lbl.pack(anchor="w", padx=18, pady=(18, 12))

        self.option_buttons = []
        for i in range(4):
            btn = ctk.CTkButton(
                body, text="", anchor="w", height=44, cursor="hand2",
                font=theme.FONT_UI, corner_radius=theme.R["button"],
                fg_color=p["btn"], hover_color=p["btn_hover"], text_color=p["text"],
                command=lambda idx=i: self._choose(idx))
            btn.pack(fill="x", padx=18, pady=4)
            btn.configure(state="disabled")
            self.option_buttons.append(btn)

        self.feedback_lbl = ctk.CTkLabel(self.quiz_frame, text="", font=theme.FONT_SMALL,
                                         text_color=p["muted"], wraplength=520, justify="left")
        self.feedback_lbl.pack(anchor="w", padx=36, pady=(0, 4))

        self.cancel_btn = ctk.CTkButton(
            self.quiz_frame, text="Прервать тест", command=self._on_close,
            fg_color=p["btn"], hover_color=p["btn_hover"], text_color=p["text"],
            height=40, cursor="hand2", font=theme.FONT_UI,
            corner_radius=theme.R["button"], border_width=1, border_color=p["border"])
        self.cancel_btn.pack(fill="x", padx=36, pady=(0, 18))

    # -----------------------------------------------------
    # Сборка: экран ожидания модели (решение B)
    # -----------------------------------------------------
    def _build_wait(self):
        p = self.palette
        self.wait_frame = ctk.CTkFrame(self, fg_color="transparent")

        card = ctk.CTkFrame(self.wait_frame, fg_color=p["surface"],
                            corner_radius=theme.R["card"])
        card.pack(fill="both", expand=True, padx=18, pady=18)

        mid = ctk.CTkFrame(card, fg_color="transparent")
        mid.pack(fill="both", expand=True, padx=24, pady=(44, 0))

        self.wait_icon = ctk.CTkLabel(mid, text="⏳",
                                      font=(theme.FONT_PANEL_TITLE[0], 46, "bold"),
                                      text_color=p["warn"])
        self.wait_icon.pack(anchor="center")

        self.wait_title = ctk.CTkLabel(mid, text="Модель загружается…",
                                       font=(theme.FONT_PANEL_TITLE[0], 20, "bold"),
                                       text_color=p["text_strong"])
        self.wait_title.pack(anchor="center", pady=(12, 6))

        self.wait_hint = ctk.CTkLabel(
            mid, text="Загрузка локальной модели занимает ~30 секунд.",
            font=theme.FONT_SMALL, text_color=p["muted"], justify="center",
            wraplength=440)
        self.wait_hint.pack(anchor="center", pady=(0, 18))

        self.wait_bar = ctk.CTkProgressBar(card, height=8, corner_radius=4,
                                           fg_color=p["surface_alt"],
                                           progress_color=p["accent"])
        try:
            self.wait_bar.configure(mode="indeterminate")
        except Exception:
            pass
        self.wait_bar.pack(fill="x", padx=24, pady=(0, 10))

        self.wait_cancel_btn = ctk.CTkButton(
            card, text="Прервать тест", command=self._on_close,
            fg_color=p["btn"], hover_color=p["btn_hover"], text_color=p["text"],
            height=40, cursor="hand2", font=theme.FONT_UI,
            corner_radius=theme.R["button"], border_width=1, border_color=p["border"])
        self.wait_cancel_btn.pack(fill="x", padx=36, pady=(0, 22))

    # -----------------------------------------------------
    # Сборка: экран результата
    # -----------------------------------------------------
    def _build_result(self):
        p = self.palette
        self.result_frame = ctk.CTkFrame(self, fg_color="transparent")
        # пока не pack'аем — покажем после теста

        card = ctk.CTkFrame(self.result_frame, fg_color=p["surface"],
                            corner_radius=theme.R["card"])
        card.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(card, text="🎯 Твой уровень английского", font=theme.FONT_PANEL_TITLE,
                     text_color=p["muted"]).pack(anchor="w", padx=24, pady=(24, 0))
        self.level_lbl = ctk.CTkLabel(card, text="—", font=(theme.FONT_PANEL_TITLE[0], 52, "bold"),
                                      text_color=p["accent"])
        self.level_lbl.pack(anchor="w", padx=24, pady=(0, 4))
        self.summary_lbl = ctk.CTkLabel(card, text="", font=theme.FONT_UI,
                                        text_color=p["text"], justify="left", wraplength=480)
        self.summary_lbl.pack(anchor="w", padx=24, pady=(0, 10))
        self.breakdown_lbl = ctk.CTkLabel(card, text="", font=theme.FONT_SMALL,
                                          text_color=p["muted"], justify="left")
        self.breakdown_lbl.pack(anchor="w", padx=24, pady=(0, 16))

        self.again_btn = ctk.CTkButton(
            card, text="Пройти заново", command=self._restart,
            fg_color=p["btn"], hover_color=p["btn_hover"], text_color=p["text"],
            height=42, cursor="hand2", font=theme.FONT_UI, corner_radius=theme.R["button"])
        self.again_btn.pack(fill="x", padx=24, pady=(0, 8))

        self.done_btn = ctk.CTkButton(
            card, text="Готово", command=self._done,
            fg_color=p["accent"], hover_color=p["accent_hover"], text_color="#FFFFFF",
            height=44, cursor="hand2", font=theme.FONT_UI, corner_radius=theme.R["button"])
        self.done_btn.pack(fill="x", padx=24, pady=(0, 24))

    # -----------------------------------------------------
    # Ожидание готовности модели (решение B)
    # -----------------------------------------------------
    def _start_flow(self):
        """Решаем, что показать сразу: тест или экран ожидания модели."""
        if self._aborted:
            return
        if self.ready_probe is None:
            self._show_quiz()
            self._begin()
            return
        self._set_wait("loading")
        self._show_wait()
        self._poll_ready()

    def _poll_ready(self):
        if self._finished or self._aborted:
            return
        state = self._probe_state()
        if state == "ready":
            self._show_quiz()
            self._begin()
            return
        self._set_wait(state)
        self._wait_job = self.after(POLL_MS, self._poll_ready)

    def _probe_state(self):
        """Спрашивает пробу: "ready" | "loading" | "offline"."""
        probe = self.ready_probe
        if probe is None:
            return "ready"
        try:
            value = probe()
        except Exception as exc:
            print("⚠️ Тест уровня: проба готовности не сработала (%s)" % exc)
            return "offline"
        if isinstance(value, bool):
            return "ready" if value else "loading"
        return value or "offline"

    def _set_wait(self, state):
        if state == "ready" or not hasattr(self, "wait_icon"):
            return
        p = self.palette
        if state == "offline":
            self.wait_icon.configure(text="🔌", text_color=p["err"])
            self.wait_title.configure(text="Ожидаю LLM-сервер…")
            self.wait_hint.configure(
                text="Локальный сервер не отвечает.\n"
                     "Тест начнётся автоматически, как только модель будет готова.\n"
                     "Подробности: logs\\llama-server.log",
                text_color=p["muted"])
        else:
            self.wait_icon.configure(text="⏳", text_color=p["warn"])
            self.wait_title.configure(text="Модель загружается…")
            self.wait_hint.configure(
                text="Загрузка локальной модели занимает ~30 секунд.\n"
                     "Тест начнётся автоматически, как только она будет готова.",
                text_color=p["muted"])

    def _start_spinner(self):
        try:
            self.wait_bar.start()
        except Exception:
            pass

    def _stop_spinner(self):
        try:
            self.wait_bar.stop()
        except Exception:
            pass

    # -----------------------------------------------------
    # Ход теста
    # -----------------------------------------------------
    def _begin(self):
        self._set_loading("⏳ Готовлю первый вопрос…")
        self.controller.start(self.user_id,
                              on_question=self._show_question,
                              on_error=self._on_error)

    def _set_loading(self, text):
        self.question_lbl.configure(text=text)
        self.feedback_lbl.configure(text="")
        try:
            self.progress_bar.set(0)
        except Exception:
            pass
        for btn in self.option_buttons:
            btn.configure(state="disabled", text="",
                          fg_color=self.palette["btn"], text_color=self.palette["text"])

    def _show_question(self, question):
        self.question_lbl.configure(text=question["question"])
        total = question.get("total_max") or 1
        self.progress_lbl.configure(
            text="Вопрос %d (из ≤%d) · сложность %s" % (
                question["index"], total, question["difficulty_label"]))
        try:
            self.progress_bar.set(min(1.0, question["index"] / float(total)))
        except Exception:
            pass
        self._feedback_clear()
        p = self.palette
        for i, btn in enumerate(self.option_buttons):
            btn.configure(text=question["options"][i], state="normal",
                          fg_color=p["btn"], text_color=p["text"])

    def _choose(self, index):
        for btn in self.option_buttons:
            btn.configure(state="disabled")
        self.feedback_lbl.configure(text="Проверяю…", text_color=self.palette["muted"])
        if not self.controller.answer(
                self.user_id, index,
                on_feedback=self._show_feedback,
                on_question=self._show_question,
                on_result=self._show_result,
                on_error=self._on_error):
            # занято — вернём кнопки, чтобы можно было нажать снова
            for btn in self.option_buttons:
                btn.configure(state="normal")

    def _show_feedback(self, check):
        p = self.palette
        chosen = check.get("chosen_index")
        if chosen is not None and 0 <= chosen < len(self.option_buttons):
            btn = self.option_buttons[chosen]
            if check["correct"]:
                btn.configure(fg_color=p["ok"], text_color="#FFFFFF")
            else:
                btn.configure(fg_color=p["err"], text_color="#FFFFFF")
        if check["correct"]:
            self.feedback_lbl.configure(text="✅ Верно! Готовлю следующий вопрос…",
                                        text_color=p["ok"])
        else:
            # подсветим и правильный вариант — так нагляднее
            ci = check.get("correct_index")
            if ci is not None and 0 <= ci < len(self.option_buttons):
                self.option_buttons[ci].configure(fg_color=p["ok"], text_color="#FFFFFF")
            self.feedback_lbl.configure(
                text="❌ Правильный ответ: %s. Готовлю следующий вопрос…"
                     % check["correct_answer"],
                text_color=p["err"])

    def _feedback_clear(self):
        self.feedback_lbl.configure(text="", text_color=self.palette["muted"])

    def _show_result(self, result):
        if not result:
            self._on_error("Не удалось получить результат теста.")
            return
        self._finished = True
        self.result_level = result["level"]

        self.level_lbl.configure(text=result["level"])
        self.summary_lbl.configure(
            text="Верных ответов: %d из %d. Уровень сохранён в профиль."
                 % (result["correct"], result["total"]))
        self.breakdown_lbl.configure(text=self._breakdown_text(result.get("breakdown", {})))
        self._show(self.result_frame)

    @staticmethod
    def _breakdown_text(breakdown):
        if not breakdown:
            return ""
        parts = []
        for level in level_test.LEVELS:
            cell = breakdown.get(level)
            if cell:
                parts.append("%s: %d/%d" % (level, cell["correct"], cell["total"]))
        return "По уровням — " + "  ·  ".join(parts) if parts else ""

    def _restart(self):
        self.result_level = None
        self._finished = False
        self._aborted = False
        self._start_flow()

    def _on_error(self, message):
        self.question_lbl.configure(text="⚠️ Ошибка теста: %s" % message)
        self.feedback_lbl.configure(text="Закрой окно и попробуй позже.",
                                    text_color=self.palette["err"])
        for btn in self.option_buttons:
            btn.configure(state="disabled")

    # -----------------------------------------------------
    # Закрытие
    # -----------------------------------------------------
    def _on_close(self):
        if not self._finished:
            if not messagebox.askyesno(
                    "Прервать тест?",
                    "Закрыть без результата?\n\n"
                    "Текущий уровень в профиле не изменится.", parent=self):
                return
            self._aborted = True
            if self._wait_job is not None:
                try:
                    self.after_cancel(self._wait_job)
                except Exception:
                    pass
                self._wait_job = None
            self._stop_spinner()
            self.controller.cancel(self.user_id)
        self.result_level = None if not self._finished else self.result_level
        self._close()

    def _done(self):
        # уровень уже записан в профиль в момент get_result()
        self._aborted = True
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    # -----------------------------------------------------
    def _center(self, parent, w, h):
        try:
            parent.update_idletasks()
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 2)
        except Exception:
            x = y = 120
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, x), max(0, y)))

    def _grab(self):
        try:
            self.grab_set()
            self.lift()
        except Exception:
            pass

    # -----------------------------------------------------
    @classmethod
    def ask(cls, parent, palette, controller, user_id, ready_probe=None):
        """Открыть тест и дождаться результата. Возвращает уровень или None.

        ready_probe — необязательная проба готовности модели (callable,
        возвращает "ready"/"loading"/"offline" или bool). Если она задана,
        тест стартует только когда модель готова (решение B).
        """
        panel = cls(parent, palette, controller, user_id, ready_probe=ready_probe)
        parent.wait_window(panel)
        return panel.result_level
