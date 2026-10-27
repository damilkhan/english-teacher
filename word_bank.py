# -*- coding: utf-8 -*-
# =========================================================
# WORD_BANK.PY — банк слов по уровням и текущая ТЕМА ученика
# =========================================================
# Зачем: слова для изучения больше не приходят только из переводчика.
# У проекта есть готовые наборы слов по темам — data/words_<уровень>.json,
# где тема = блок карты (point_id: "city/point_1").
#
# Решение ученика 54 (27.10.2026):
#   • новые слова дают каждый день, порциями (config.VOCAB_NEW_PER_DAY);
#   • слова берутся из ТЕКУЩЕЙ темы (блок, который ещё не сдан);
#   • тема меняется не по календарю, а по усвоению: блок закрыт = его
#     «Проверка» (экзамен) записана как сданная (profile["exams"][id]["passed"]).
#
# Файл слов: {"version":1, "level":"A2", "themes": {"city/point_1": [ {...} ]}}
# Поля слова: ru, en, example. Тема — ключ словаря (в самом слове её не
# повторяем, чтобы не расходилась).
#
# Модуль чистый: ни Tk, ни микрофона. Карту курса читает progress_map.py,
# профиль приходит словарём; файлы слов кэшируются в памяти.
# =========================================================

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import config

LEVELS = ("A0", "A1", "A2", "B1", "B2", "C1")
DEFAULT_LEVEL = "A2"
_CACHE: Dict[str, dict] = {}


def data_dir(path=None) -> str:
    """Папка с банком слов (data/ в корне проекта)."""
    if path:
        return str(path)
    root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, "data")


def file_for_level(level, path=None) -> str:
    """Путь к файлу слов уровня: data/words_a2.json."""
    name = str(level or DEFAULT_LEVEL).strip().upper()
    if name not in LEVELS:
        name = DEFAULT_LEVEL
    return os.path.join(data_dir(path), "words_%s.json" % name.lower())


def parse_word(item, theme="") -> Optional[dict]:
    """Строка файла → слово карточки. Пустое/битое → None."""
    if not isinstance(item, dict):
        return None
    ru = str(item.get("ru") or "").strip()
    en = str(item.get("en") or "").strip()
    if not ru or not en:
        return None
    return {
        "ru": ru,
        "en": en,
        "example": str(item.get("example") or "").strip(),
        "theme": str(item.get("theme") or theme or "").strip(),
    }


