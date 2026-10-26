# -*- coding: utf-8 -*-
# =========================================================
# GAPS.PY — КАРТА ПРОБЕЛОВ ученика (§46, решение 26.10.2026)
# =========================================================
# Считаем не пары «сказал → как надо» (замер: 22 пары, повторов 0 — карта
# была бы пустой), а ГРАММАТИЧЕСКИЕ ПРАВИЛА из закрытого списка RULES.
#
# Один и тот же список знают все:
#   * Аналитик — выбирает ОДНО слово и кладёт в поле "rule" каждой ошибки;
#   * gaps.py — считает по базе, сколько раз правило встречалось;
#   * Планировщик и Аналитик — получают 3 самых частых правила строкой;
#   * вкладка «Профиль» → «Статистика» — показывает таблицу ученику.
#
# Порог: правило встретилось 2+ раза = ПРОБЕЛ, 1 раз = «встречалось».
# «other» в промпт НЕ идёт (это свалка, а не правило) — только в таблицу.
# =========================================================

import difflib
import re
from collections import Counter

import config
import stats_store

# Закрытый список правил (модель своё придумать не может).
RULES = ("past_simple", "aux_verb", "verb_form", "word_order", "article",
         "preposition", "plural", "spelling", "word_choice", "other")

# Подписи для вкладки «Профиль» (по-русски, ученик читает их).
RULE_RU = {
    "past_simple": "прошедшее время",
    "aux_verb": "do/does/did (вспомогательный глагол)",
    "verb_form": "форма глагола",
    "word_order": "порядок слов",
    "article": "артикль a/an/the",
    "preposition": "предлог in/on/at",
    "plural": "множественное число",
    "spelling": "написание",
    "word_choice": "не то слово / форма слова",
    "other": "прочее (без правила)",
}

# Как правило называть в промпте (английский урок — английские слова).
RULE_EN = {
    "past_simple": "past simple (verb forms in the past)",
    "aux_verb": "do/does/did and questions/negatives",
    "verb_form": "verb form (after modals, -ing/-ed)",
    "word_order": "word order",
    "article": "articles a/an/the",
    "preposition": "prepositions in/on/at",
    "plural": "plural of nouns",
    "spelling": "spelling",
    "word_choice": "word choice (wrong word or word form)",
    "other": "other",
}

ARTICLES = {"a", "an", "the"}
PREPOSITIONS = {"in", "on", "at", "to", "of", "for", "with", "by", "from",
                "about", "into", "over", "under", "near", "after", "before",
                "during", "without", "between", "through", "off", "up"}
AUX_WORDS = {"do", "does", "did", "don't", "doesn't", "didn't", "not", "no",
             "am", "is", "are", "was", "were", "will", "can", "could",
             "should", "would", "have", "has", "had"}

# Частые неправильные глаголы: для ДОГАДКИ правила у старых записей
# (у них поля rule нет — модель их не размечала).
IRREGULAR_PAST = {
    "be": ("was", "were"), "begin": ("began",), "break": ("broke",),
    "bring": ("brought",), "buy": ("bought",), "catch": ("caught",),
    "choose": ("chose",), "come": ("came",), "do": ("did",),
    "drink": ("drank",), "drive": ("drove",), "eat": ("ate",),
    "fall": ("fell",), "feel": ("felt",), "find": ("found",),
    "fly": ("flew",), "forget": ("forgot",), "get": ("got",),
    "give": ("gave",), "go": ("went",), "have": ("had",),
    "hear": ("heard",), "keep": ("kept",), "know": ("knew",),
    "leave": ("left",), "lose": ("lost",), "make": ("made",),
    "meet": ("met",), "pay": ("paid",), "read": ("read",),
    "run": ("ran",), "say": ("said",), "see": ("saw",),
    "send": ("sent",), "sit": ("sat",), "sleep": ("slept",),
    "speak": ("spoke",), "spend": ("spent",), "stand": ("stood",),
    "swim": ("swam",), "take": ("took",), "teach": ("taught",),
    "tell": ("told",), "think": ("thought",), "understand": ("understood",),
    "wake": ("woke",), "wear": ("wore",), "win": ("won",),
    "write": ("wrote",),
}

