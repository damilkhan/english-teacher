# -*- coding: utf-8 -*-
# =========================================================
# SCENES.PY — библиотека СЦЕН-диалогов (шаг 3, 02.11.2026)
# =========================================================
# Сцена = жизненная ситуация (ресторан, аптека, аэропорт…), в которой ученик
# РАЗГОВАРИВАЕТ. Это НЕ урок «про слова» и не дрилл: реплики участника
# (официанта, врача, кассира) готовы и лежат здесь, а не сочиняются моделью.
#
# Почему так (решение ученика 02.11.2026, вариант А):
#   §35 показал: промптом выдумки НЕ убрать — маленькая модель всё равно
#   приносит «кино у стоматолога». Готовый вопрос убирает выдумку совсем:
#   модель в сцене не зовётся, длинных секунд ожидания тоже нет.
#
# Правила файла (решение 73): библиотека НА УРОВЕНЬ, схема одна, id с уровнем
# (a2.restaurant). Движок про уровень не знает — он просто читает файл.
#
# Схема (data/scenes_a2.json):
#   scenes[]:
#     id        — a2.restaurant (уровень в id);
#     title     — английское название, title_ru — по-русски;
#     lesson    — id урока карты, к которому сцена привязана (city/2.1);
#     card      — КАРТОЧКА РОЛИ: кто есть кто и что делает (ru и en);
#     steps[]   — шаги сцены: n, title, questions[] = {en, hint};
#                 hint — короткая подсказка ПО-РУССКИ (ситуация со смыслом,
#                 не перевод: «у окна?», «картой или наличными?»).
#
# Здесь ТОЛЬКО чтение: ни Tk, ни модели, ни записи в базу.
# =========================================================

from __future__ import annotations

import json
import logging
import os

_log = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
# Кэш по уровню: файл читается один раз за запуск.
_CACHE = {}


def path(level="A2") -> str:
    """Путь к файлу библиотеки уровня (a2 → data/scenes_a2.json)."""
    return os.path.join(_HERE, "data", "scenes_%s.json"
                        % str(level or "A2").strip().lower())


def _load(level="A2") -> dict:
    key = str(level or "A2").strip().upper()
    if key in _CACHE:
        return _CACHE[key]
    data = {"version": 0, "scenes": []}
    try:
        with open(path(key), "r", encoding="utf-8") as fh:
            loaded = json.load(fh) or {}
        if isinstance(loaded, dict):
            data = loaded
    except Exception as exc:                        # pragma: no cover
        _log.warning("Библиотека сцен не прочитана (%s): %s", path(key), exc)
        data = {"version": 0, "scenes": []}
    rows = data.get("scenes")
    data["scenes"] = [row for row in (rows or [])
                      if isinstance(row, dict) and row.get("id")]
    _CACHE[key] = data
    return data


def library(level="A2") -> list:
    """Все сцены уровня (список словарей)."""
    return list(_load(level)["scenes"])


def scene_ids(level="A2") -> list:
    """Id всех сцен уровня."""
    return [str(row.get("id")) for row in library(level)]


def scene(scene_id, level="A2") -> dict:
    """Сцена по id (пусто — такой нет)."""
    want = str(scene_id or "").strip()
    if not want:
        return {}
    for row in library(level):
        if str(row.get("id")) == want:
            return row
    return {}


def for_lesson(lesson_id, level="A2") -> str:
    """Id сцены, привязанной к уроку карты; "" — урок обычный.

    Так сцена включается с КАРТЫ: отдельной кнопки нет (решение ученика).
    """
    want = str(lesson_id or "").strip()
    if not want:
        return ""
    for row in library(level):
        if str(row.get("lesson") or "").strip() == want:
            return str(row.get("id"))
    return ""


def steps(scene_id, level="A2") -> list:
    """Шаги сцены по порядку (пусто — сцены нет)."""
    item = scene(scene_id, level)
    return [step for step in (item.get("steps") or []) if isinstance(step, dict)]


def step_count(scene_id, level="A2") -> int:
    """Сколько шагов в сцене."""
    return len(steps(scene_id, level))


def _questions(step: dict) -> list:
    rows = step.get("questions") if isinstance(step, dict) else None
    return [row for row in (rows or [])
            if isinstance(row, dict) and str(row.get("en") or "").strip()]


def counts(scene_id, level="A2") -> list:
    """Сколько вопросов в каждом шаге: [3, 2, 3, 3, 1, 3].

    Нужно сессии: по этому списку она понимает, где кончается шаг.
    """
    return [len(_questions(step)) for step in steps(scene_id, level)]


def total_questions(scene_id, level="A2") -> int:
    """Сколько всего вопросов в сцене."""
    return sum(counts(scene_id, level))


def question(scene_id, step, index=0, level="A2") -> dict:
    """Вопрос по позиции: шаг 1..N, index 0.. (пусто — такого нет).

    Возвращает en, hint, номер вопроса ВО ВСЕЙ сцене (number) и всего (total),
    номер шага и сколько шагов: этого хватает и для чата, и для лога.
    """
    try:
        step_no = int(step)
        index = int(index)
    except (TypeError, ValueError):
        return {}
    rows = steps(scene_id, level)
    if not 1 <= step_no <= len(rows) or index < 0:
        return {}
    questions = _questions(rows[step_no - 1])
    if index >= len(questions):
        return {}
    item = questions[index]
    before = sum(len(_questions(row)) for row in rows[:step_no - 1])
    return {
        "en": str(item.get("en") or "").strip(),
        "hint": str(item.get("hint") or "").strip(),
        "slot": str(item.get("slot") or "").strip(),
        "step": step_no,
        "of_steps": len(rows),
        "index": index,
        "of_step": len(questions),
        "number": before + index + 1,
        "total": total_questions(scene_id, level),
    }


def card(scene_id, level="A2") -> dict:
    """Карточка роли: кто есть кто и что делает (ru и en)."""
    item = scene(scene_id, level)
    value = item.get("card")
    return value if isinstance(value, dict) else {}


def title(scene_id, level="A2") -> str:
    """Название сцены по-русски (для строки в чате)."""
    item = scene(scene_id, level)
    return str(item.get("title_ru") or item.get("title") or "").strip()


def describe(scene_id, level="A2") -> str:
    """Одна строка для лога: «В ресторане: шагов 6, вопросов 15»."""
    if not scene(scene_id, level):
        return ""
    return "%s: шагов %d, вопросов %d" % (title(scene_id, level) or scene_id,
                                          step_count(scene_id, level),
                                          total_questions(scene_id, level))
