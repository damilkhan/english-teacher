# -*- coding: utf-8 -*-
# =========================================================
# SERVER_WAITER.PY — терпеливое ожидание LLM-сервера
# =========================================================
# Раньше при недоступном сервере приложение СРАЗУ писало «LLM-сервер не
# отвечает». На практике сервер часто просто «задумывается» на пару секунд
# (перезапуск модели, загрузка), и ученик получал пугающую ошибку на ровном
# месте. Теперь так:
#
#   1) сначала ждём молча (сервер успевает очнуться сам);
#   2) если молчит дольше announce_after — показываем «ожидание»;
#   3) если не ответил и за wait_seconds — только тогда говорим, что сервер
#      не отвечает.
#
# Класс чистый: никакого Tk и потоков — приложение «тикает» его по таймеру
# и передаёт свежее состояние сервера (см. ui/app.py → _poll_server_task).
# Благодаря этому логику ожидания можно проверить тестами без окна.
# =========================================================

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# Сколько ждать сервер по умолчанию (меняется через config).
DEFAULT_WAIT_SECONDS = 15.0
DEFAULT_POLL_MS = 800
DEFAULT_ANNOUNCE_AFTER = 1.5

# Статусы, которые возвращает step().
READY = "ready"           # сервер ответил — можно действовать
ANNOUNCE = "announce"     # сервер молчит — покажи «ожидание»
PENDING = "pending"       # ждём дальше, ничего показывать не надо
TIMEOUT = "timeout"       # сервер молчит слишком долго — «не отвечает»


class ServerWaiter:
    """Ждёт готовности сервера: «ожидание» → (если долго) «не отвечает»."""

    # Те же статусы, но как атрибуты класса: удобно писать ServerWaiter.READY
    READY = READY
    ANNOUNCE = ANNOUNCE
    PENDING = PENDING
    TIMEOUT = TIMEOUT

    def __init__(self, wait_seconds=None, poll_ms=None, announce_after=None):
        try:
            self.wait_seconds = float(
                DEFAULT_WAIT_SECONDS if wait_seconds is None else wait_seconds)
        except (TypeError, ValueError):
            self.wait_seconds = DEFAULT_WAIT_SECONDS
        try:
            self.poll_ms = max(50, int(DEFAULT_POLL_MS if poll_ms is None else poll_ms))
        except (TypeError, ValueError):
            self.poll_ms = DEFAULT_POLL_MS
        try:
            self.announce_after = float(
                DEFAULT_ANNOUNCE_AFTER if announce_after is None else announce_after)
        except (TypeError, ValueError):
            self.announce_after = DEFAULT_ANNOUNCE_AFTER

        self.reset()

    # -----------------------------------------------------
    def reset(self) -> None:
        """Начать ожидание заново."""
        self.elapsed = 0.0
        self.announced = False
        self.finished = False

    @property
    def step_seconds(self) -> float:
        """Сколько секунд прибавляет один шаг опроса."""
        return self.poll_ms / 1000.0

    # -----------------------------------------------------
    def step(self, ready: bool) -> str:
        """Принять свежее состояние сервера и решить, что делать дальше.

        ready=True  → READY (сервер очнулся);
        иначе       → ANNOUNCE (пора показать «ожидание»), PENDING (ждём
                      молча) или TIMEOUT (сервер молчит слишком долго).
        После READY/TIMEOUT ожидание считается завершённым (finished=True)
        и дальнейшие шаги возвращают тот же итог.
        """
        if ready:
            self.finished = True
            return READY
        if self.finished:
            # ожидание уже закончилось неудачей — не начинаем заново
            return TIMEOUT

        self.elapsed += self.step_seconds
        if self.elapsed >= self.wait_seconds:
            self.finished = True
            _log.info("Ожидание сервера исчерпано (%.1f с)", self.elapsed)
            return TIMEOUT
        if not self.announced and self.elapsed >= self.announce_after:
            self.announced = True
            return ANNOUNCE
        return PENDING

    # -----------------------------------------------------
    def is_timeout(self) -> bool:
        return self.finished and self.elapsed >= self.wait_seconds
