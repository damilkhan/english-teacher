# -*- coding: utf-8 -*-
# =========================================================
# SERVER_MONITOR.PY — слежение за состоянием LLM-сервера
# =========================================================
# Раньше gui.py проверял /health ОДИН РАЗ при старте, из-за чего бейдж
# залипал на «Сервер не запущен», пока модель грузилась ~30 секунд.
# Теперь опрос идёт по таймеру, а состояния три: ready / loading / offline.
#
# Планировщик (window.after) передаётся снаружи — поэтому класс
# тестируется без Tk.
# =========================================================

import server_manager

INTERVAL_MS = 3000


class ServerMonitor:
    def __init__(self, on_state, schedule, cancel, interval_ms=INTERVAL_MS, state_fn=None):
        self.on_state = on_state            # (state, message)
        self._schedule = schedule           # window.after
        self._cancel = cancel               # window.after_cancel
        self.interval_ms = interval_ms
        self.state_fn = state_fn or server_manager.health_state
        self._after_id = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        self._tick()

    def stop(self):
        self.running = False
        if self._after_id is not None:
            try:
                self._cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def check_now(self):
        """Разовый опрос. Возвращает имя состояния."""
        try:
            state, message = self.state_fn(timeout=1.5)
        except Exception as exc:
            state, message = "offline", f"ошибка опроса: {exc}"
        if self.on_state is not None:
            try:
                self.on_state(state, message)
            except Exception as exc:
                print(f"⚠️ Ошибка обработчика состояния сервера: {exc}")
        return state

    def _tick(self):
        if not self.running:
            return
        self.check_now()
        self._after_id = self._schedule(self.interval_ms, self._tick)