def load(level, path=None) -> dict:
    """Прочитать файл слов уровня → {"level":…, "themes": {id: [слово, …]}}.

    Нет файла или он битый → пустой банк (пустые темы). Не падаем: без банка
    повторение работает как раньше, на карточках из профиля.
    """
    key = file_for_level(level, path)
    if key in _CACHE:
        return _CACHE[key]
    empty = {"level": str(level or DEFAULT_LEVEL), "themes": {}}
    try:
        with open(key, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        _CACHE[key] = empty
        return empty
    themes: Dict[str, List[dict]] = {}
    source = raw.get("themes") if isinstance(raw, dict) else None
    if isinstance(source, dict):
        for theme_id, items in source.items():
            words = []
            for item in (items or []):
                parsed = parse_word(item, theme_id)
                if parsed:
                    words.append(parsed)
            if words:
                themes[str(theme_id).strip()] = words
    out = {"level": str(raw.get("level") or level or DEFAULT_LEVEL) if isinstance(raw, dict) else DEFAULT_LEVEL,
           "themes": themes}
    _CACHE[key] = out
    return out


def forget(level=None, path=None):
    """Сбросить кэш (тесты и правка файла слов на ходу)."""
    if level is None:
        _CACHE.clear()
        return
    _CACHE.pop(file_for_level(level, path), None)


def themes(level, path=None) -> Dict[str, List[dict]]:
    return dict(load(level, path).get("themes") or {})


def words_of_theme(level, theme, path=None) -> List[dict]:
    """Слова темы (пустой список — темы нет в банке)."""
    theme = str(theme or "").strip()
    if not theme:
        return []
    return list((load(level, path).get("themes") or {}).get(theme) or [])


def has_level(level, path=None) -> bool:
    """Есть ли для уровня файл с непустым банком."""
    return bool((load(level, path).get("themes") or {}))


# ---------------------------------------------------------
# Тема: где ученик сейчас
# ---------------------------------------------------------
def student_level(profile) -> str:
    """Уровень ученика: из теста уровня, иначе config.VOCAB_LEVEL, иначе A2."""
    forced = str(getattr(config, "VOCAB_LEVEL", "") or "").strip().upper()
    if forced in LEVELS:
        return forced
    tests = (profile or {}).get("level_tests")
    if isinstance(tests, list):
        for item in reversed(tests):
            if isinstance(item, dict):
                name = str(item.get("level") or "").strip().upper()
                if name in LEVELS:
                    return name
    return DEFAULT_LEVEL


def check_lesson_id(wordmap, point_id) -> str:
    """id урока-проверки блока («city/1.4») или пусто, если её нет."""
    if wordmap is None:
        return ""
    try:
        lessons = wordmap.lessons_of(point_id)
    except Exception:
        return ""
    for lesson in lessons:
        if str((lesson or {}).get("type") or "").strip().lower() == "check":
            return str((lesson or {}).get("id") or "").strip()
    return ""


def theme_passed(profile, wordmap, point_id) -> bool:
    """Блок сдан? Признак — «Проверка» записана как сданная в профиле."""
    check_id = check_lesson_id(wordmap, point_id)
    if not check_id:
        return False
    exams = (profile or {}).get("exams")
    if not isinstance(exams, dict):
        return False
    entry = exams.get(check_id)
    return bool(isinstance(entry, dict) and entry.get("passed"))


def current_theme(profile, wordmap, level=None, path=None) -> str:
    """Текущая тема ученика: первый НЕсданный блок его уровня.

    Порядок: локации в порядке файла курса, начиная с уровня ученика
    (ниже — уже закрыто вступительным тестом), блоки внутри локации —
    по номеру. Всё сдано → "" (новых слов нет, только повторение).
    """
    if wordmap is None:
        return ""
    level = level or student_level(profile)
    rank = wordmap.level_rank(level)
    if rank < 0:
        rank = 0
    try:
        location_ids = list(wordmap.location_ids())
    except Exception:
        return ""
    for loc_id in location_ids:
        try:
            loc_level = (wordmap.get_location(loc_id) or {}).get("level")
        except Exception:
            continue
        if wordmap.level_rank(loc_level) < rank:
            continue                      # локация ниже уровня — уже закрыта
        try:
            points = wordmap.points_of(loc_id)
        except Exception:
            continue
        for point in points:
            point_id = str((point or {}).get("id") or "").strip()
            if not point_id:
                continue
            if not theme_passed(profile, wordmap, point_id):
                return point_id
    return ""


def theme_title(wordmap, point_id) -> str:
    """Название блока для интерфейса («Making Arrangements»)."""
    if wordmap is None:
        return ""
    try:
        return str((wordmap.get_point(point_id) or {}).get("block_title") or "").strip()
    except Exception:
        return ""


def theme_label(wordmap, point_id) -> str:
    """«1. Making Arrangements» — номер блока и название (пусто — нет данных)."""
    if wordmap is None or not point_id:
        return ""
    try:
        point = wordmap.get_point(point_id) or {}
    except Exception:
        return ""
    title = str(point.get("block_title") or "").strip()
    number = point.get("number")
    if not title:
        return ""
    if isinstance(number, int) and number > 0:
        return "%d. %s" % (number, title)
    return title


def progress(profile, wordmap, level=None, path=None) -> dict:
    """Сводка для интерфейса: {"level","theme","title","in_bank","words"}."""
    level = level or student_level(profile)
    theme = current_theme(profile, wordmap, level, path)
    words = words_of_theme(level, theme, path) if theme else []
    return {
        "level": level,
        "theme": theme,
        "title": theme_title(wordmap, theme),
        "in_bank": bool(words),
        "words": len(words),
    }