# Закрытый список «не то слово»: пары РАЗНЫХ слов, которые похожи по буквам
# (догадка по difflib отнесла бы их к опечатке). §46: lay -> lie, possible -> possibly.
WORD_CHOICE_PAIRS = {
    ("lay", "lie"), ("lie", "lay"),
    ("possible", "possibly"), ("probable", "probably"),
    ("say", "tell"), ("tell", "say"),
    ("do", "make"), ("make", "do"),
    ("learn", "teach"), ("teach", "learn"),
    ("lose", "loose"), ("loose", "lose"),
    ("then", "than"), ("than", "then"),
    ("its", "it's"), ("it's", "its"),
    ("affect", "effect"), ("effect", "affect"),
    ("borrow", "lend"), ("lend", "borrow"),
}


# ---------------------------------------------------------
# Правило: нормализация и догадка
# ---------------------------------------------------------
def normalize_rule(value):
    """Любое слово модели → одно из RULES. Неизвестное → "other"."""
    key = str(value or "").strip().lower()
    key = key.replace("-", "_").replace(" ", "_")
    return key if key in RULES else "other"


def _words(text):
    """Слова латиницей в нижнем регистре (апостроф внутри слова сохраняем)."""
    return re.findall("[A-Za-z']+", str(text or "").lower())


def _diff(first, second):
    """Что убрали и что добавили (с учётом повторов)."""
    a, b = Counter(first), Counter(second)
    return list((a - b).elements()), list((b - a).elements())


def guess_rule(wrong, correct):
    """ДОГАДКА правила по паре «было → стало» (модель не спрашиваем).

    Нужна только там, где правила нет: старые записи из JSON и правки из
    описания фото. Правило от Аналитика всегда важнее этой догадки.
    """
    was, now = _words(wrong), _words(correct)
    if not was or not now or was == now:
        return "other"
    if sorted(was) == sorted(now):
        return "word_order"          # те же слова, другой порядок

    removed, added = _diff(was, now)

    # вспомогательный глагол: you not have → you don't have
    if added and set(added) <= AUX_WORDS and (not removed or set(removed) <= AUX_WORDS):
        return "aux_verb"
    # артикль добавили/убрали/заменили
    if added and set(added) <= ARTICLES and (not removed or set(removed) <= ARTICLES):
        return "article"
    if removed and not added and set(removed) <= ARTICLES:
        return "article"
    # лишнее/пропавшее "to" после модального: I must to say -> I must say
    if removed == ["to"] and not added:
        return "verb_form"

    # предлог поменяли на другой предлог
    if removed and added and set(removed) <= PREPOSITIONS and set(added) <= PREPOSITIONS:
        return "preposition"
    # предлог ПРОПАЛ вместе с лишними словами: one time in month -> once a month
    if set(removed) & PREPOSITIONS:
        return "preposition"

    if len(removed) == 1 and len(added) == 1:
        old, new = removed[0], added[0]
        if (old, new) in WORD_CHOICE_PAIRS:
            return "word_choice"     # lay -> lie: ДРУГОЕ слово, не опечатка
        # наречие вместо прилагательного: possible -> possibly (НЕ «написание»)
        if new.endswith("ly") and (new[:-2] == old or new[:-2] + "e" == old):
            return "word_choice"
        if new in IRREGULAR_PAST.get(old, ()):
            return "past_simple"
        if new == old + "ed" or (old.endswith("e") and new == old + "d"):
            return "past_simple"
        if new == old + "s" or new == old + "es" \
                or (old.endswith("y") and new == old[:-1] + "ies"):
            return "plural"
        ratio = difflib.SequenceMatcher(None, old, new).ratio()
        if ratio >= 0.8:
            return "spelling"
        return "word_choice"         # одно слово заменили другим = «не то слово»

    return "other"


# ---------------------------------------------------------
# Агрегация
# ---------------------------------------------------------
def gap_threshold():
    """Сколько раз правило должно встретиться, чтобы звать его пробелом."""
    try:
        return max(1, int(getattr(config, "GAPS_MIN_COUNT", 2)))
    except (TypeError, ValueError):
        return 2


