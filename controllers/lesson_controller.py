# -*- coding: utf-8 -*-
# =========================================================
# LESSON_CONTROLLER.PY — оркестрация ЗАНЯТИЯ по карте
# =========================================================
# Держит текущую сессию урока (lesson.LessonSession) и сообщает наружу о
# её изменениях через колбэки. Логика правил — в lesson.py, интерфейс —
# в ui/app.py; здесь только «склейка» + гарантия главного потока.
#
# Колбэки (все вызываются в главном потоке через dispatch):
#   on_started(session)      — занятие началось;
#   on_reply(state)          — учтена реплика ученика;
#   on_finished(session)     — занятие завершено (дошёл до лимита ИЛИ
#                              сданы все задания, см. credit_finished);
#   on_aborted(session)      — ученик вышел раньше (НЕ засчитывается).
# =========================================================

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

import lesson as lesson_mod

_log = logging.getLogger(__name__)


class LessonController:
    """Текущее занятие: старт, учёт реплик, завершение и выход."""

    def __init__(self, dispatch: Optional[Callable[[Callable], Any]] = None,
                 on_started: Optional[Callable] = None,
                 on_reply: Optional[Callable] = None,
                 on_finished: Optional[Callable] = None,
                 on_aborted: Optional[Callable] = None) -> None:
        self._dispatch = dispatch or (lambda fn: fn())
        self.on_started = on_started
        self.on_reply = on_reply
        self.on_finished = on_finished
        self.on_aborted = on_aborted
        self.session: Optional[lesson_mod.LessonSession] = None

    # -----------------------------------------------------
    # Состояние
    # -----------------------------------------------------
    @property
    def is_active(self) -> bool:
        """Идёт ли занятие сейчас."""
        return bool(self.session and self.session.is_active)

    @property
    def lesson_id(self) -> Optional[str]:
        return self.session.lesson_id if self.session else None

    def current(self) -> Optional[lesson_mod.LessonSession]:
        return self.session

    # -----------------------------------------------------
    # Старт / завершение
    # -----------------------------------------------------
    def start(self, lesson_id: str, point_id: Optional[str] = None,
              lesson_type: Any = lesson_mod.SPEAKING, title: str = "",
              topic: str = "", block_number: Optional[int] = None,
              block_title: str = "", reply_target: Optional[int] = None,
              code: str = ""):
        """Начать занятие. Возвращает сессию (или None, если уже идёт)."""
        if self.is_active:
            _log.info("Урок уже идёт (%s) — новый не начинаю", self.lesson_id)
            return None
        self.session = lesson_mod.LessonSession(
            lesson_id, point_id=point_id, lesson_type=lesson_type, title=title,
            topic=topic, block_number=block_number, block_title=block_title,
            reply_target=reply_target, code=code)
        session = self.session
        self._emit(self.on_started, session)
        return session

    def register_reply(self) -> Optional[Dict[str, Any]]:
        """Учесть реплику ученика. Автозавершает занятие по лимиту."""
        if not self.is_active:
            return None
        state = self.session.register_reply()
        self._emit(self.on_reply, state)
        if self.session.finished:
            self._emit(self.on_finished, self.session)
        return state

    def finish(self) -> Optional[lesson_mod.LessonSession]:
        """Завершить занятие вручную (например, «Продолжить»/итог)."""
        if not self.is_active:
            return None
        self.session.finish()
        self._emit(self.on_finished, self.session)
        return self.session

    def credit_finished(self) -> Optional[lesson_mod.LessonSession]:
        """Сообщить, что занятие закрылось ЗАЧЁТОМ задания (§36).

        От finish() отличается тем, что сессия уже помечена завершённой:
        lesson.LessonSession.credit_task делает это сам. Но колбэк
        on_finished всё равно нужен — иначе не покажется итог урока.
        Повторный вызов после закрытия сессии ничего не показывает:
        приложение само решает, показывать итог или отложить (§32).
        """
        if self.session is None or not self.session.finished:
            return None
        self._emit(self.on_finished, self.session)
        return self.session

    def abort(self) -> Optional[lesson_mod.LessonSession]:
        """Прервать занятие (ученик нажал «Выйти»). НЕ засчитывается."""
        if self.session is None:
            return None
        was_active = self.session.is_active
        self.session.abort()
        if was_active:
            self._emit(self.on_aborted, self.session)
        return self.session

    def reset(self) -> None:
        """Забыть занятие без колбэков (например, при смене ученика)."""
        self.session = None

    # -----------------------------------------------------
    def _emit(self, callback, *args) -> None:
        """Вызвать колбэк в главном потоке (ошибки не пробрасываем)."""
        if callback is None:
            return

        def _safe():
            try:
                callback(*args)
            except Exception as exc:
                _log.warning("Урок: ошибка в колбэке (%s)", exc)

        try:
            self._dispatch(_safe)
        except Exception as exc:
            _log.warning("Урок: dispatch не сработал (%s)", exc)
