# -*- coding: utf-8 -*-
# =========================================================
# VOCAB_LINES.PY — что Вербот ГОВОРИТ в окне слов
# =========================================================
# Просьба ученика 27.10.2026: в окне карточек Вербот должен:
#   • перед окном ОТВЕТИТЬ на просьбу («Okay! Here are your words.»)
#     и проговорить фразу до конца — только потом открываются карточки;
#   • на каждый верный ответ хвалить РАЗНЫМИ фразами;
#   • на промах РЕДКО подбадривать — тоже разными фразами.
#
# Всё ТОЛЬКО по-английски, без русских приписок: это урок английского.
#
# Наборы:
#   OPEN_LINES     — одна фраза перед окном карточек;
#   PRAISE_LINES   — похвала на верный ответ;
#   MOTIVATE_LINES — подбадривание на промах (не каждый раз).
#
# Правила (просьба ученика):
#   • одна и та же похвала звучит не больше MAX_REPEAT раз за заход;
#   • подбадривание выпадает случайно (MOTIVATE_CHANCE) и не два раза подряд.
#
# Модуль чистый: ни Tk, ни сети, ни звука — только выбор фразы.
# =========================================================

from __future__ import annotations

import random

# --- перед окном карточек ---
OPEN_LINES = (
    "Okay! Here are your words.",
    "Sure! Let's look at your words.",
    "All right, your words are ready.",
    "Great! It's word time.",
    "Let's do some words now.",
    "Here we go — your words.",
    "Good! Let's practise your words.",
    "Ready? Here are your words.",
    "Nice! Let's repeat some words.",
    "Okay, let's work on your words.",
)

# --- похвала на верный ответ ---
PRAISE_LINES = (
    "Good!",
    "Nice!",
    "Well done!",
    "Perfect!",
    "Exactly!",
    "That's right!",
    "Great job!",
    "You got it!",
    "Excellent!",
    "Brilliant!",
    "Spot on!",
    "Yes! That's it!",
    "Very good!",
    "Awesome!",
)

# --- подбадривание на промах (редко) ---
MOTIVATE_LINES = (
    "Almost! Try again.",
    "So close! One more time.",
    "Not quite. You can do it.",
    "Nearly there. Try again.",
    "Keep going, you're close.",
    "Don't worry. Try once more.",
    "Almost there. Listen and repeat.",
)

# Одна и та же фраза — не больше стольких раз за заход.
MAX_REPEAT = 2
# Как часто подбадривать на промах (0.35 = примерно каждый третий промах).
MOTIVATE_CHANCE = 0.35


def pick_open(last="", rng=None):
    """Фраза перед окном слов: любая, но НЕ та же, что в прошлый раз."""
    previous = str(last or "")
    pool = [line for line in OPEN_LINES if line != previous]
    if not pool:
        pool = list(OPEN_LINES)
    picker = rng or random
    return picker.choice(pool)


class LinePicker:
    """Выбор фраз за ОДИН заход: без повторов чаще MAX_REPEAT раз.

    Заход = открытое окно слов. Новое окно — новый LinePicker, счётчики
    начинаются с нуля.
    """

    def __init__(self, rng=None, max_repeat=MAX_REPEAT, chance=MOTIVATE_CHANCE):
        self._rng = rng if rng is not None else random.Random()
        try:
            self._max = max(1, int(max_repeat))
        except (TypeError, ValueError):
            self._max = MAX_REPEAT
        try:
            value = float(chance)
        except (TypeError, ValueError):
            value = MOTIVATE_CHANCE
        self._chance = max(0.0, min(1.0, value))
        self._used = {}
        self._last = ""
        self.spoken = []          # что уже звучало (для тестов и разбора)

    # -----------------------------------------------------
    def used(self, line) -> int:
        """Сколько раз фраза уже звучала в этом заходе."""
        return self._used.get(str(line), 0)

    def pick(self, lines):
        """Фраза из набора с учётом лимита повторов."""
        items = [str(line) for line in (lines or ()) if str(line).strip()]
        if not items:
            return ""
        # не та же, что только что (иначе два раза подряд одно и то же)
        pool = [line for line in items
                if self.used(line) < self._max and line != self._last]
        if not pool:
            # все фразы израсходовали лимит — говорим дальше, но не ту же подряд
            pool = [line for line in items if line != self._last] or items
        line = self._rng.choice(pool)
        self._used[line] = self.used(line) + 1
        self._last = line
        self.spoken.append(line)
        return line

    def praise(self) -> str:
        """Похвала на верный ответ (разная, не больше двух раз за заход)."""
        return self.pick(PRAISE_LINES)

    def maybe_motivate(self) -> str:
        """Подбадривание на промах: РЕДКО и не два раза подряд. Пусто — молчим."""
        if self._rng.random() >= self._chance:
            return ""
        pool = [line for line in MOTIVATE_LINES if line != self._last]
        if not pool:
            return ""
        return self.pick(pool)
