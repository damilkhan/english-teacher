# -*- coding: utf-8 -*-
# =========================================================
# PICTURE_TASK.PY — задание «опиши фото»: каталог, выбор, порог букв
# =========================================================
# Чистая логика без окна и без сети:
#   * каталог фото (assets/pictures/pictures.json) и выбор фото по уровню;
#   * ЖЁСТКИЙ порог букв в описании (config.PICTURE_LETTER_THRESHOLDS);
#   * защита от накрутки: самое частое слово ≤ 40 %, разных слов ≥ половины
#     ожидаемых.
#
# Замеры, на которых всё построено (§18, 23.10.2026):
#   * порог = 80 % от минимума букв, который пишет модель-«ученик» уровня;
#     A2 = 105 букв;
#   * фото меньше 768 px по длинной стороне отправлять модели НЕЛЬЗЯ
#     (ложно бракует верный ответ), храним 1024.
# =========================================================

import json
import os
import re

import config


# ---------- каталог фото ----------
_catalog_cache = None


def load_catalog(path=None):
    """{ключ: {file, level, topic, points, credit}} из pictures.json.

    Путь к файлу картинки становится АБСОЛЮТНЫМ (сразу годен для PIL),
    сам JSON в git лежит с относительными путями.
    """
    global _catalog_cache
    path = path or config.PICTURE_INDEX
    if _catalog_cache is not None and path == config.PICTURE_INDEX:
        return _catalog_cache
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    pictures = data.get("pictures") if isinstance(data, dict) else None
    if not isinstance(pictures, dict):
        return {}
    base = os.path.dirname(path)
    result = {}
    for key, item in pictures.items():
        if not isinstance(item, dict) or not item.get("file"):
            continue
        entry = dict(item)
        entry["key"] = key
        entry["path"] = os.path.join(base, str(item["file"]).replace("/", os.sep))
        result[key] = entry
    if path == config.PICTURE_INDEX:
        _catalog_cache = result
    return result


LEVEL_ORDER = ("A0", "A1", "A2", "B1", "B2", "C1", "C2")


def normalize_level(level):
    """'a2' → 'A2'; пусто/мусор → ''."""
    text = str(level or "").strip().upper()
    return text if text in LEVEL_ORDER else ""


def level_for_threshold(level):
    """Уровень для порога букв: неизвестный → как A2 (config)."""
    return normalize_level(level) or "A2"


def threshold_for(level):
    """Порог букв (ЖЁСТКИЙ) для уровня."""
    table = getattr(config, "PICTURE_LETTER_THRESHOLDS", {}) or {}
    key = level_for_threshold(level)
    value = table.get(key)
    if value is None:
        value = getattr(config, "PICTURE_LETTER_DEFAULT", 105)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 105


def pictures_for_level(level, catalog=None):
    """Ключи фото уровня; если таких нет — ближайшего НИЖЕ (A0 … уровень)."""
    catalog = load_catalog() if catalog is None else catalog
    level = normalize_level(level)
    if not level:
        level = "A0"
    limit = LEVEL_ORDER.index(level)
    exact = [k for k, v in catalog.items()
             if normalize_level(v.get("level")) == level]
    if exact:
        return sorted(exact)
    for step in range(limit - 1, -1, -1):          # ниже уровня
        lower = LEVEL_ORDER[step]
        found = [k for k, v in catalog.items()
                 if normalize_level(v.get("level")) == lower]
        if found:
            return sorted(found)
    return sorted(catalog.keys())


def pick_picture(level, used=None, catalog=None):
    """Ключ фото для уровня, по возможности НЕ повторяя уже показанные."""
    catalog = load_catalog() if catalog is None else catalog
    keys = pictures_for_level(level, catalog)
    if not keys:
        return None
    used = set(used or ())
    fresh = [k for k in keys if k not in used]
    return (fresh or keys)[0]


# ---------- порог букв и защита от накрутки ----------
_WORD_RE = re.compile(r"[A-Za-z']+")


def letters(text):
    """Сколько в тексте БУКВ (пробелы, цифры и знаки не считаем)."""
    return sum(1 for ch in str(text or "") if ch.isalpha())


def words(text):
    """Слова ответа: латиница/апостроф, в нижнем регистре."""
    return _WORD_RE.findall(str(text or "").lower())


def word_stats(text):
    """(сколько слов, сколько РАЗНЫХ, доля самого частого слова)."""
    items = words(text)
    if not items:
        return 0, 0, 0.0
    counts = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    top = max(counts.values())
    return len(items), len(counts), top / float(len(items))


def expected_words(level):
    """Сколько РАЗНЫХ слов ждём: примерно порог букв / 4 (A2 → 26 → 13)."""
    return max(6, int(round(threshold_for(level) / 4.0)))


def check_description(text, level):
    """Годится ли описание. Словарь с причиной отказа (None = принято).

    Причины:
      too_short  — меньше порога букв;
      repeated   — одно слово больше 40 % слов (накрутка повтором);
      few_words  — слишком мало разных слов для уровня.
    """
    threshold = threshold_for(level)
    count = letters(text)
    total, unique, top_share = word_stats(text)
    want_unique = max(3, int(round(expected_words(level)
                                  * getattr(config, "PICTURE_UNIQUE_SHARE", 0.5))))
    max_share = getattr(config, "PICTURE_MAX_WORD_SHARE", 0.40)
    reason = None
    if count < threshold:
        reason = "too_short"
    elif total and top_share > max_share:
        reason = "repeated"
    elif unique < want_unique:
        reason = "few_words"
    return {
        "ok": reason is None,
        "reason": reason,
        "letters": count,
        "threshold": threshold,
        "words": total,
        "unique": unique,
        "want_unique": want_unique,
        "top_share": round(top_share, 3),
    }


def describe_task(level, catalog=None):
    """Данные задания для одного фото: тема, пункты, путь, порог."""
    catalog = load_catalog() if catalog is None else catalog
    key = pick_picture(level, catalog=catalog)
    if not key:
        return None
    entry = dict(catalog[key])
    entry["threshold"] = threshold_for(level)
    entry["level"] = level_for_threshold(level)
    return entry