def aggregate(rows=None, user_id=None):
    """Свести записи по правилам: [( правило, сколько, примеры, даты ), …].

    rows=None → читаем базу. Сортировка: сначала частые, внутри — по имени
    правила, чтобы таблица не «прыгала» между перерисовками.
    """
    data = stats_store.rows(user_id) if rows is None else (rows or [])
    buckets = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        rule = normalize_rule(row.get("rule"))
        bucket = buckets.get(rule)
        if bucket is None:
            bucket = buckets[rule] = {
                "rule": rule,
                "label": RULE_RU.get(rule, rule),
                "count": 0,
                "examples": [],
                "first": "",
                "last": "",
            }
        bucket["count"] += 1
        wrong = str(row.get("wrong") or "").strip()
        correct = str(row.get("correct") or "").strip()
        pair = (wrong, correct)
        if (wrong or correct) and pair not in bucket["examples"] \
                and len(bucket["examples"]) < 3:
            bucket["examples"].append(pair)
        date = str(row.get("date") or "").strip()
        if date:
            if not bucket["first"] or date < bucket["first"]:
                bucket["first"] = date
            if not bucket["last"] or date > bucket["last"]:
                bucket["last"] = date

    out = list(buckets.values())
    # «прочее» — ВСЕГДА последним: это не правило, и вверху таблицы ему не место
    out.sort(key=lambda b: (b["rule"] == "other", -b["count"], b["rule"]))
    limit = gap_threshold()
    for bucket in out:
        # «без правила» пробелом не считается, даже если встречалось 10 раз
        bucket["is_gap"] = bucket["count"] >= limit and bucket["rule"] != "other"
    return out


def _example_text(pairs, limit=1):
    """Одна-две пары «было → стало» строкой для промпта."""
    parts = []
    for wrong, correct in pairs[:limit]:
        if wrong and correct:
            parts.append('"%s" -> "%s"' % (wrong, correct))
        elif wrong:
            parts.append('"%s"' % wrong)
    return "; ".join(parts)


def prompt_block(user_id=None, limit=None, rows=None):
    """Строка «частые проблемы» для Планировщика И Аналитика (английский).

    Пусто, если пробелов нет или блок выключен в config. «other» не отдаём.
    Формулировка осторожная: список — это СПРАВКА, а не список того, что
    надо найти (иначе модель начинает выдумывать ошибки, §35/§45).
    """
    if not getattr(config, "GAPS_IN_PROMPT", True):
        return ""
    try:
        limit = int(limit or getattr(config, "GAPS_PROMPT_LIMIT", 3))
    except (TypeError, ValueError):
        limit = 3
    items = [b for b in aggregate(rows=rows, user_id=user_id)
             if b["rule"] != "other" and b["is_gap"]]
    if not items:
        return ""
    lines = ["- %s: %d times%s" % (RULE_EN.get(b["rule"], b["rule"]), b["count"],
                                   (" (e.g. %s)" % _example_text(b["examples"]))
                                   if b["examples"] else "")
             for b in items[:max(1, limit)]]
    return ("STUDENT'S RECURRING PROBLEMS on record (statistics only, not a to-do list; do NOT\n"
            "hunt for them):\n"
            + "\n".join(lines) + "\n"
            "Correct ONLY real mistakes in this message. Never invent a mistake\n"
            "to match this list; a correct sentence stays correct.")


def table_rows(user_id=None, limit=10, rows=None):
    """Строки для таблицы «Профиль → Статистика»: [( правило, раз, примеры )]."""
    out = []
    for bucket in aggregate(rows=rows, user_id=user_id):
        examples = []
        for wrong, correct in bucket["examples"]:
            if wrong and correct:
                examples.append("%s → %s" % (wrong, correct))
            elif wrong:
                examples.append(wrong)
            if len(examples) >= 2:
                break
        out.append({
            "rule": bucket["rule"],
            "label": bucket["label"],
            "count": bucket["count"],
            "examples": "; ".join(examples),
            "gap": bucket["is_gap"],
        })
        if limit and len(out) >= limit:
            break
    return out
