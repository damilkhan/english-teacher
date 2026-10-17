# -*- coding: utf-8 -*-
# =========================================================
# REACTIONS.PY — «педагогические» реакции робота на ответы ученика
# =========================================================
# Задача: замечать моменты, когда ученик ДОЛГО не мог ответить, а потом
# справился. Это самый ценный момент для похвалы: «ты смог!».
#
# Правило (как договорились):
#   3 неправильных ответа подряд → верный ответ →
#   робот сначала УДИВЛЯЕТСЯ (1.5 с), потом ОДОБРИТЕЛЬНО УЛЫБАЕТСЯ.
#
# Модуль чистый: ни Tk, ни потоков. Возвращает имя реакции или None.
# =========================================================

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

_log = logging.getLogger(__name__)

# Имена реакций (совпадают со «сценариями» лица).
PRAISE_AFTER_STRUGGLE = "praise_after_struggle"   # удивление → улыбка

# Значения по умолчанию (можно менять из приложения/настроек).
DEFAULT_MISSES = 3
DEFAULT_SURPRISE_SECONDS = 1.5
DEFAULT_SMILE_SECONDS = 2.4


@dataclass
class Reaction:
    """Готовая реакция: какие состояния лица показать и сколько держать."""
    name: str
    steps: Tuple[Tuple[str, float], ...]

    def __bool__(self) -> bool:
        return bool(self.steps)


def surprise_then_smile(surprise: float = DEFAULT_SURPRISE_SECONDS,
                        smile: float = DEFAULT_SMILE_SECONDS) -> Reaction:
    """Сценарий «удивилась → одобрительно улыбнулась»."""
    # Имена состояний — из character_face (строки, чтобы не тянуть импорт Tk).
    return Reaction(PRAISE_AFTER_STRUGGLE,
                    (("surprised", float(surprise)),
                     ("smile", float(smile))))


class ReactionTracker:
    """Считает серию неудач и решает, когда пора удивиться и похвалить.

    Использование:
        tracker = ReactionTracker()
        reaction = tracker.record(ok=False)   # неудача
        reaction = tracker.record(ok=True)    # удача → возможно Reaction
    """

    def __init__(self, misses_before: int = DEFAULT_MISSES) -> None:
        try:
            self.misses_before = max(1, int(misses_before))
        except (TypeError, ValueError):
            self.misses_before = DEFAULT_MISSES
        self.streak = 0            # сколько неудач подряд
        self.total_misses = 0
        self.total_correct = 0
        self.celebrated = 0        # сколько раз уже похвалили за старание

    # -----------------------------------------------------
    def record(self, ok: Optional[bool]) -> Optional[Reaction]:
        """Учесть ответ ученика. Возвращает Reaction, если пора реагировать.

        ok=None — «непонятно» (пустой/нераспознанный ответ): серию НЕ рвём
        и НЕ увеличиваем — иначе случайный шум сбивал бы счёт.
        """
        if ok is None:
            return None
        if not ok:
            self.streak += 1
            self.total_misses += 1
            return None
        # правильный ответ
        self.total_correct += 1
        struggled = self.streak >= self.misses_before
        self.streak = 0
        if struggled:
            self.celebrated += 1
            _log.info("Реакция: справился после %d неудач подряд", self.misses_before)
            return surprise_then_smile()
        return None

    # -----------------------------------------------------
    def reset(self) -> None:
        """Новый ученик / новый урок — начинаем счёт заново."""
        self.streak = 0
        self.total_misses = 0
        self.total_correct = 0
        self.celebrated = 0

    @property
    def struggling(self) -> bool:
        """Ученик сейчас в полосе неудач (3 и больше подряд)."""
        return self.streak >= self.misses_before


def answer_is_correct(analysis: Optional[dict]) -> Optional[bool]:
    """Понять по разбору Аналитика, верный ли был ответ.

    Возвращает True/False, либо None, если судить не по чему:
      * move_status "P" (доработать) или есть ошибки → False;
      * move_status "A" (принято) без ошибок → True;
      * разбора нет → None.
    """
    if not isinstance(analysis, dict) or not analysis.get("ok"):
        return None
    errors = analysis.get("errors") or []
    status = str(analysis.get("move_status") or "").upper()
    if errors:
        return False
    if status == "P":
        return False
    if status == "A":
        return True
    return None
