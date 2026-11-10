# -*- coding: utf-8 -*-
"""Библиотека смысловых пар для движка подстановки (§55, шаг 2).

Что здесь есть:
  * library(level)        — весь словарь правил файла data/phrase_pairs_a2.json;
  * pick(rule_id, window) — 3 фразы подряд (обе стороны пары рядом, решение 68);
  * rule_for_words(...)   — какое правило библиотеки сработало в паре
                            «сказал -> как надо» (связь базы ошибок с парой).

Движок про УРОВЕНЬ не знает (решение 73): уровень — это только имя файла.
Файл библиотеки личный по смыслу, но лежит в git: тексты пишет человек,
модель фраз не сочиняет (решение 67).
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Сколько фраз правила показываем в одном дрилле (решение 77: 6 в файле,
# 3 в работе, 3 в запасе на следующий раз).
DRILL_PER_RULE = 3

_CACHE = {}      # type: Dict[str, Dict[str, Any]]


def path_for(level: str = "a2") -> str:
    """Путь к файлу библиотеки уровня (одна схема на все уровни)."""
    name = str(level or "a2").strip().lower()
    return os.path.join(DATA_DIR, "phrase_pairs_%s.json" % name)


def library(level: str = "a2", refresh: bool = False) -> Dict[str, Any]:
    """Правила уровня: {rule_id: {"pair", "words", "phrases"}}.

    Файла нет или он битый — пустой словарь и строка в лог: дрилл просто
    не запустится, урок пойдёт как раньше.
    """
    name = str(level or "a2").strip().lower()
    if not refresh and name in _CACHE:
        return _CACHE[name]
    data = {}                                       # type: Dict[str, Any]
    path = path_for(name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        rules = raw.get("rules") if isinstance(raw, dict) else None
        if isinstance(rules, dict):
            data = {str(k): v for k, v in rules.items() if isinstance(v, dict)}
    except (OSError, ValueError) as exc:
        print("⚠️ Библиотека фраз %s не прочитана: %s" % (name, exc))
    _CACHE[name] = data
    return data


def rule_ids(level: str = "a2") -> List[str]:
    """Все правила уровня по порядку файла."""
    return list(library(level).keys())


def rule(rule_id: Any, level: str = "a2") -> Optional[Dict[str, Any]]:
    """Одно правило библиотеки или None."""
    return library(level).get(str(rule_id or "").strip())


def all_phrases(rule_id: Any, level: str = "a2") -> List[Dict[str, str]]:
    """Все 6 фраз правила (пустой список, если правила нет)."""
    item = rule(rule_id, level)
    out = []                                        # type: List[Dict[str, str]]
    for phrase in (item or {}).get("phrases") or []:
        if isinstance(phrase, dict) and phrase.get("ru") and phrase.get("en"):
            out.append({"ru": str(phrase.get("ru")).strip(),
                        "en": str(phrase.get("en")).strip(),
                        "why": str(phrase.get("why") or "").strip(),
                        "hint2": str(phrase.get("hint2") or "").strip()})
    return out


def pick(rule_id: Any, window: int = 0, count: int = DRILL_PER_RULE,
         level: str = "a2") -> List[Dict[str, str]]:
    """Тройка фраз правила: window=0 — первая, window=1 — вторая (запас).

    Фразы из файла идут ПАРАМИ (одна сторона пары, потом другая), поэтому
    три подряд — это контраст, а не три случайных примера (решение 68).
    Окно вне файла заворачивается по кругу: фразы не теряются.
    """
    items = all_phrases(rule_id, level)
    if not items:
        return []
    size = max(1, min(int(count or DRILL_PER_RULE), len(items)))
    try:
        start = int(window or 0) * size
    except (TypeError, ValueError):
        start = 0
    start %= len(items)
    out = items[start:start + size]
    if len(out) < size:                      # хвост файла — берём с начала
        out = out + items[:size - len(out)]
    return out


def _has(text: Any, word: str) -> bool:
    """Есть ли слово в тексте целым словом (без «lie» внутри «believe»)."""
    low = re.sub(r"[^a-z']+", " ", str(text or "").lower())
    if not low.strip() or not word:
        return False
    pattern = r"(?<![a-z])" + re.escape(str(word).lower()) + r"(?![a-z])"
    return re.search(pattern, low) is not None


def has_word(text: Any, word: Any) -> bool:
    """Публичная проверка «слово есть в тексте целым словом» (для lesson.py)."""
    return _has(text, word)


def rule_for_words(wrong: Any, correct: Any, level: str = "a2") -> Optional[str]:
    """Какое правило библиотеки стоит за парой «было -> стало».

    Ищем правило, у которого одно ключевое слово пары есть в ПРАВИЛЬНОМ
    тексте, а другое — в НЕПРАВИЛЬНОМ: `go to lay down -> go to lie down`
    даёт `a2.lay_lie`. Если подходят два правила сразу — отдаём None:
    лучше не отметить правило, чем отметить чужое (ученик: точность).
    """
    library(level)                                  # прогреть кэш один раз
    found = ""                                      # type: str
    for rule_id, item in library(level).items():
        words = [str(w).strip().lower() for w in (item.get("words") or []) if w]
        if len(words) < 2:
            continue
        first, second = words[0], words[1]
        hit = ((_has(correct, first) and _has(wrong, second))
               or (_has(correct, second) and _has(wrong, first)))
        if not hit:
            continue
        if found and found != rule_id:
            return None                # две пары подходят — не гадаем
        found = rule_id
    return found or None


def describe(rule_id: Any, level: str = "a2") -> str:
    """Строка «о чём пара» для лога: берётся из поля pair."""
    item = rule(rule_id, level)
    return str((item or {}).get("pair") or "").strip()

# ---------------------------------------------------------------
# §65 (10.11.2026): равнозначные варианты фразы (решение ученика 109)
# ---------------------------------------------------------------
# Зачем: смысл один, а сказать можно по-разному. После верного ответа
# показываем 1-2 равнозначных варианта — так растёт словарный запас.
# Тексты пишет ЧЕЛОВЕК (решение 67), модель их не сочиняет: файл
# data/paraphrases_a2.json плюс поле "alts" у фраз библиотеки пар.
_ALTS_CACHE = {}      # type: Dict[str, Dict[str, List[str]]]


def _flat_key(text: Any) -> str:
    """Фраза в одной форме: без регистра, знаков и лишних пробелов."""
    value = str(text or "").lower()
    keep = [ch if (ch.isalnum() or ch == "'") else " " for ch in value]
    return " ".join("".join(keep).split())


def _alts_file(level: str = "a2") -> Dict[str, List[str]]:
    """{фраза-в-одной-форме: [варианты]} из data/paraphrases_<уровень>.json."""
    name = str(level or "a2").strip().lower()
    if name in _ALTS_CACHE:
        return _ALTS_CACHE[name]
    data = {}                                   # type: Dict[str, List[str]]
    path = os.path.join(DATA_DIR, "paraphrases_%s.json" % name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        items = raw.get("alts") if isinstance(raw, dict) else None
        if isinstance(items, dict):
            for key, value in items.items():
                if not isinstance(value, list):
                    continue
                good = [str(v).strip() for v in value if str(v or "").strip()]
                if good:
                    data[_flat_key(key)] = good
    except (OSError, ValueError) as exc:
        print("⚠️ Варианты фраз %s не прочитаны: %s" % (name, exc))
    _ALTS_CACHE[name] = data
    return data


def alts(text: Any, level: str = "a2") -> List[str]:
    """Равнозначные варианты фразы (пусто — вариантов нет).

    Ищем СНАЧАЛА точное совпадение фразы, потом — вхождение (задание дрилла
    может нести лишние слова вроде вежливого «please»).
    """
    key = _flat_key(text)
    if not key:
        return []
    table = _alts_file(level)
    found = list(table.get(key) or [])
    if found:
        return found
    for item in sorted(table, key=len, reverse=True):
        if item in key:
            return list(table[item])
    return []
