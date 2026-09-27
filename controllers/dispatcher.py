# -*- coding: utf-8 -*-
# =========================================================
# DISPATCHER.PY — потокобезопасная передача вызовов в главный поток Tk
# =========================================================
# Проблема: Tk нельзя трогать из чужих потоков. Обычный приём —
# window.after(0, fn) из воркера, но он работает ТОЛЬКО если mainloop
# уже запущен. До этого (и в автотестах, которые гоняют update())
# tkinter падает с "main thread is not in main loop".
#
# Решение: воркеры кладут функции в очередь, а главный поток разбирает
# её по таймеру. Не зависит от mainloop, не теряет вызовы, тестируется
# без окна.
# =========================================================

import queue

DRAIN_INTERVAL_MS = 30


class Dispatcher:
    def __init__(self, schedule, cancel, interval_ms=DRAIN_INTERVAL_MS):
        self._queue = queue.Queue()
        self._schedule = schedule      # window.after
        self._cancel = cancel          # window.after_cancel
        self.interval_ms = interval_ms
        self._after_id = None
        self._stopped = True

    # --- вызывается из ЛЮБОГО потока ---
    def dispatch(self, fn):
        self._queue.put(fn)

    # --- главный поток ---
    def start(self):
        if not self._stopped:
            return
        self._stopped = False
        self._drain()

    def stop(self):
        self._stopped = True
        if self._after_id is not None:
            try:
                self._cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def drain_once(self):
        """Выполнить всё, что накопилось. Нужно тестам (и не только)."""
        while True:
            try:
                fn = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as exc:
                print(f"⚠️ Ошибка в отложенном вызове: {exc}")

    def _drain(self):
        self.drain_once()
        if not self._stopped:
            self._after_id = self._schedule(self.interval_ms, self._drain)
