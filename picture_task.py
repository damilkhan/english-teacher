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
import random
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


def _word_stem(word):
    """Основа слова для сверки: expensive→expens, bigger→bigg, used→us."""
    stem = str(word or "").strip().lower()
    for tail in ("est", "ing", "er", "ed", "s"):
        if len(stem) > len(tail) + 2 and stem.endswith(tail):
            return stem[:-len(tail)]
    return stem


def words_report(text, words):
    """Какие слова урока прозвучали в описании — ФАКТ, без оценки (§86).

    Решение ученика 16.11.2026: фото-задание фразы урока НЕ требует, поэтому
    это не проверка, а строчка для сведения. Зачёт задания — по буквам.
    Пустая строка, если слов урока нет.
    """
    items = [str(w).strip() for w in (words or ()) if str(w).strip()]
    if not items:
        return ""
    low = str(text or "").lower()
    used, missed = [], []
    for word in items:
        rx = re.compile(r"(?<![a-z0-9])" + re.escape(_word_stem(word)))
        (used if rx.search(low) else missed).append(word)
    parts = []
    if used:
        parts.append("used: %s" % ", ".join(used))
    if missed:
        parts.append("not used: %s" % ", ".join(missed))
    return "\U0001F50E Words from the lesson — %s." % "; ".join(parts)


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
    """Ключ фото для уровня, по возможности НЕ повторяя уже показанные.

    §62 (жалоба ученика 07.11.2026): раньше всегда брался ПЕРВЫЙ по алфавиту
    ключ, и задание «опиши фото» каждый урок показывало автобусную станцию
    (bus-stop). Теперь из непоказанных берём СЛУЧАЙНОЕ; когда все фото уровня
    показаны — начинаем круг заново (тоже случайно).
    """
    catalog = load_catalog() if catalog is None else catalog
    keys = pictures_for_level(level, catalog)
    if not keys:
        return None
    used = set(used or ())
    fresh = [k for k in keys if k not in used]
    pool = fresh or keys
    if len(pool) == 1:
        return pool[0]
    return random.choice(pool)


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


def pick_by_topic(level, topic="", catalog=None, used=None):
    """Ключ фото по ТЕМЕ урока (§86, 17.11.2026).

    Сначала ищем фото нужного уровня с той же темой, потом — среди всех.
    Среди найденных берём ещё не показанное (как pick_picture).
    Пусто — темы нет в каталоге, вызывающий берёт случайное по уровню.
    """
    catalog = load_catalog() if catalog is None else catalog
    want = str(topic or "").strip().lower()
    if not want:
        return None
    same_level, other_level = [], []
    for key, card in catalog.items():
        have = str(card.get("topic") or "").strip().lower()
        if not have:
            continue
        if have != want and want not in have and have not in want:
            continue
        if normalize_level(card.get("level")) == normalize_level(level):
            same_level.append(key)
        else:
            other_level.append(key)
    keys = sorted(same_level) or sorted(other_level)
    if not keys:
        return None
    used = set(used or ())
    fresh = [k for k in keys if k not in used]
    return random.choice(fresh or keys)


def describe_task(level, catalog=None, used=None, topic="", key=""):
    """Данные задания для одного фото: тема, пункты, путь, порог.

    used — ключи уже показанных фото (профиль ученика), чтобы не повторяться.
    """
    catalog = load_catalog() if catalog is None else catalog
    # §86: фото может быть привязано к уроку — по ключу (data/lessons_a2.json,
    # поле picture) или по теме. Нет ни того, ни другого — как раньше:
    # случайное среди непоказанных фото этого уровня.
    chosen = str(key or "").strip()
    if chosen not in catalog:
        chosen = pick_by_topic(level, topic, catalog, used) or ""
    if not chosen:
        chosen = pick_picture(level, used=used, catalog=catalog) or ""
    if not chosen:
        return None
    key = chosen
    entry = dict(catalog[key])
    entry["key"] = key
    entry["threshold"] = threshold_for(level)
    entry["level"] = level_for_threshold(level)
    return entry
