"""Карточки правил A2 (§79): тексты правил и выбор нужной карточки.

Решение ученика 12.11.2026: при ошибке — выделение, клик на красном куске и
табличка с правилом и примерами. Выделение сделано в §77, здесь — тексты и
выбор. Тексты правил пишет человек (решение 67), модель их не сочиняет.

Два вида карточек:
  * kind="grammar" — правило грамматики (пишется руками);
  * kind="choice"  — пара слов из data/phrase_pairs_a2.json (pair / why / en).

Поле "rule" связывает карточку с закрытым списком Аналитика (roles/analyst.py:
past_simple, aux_verb, verb_form, word_order, article, preposition, plural,
spelling, word_choice, other). У одного rule может быть НЕСКОЛЬКО карточек
(article: a/an и the) — тогда нужная выбирается по совпадению слов ошибки с
полями "words" / "hints", а при равенстве — карточка с "default": true.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
CARDS_PATH = os.path.join(ROOT, "data", "cards_a2.json")

_cache = {"mtime": None, "cards": {}}


def _phrase_re(word):
    """Регулярка «слово целиком» (`put on` — тоже, в два слова)."""
    parts = [re.escape(p) for p in str(word or "").lower().split()]
    if not parts:
        return None
    return re.compile(r"(?<![a-z0-9])" + r"\s+".join(parts) + r"(?![a-z0-9])")


def load(force=False):
    """Все карточки {id: карточка}. Кэш по mtime: правишь файл — видно сразу."""
    try:
        mtime = os.path.getmtime(CARDS_PATH)
    except OSError:
        return {}
    if not force and _cache["mtime"] == mtime:
        return _cache["cards"]
    try:
        with open(CARDS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print("⚠️ Карточки правил не прочитались: %s" % exc)
        return {}
    raw = data.get("cards") if isinstance(data, dict) else {}
    cards = {}
    for card_id, card in (raw or {}).items():
        if not isinstance(card, dict) or not card.get("title"):
            continue
        card = dict(card)
        card["id"] = str(card_id)
        cards[str(card_id)] = card
    _cache["mtime"] = mtime
    _cache["cards"] = cards
    return cards


def get(card_id):
    """Карточка по id или None."""
    return load().get(str(card_id or ""))


def score(card, text):
    """Сколько слов карточки (words/hints) встретилось в тексте ошибки."""
    low = str(text or "").lower()
    if not low:
        return 0
    hits = 0
    for word in list(card.get("words") or []) + list(card.get("hints") or []):
        rx = _phrase_re(word)
        if rx is not None and rx.search(low):
            hits += 1
    return hits


def pick(rule, wrong="", correct=""):
    """Карточка под ошибку Аналитика: {"rule": "article", "wrong": ...}."""
    rule = str(rule or "").strip().lower()
    cards = load()
    items = [c for c in cards.values() if c.get("rule") == rule]
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    text = "%s %s" % (wrong or "", correct or "")
    best, best_score = None, 0
    for card in items:
        got = score(card, text)
        if got > best_score:
            best, best_score = card, got
    if best is not None:
        return best
    for card in items:
        if card.get("default"):
            return card
    # Ничего не совпало и умолчания нет — карточку НЕ выдумываем: пусть
    # ученик увидит честное «правило пока не написано» (см. ui/widgets/chat_view).
    return None


def rules_covered():
    """Какие rule закрыты карточками (для проверки полноты)."""
    return {c.get("rule") for c in load().values() if c.get("rule")}
