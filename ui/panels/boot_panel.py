# -*- coding: utf-8 -*-
# =========================================================
# UI/PANELS/BOOT_PANEL.PY — модальный экран «Модель загружается…»
# =========================================================
# Показывается при старте, пока локальный LLM-сервер ещё грузит модель.
# Опрашивает пробу готовности (callable → "ready"/"loading"/"offline" или bool)
# и закрывается сам, как только модель готова. Кнопка «Продолжить без модели»
# есть на случай, если сервер не поднимется — чтобы не запереть пользователя.
#
# Логика пробы вынесена в чистую функцию resolve_state() — её удобно тестировать
# без Tk.
# =========================================================

from typing import Callable, Optional

import customtkinter as ctk

import theme

POLL_MS = 700


def resolve_state(probe: Optional[Callable], default: str = "loading") -> str:
    """Привести ответ пробы к 'ready' | 'loading' | 'offline'.

    probe может вернуть bool, строку состояния или None. Исключение пробы
    трактуем как 'offline' (сервер недоступен), а не как падение.
    """
    if probe is None:
        return default
    try:
        value = probe()
    except Exception:
        return "offline"
    if isinstance(value, bool):
        return "ready" if value else "loading"
    return value or default


class BootPanel(ctk.CTkToplevel):
    def __init__(self, parent, palette, ready_probe=None, on_progress=None):
        super().__init__(parent)
        self.palette = palette
        self.probe = ready_probe
        self.on_progress = on_progress
        self.result = False           # True — модель готова, False — пропустили
        self._job = None
        self._started = 0.0
        self._closed = False

        self.title("Загрузка модели")
        self.configure(fg_color=palette["window"])
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._skip)
        self._center(parent, 460, 320)

        p = palette
        card = ctk.CTkFrame(self, fg_color=p["surface"], corner_radius=theme.R["card"])
        card.pack(fill="both", expand=True, padx=18, pady=18)

        self.icon = ctk.CTkLabel(card, text="⏳",
                                 font=(theme.FONT_PANEL_TITLE[0], 46, "bold"),
                                 text_color=p["warn"])
        self.icon.pack(anchor="center", pady=(36, 6))

        self.title_lbl = ctk.CTkLabel(card, text="Модель загружается…",
                                      font=(theme.FONT_PANEL_TITLE[0], 20, "bold"),
                                      text_color=p["text_strong"])
        self.title_lbl.pack(anchor="center", pady=(0, 6))

        self.hint = ctk.CTkLabel(
            card, text="Загрузка локальной модели занимает ~30 секунд.\n"
                       "Чат станет доступен, когда модель будет готова.",
            font=theme.FONT_SMALL, text_color=p["muted"], justify="center", wraplength=400)
        self.hint.pack(anchor="center", pady=(0, 12))

        self.bar = ctk.CTkProgressBar(card, height=8, corner_radius=4,
                                      fg_color=p["surface_alt"], progress_color=p["accent"])
        try:
            self.bar.configure(mode="indeterminate")
        except Exception:
            pass
        self.bar.pack(fill="x", padx=28, pady=(0, 10))
        try:
            self.bar.start()
        except Exception:
            pass

        self.skip_btn = ctk.CTkButton(
            card, text="Продолжить без модели", command=self._skip,
            fg_color=p["btn"], hover_color=p["btn_hover"], text_color=p["text"],
            height=38, cursor="hand2", font=theme.FONT_UI,
            corner_radius=theme.R["button"], border_width=1, border_color=p["border"])
        self.skip_btn.pack(fill="x", padx=28, pady=(0, 22))

        self.after(80, self._grab)
        self.after(120, self._poll)

    # -----------------------------------------------------
    def _poll(self):
        if self._closed:
            return
        state = resolve_state(self.probe)
        if state == "ready":
            self._finish(True)
            return
        self._set_state(state)
        self._job = self.after(POLL_MS, self._poll)

    def _set_state(self, state):
        p = self.palette
        if state == "offline":
            self.icon.configure(text="🔌", text_color=p["err"])
            self.title_lbl.configure(text="Ожидаю LLM-сервер…")
            self.hint.configure(
                text="Локальный сервер не отвечает.\n"
                     "Проверь logs\\llama-server.log — или продолжи без модели.",
                text_color=p["muted"])
        else:
            self.icon.configure(text="⏳", text_color=p["warn"])
            self.title_lbl.configure(text="Модель загружается…")
        if self.on_progress is not None:
            try:
                self.on_progress(state, None, 0.0)
            except Exception:
                pass

    def _finish(self, ok):
        if self._closed:
            return
        self.result = bool(ok)
        self._close()

    def _skip(self):
        self._finish(False)

    def _close(self):
        self._closed = True
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        try:
            self.bar.stop()
        except Exception:
            pass
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
    def ask(cls, parent, palette, ready_probe=None, on_progress=None):
        """Показать экран и дождаться конца. True — модель готова."""
        panel = cls(parent, palette, ready_probe=ready_probe, on_progress=on_progress)
        parent.wait_window(panel)
        return panel.result
