# -*- coding: utf-8 -*-
# =========================================================
# SCENE_REACTIONS.PY - движок реакций в сценах (НАМЕРЕНИЯ, не фразы)
# =========================================================
# Задача: сцена не читает скрипт подряд, а ОТВЕЧАЕТ на то, что ученик
# сказал. Скриптуем НЕ фразы ученика (их бесконечность), а намерения:
#   назвал предмет / назвал число / да / нет / благодарность / счёт /
#   туалет / рекомендация / что есть / сколько стоит / жалоба / не понял.
#
# Данные: data/reactions_a2.json - ОБЩИЕ на уровень, один файл на все сцены.
# Новая сцена = вопросы + метки slot в data/scenes_a2.json, код не трогаем.
# Модуль чистый: ни Tk, ни модели, ни сети (образец scenes.py, glossary.py).
#
# Решение ученика 100 (03.11.2026): не понял -> ПЕРЕСПРОС, не молчание.
# =========================================================

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

_log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "reactions_a2.json"

# Виды намерений (строки, чтобы не тянуть enum в тесты).
EMPTY = "empty"          # ничего не сказал
ITEM = "item"            # назвал предмет из слота: beer, steak, card
NUMBER = "number"        # назвал число: two, 3, just me (слот people)
YES = "yes"
NO = "no"
THANKS = "thanks"
BILL = "bill"            # просит счёт
TOILET = "toilet"
RECOMMEND = "recommend"  # что посоветуете
HAVE = "have"            # что у вас есть
PRICE = "price"          # сколько стоит
COMPLAINT = "complaint"  # недоволен едой
DONTKNOW = "dontknow"    # не знаю
REPEAT = "repeat"        # переспрос: повторите вопрос
OTHER = "other"          # слова есть, но незнакомые

_cache: Optional[dict] = None


@dataclass
class Intent:
    """Что ученик имел в виду. count - сколько предметов (0 = не сказано)."""
    kind: str
    item: str = ""
    count: int = 0

    def __bool__(self) -> bool:
        return self.kind not in ("", EMPTY)


# ---------------------------------------------------------
# Данные
# ---------------------------------------------------------
def library() -> dict:
    """Словари уровня (кэш на запуск). Битый файл -> пустой словарь, не падение."""
    global _cache
    if _cache is None:
        try:
            with open(DATA_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError) as e:
            _log.warning("reactions: не читается %s: %s", DATA_PATH, e)
            _cache = {}
    return _cache


def reload() -> dict:
    """Сбросить кэш (тесты, правка файла на ходу)."""
    global _cache
    _cache = None
    return library()


def slot_names() -> List[str]:
    """Все известные метки слотов."""
    return sorted((library().get("slots") or {}).keys())


def has_slot(slot: str) -> bool:
    return str(slot or "") in (library().get("slots") or {})


def ask(slot: str) -> str:
    """Вопрос слота (для переспроса и для тестов)."""
    return str(_conf(slot).get("ask") or "")


def _conf(slot: str) -> dict:
    return (library().get("slots") or {}).get(str(slot or "")) or {}


def _words(table: str) -> List[str]:
    return [str(w) for w in ((library().get("words") or {}).get(table) or [])]


# ---------------------------------------------------------
# Разбор текста
# ---------------------------------------------------------
def tokens(text: str) -> List[str]:
    """Слова в нижнем регистре, без знаков (апостроф внутри слова сохраняем)."""
    out = []
    for chunk in str(text or "").lower().replace("-", " ").replace("/", " ").split():
        word = "".join(ch for ch in chunk if ch.isalnum() or ch == "'")
        if word:
            out.append(word)
    return out


def _pos(ws: List[str], phrase: str) -> int:
    """Позиция фразы в списке слов (-1 если нет)."""
    pw = tokens(phrase)
    if not pw:
        return -1
    n = len(pw)
    for i in range(len(ws) - n + 1):
        if ws[i:i + n] == pw:
            return i
    return -1


def _find(ws: List[str], keys) -> Optional[str]:
    """Самая ДЛИННАЯ совпавшая фраза из keys (при равной длине - что раньше)."""
    best = None
    best_len = 0
    best_pos = 10 ** 6
    for key in keys:
        p = _pos(ws, key)
        if p < 0:
            continue
        n = len(tokens(key))
        if n > best_len or (n == best_len and p < best_pos):
            best, best_len, best_pos = key, n, p
    return best


def _find_item(ws: List[str], conf: dict):
    """Предмет слота: сначала самые длинные названия (ice cream раньше ice)."""
    items = conf.get("items") or {}
    found = _find(ws, items.keys())
    if found is None:
        # «two beers» -> «beer»: ищем по единственному числу
        singular = [_singular(w) for w in ws]
        found = _find(singular, items.keys())
    if found is None:
        return None, ""
    value = items.get(found)
    if found not in ws and _singular(found) in ws:
        value = items.get(found)
    return value, found


def _find_number(ws: List[str], conf: dict):
    """Число людей: цифра/слово/«just me»/«two of us». 0 - не сказано."""
    nums: Dict[str, str] = library().get("numbers") or {}
    if not nums:
        return 0
    found = _find(ws, nums.keys())
    if found is None:
        return 0
    label = str(nums.get(found) or "")
    table = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5,
             "Six": 6, "Seven": 7, "Eight": 8, "Nine": 9, "Ten": 10}
    return int(table.get(label, 0))



# ---------------------------------------------------------
# Намерение
# ---------------------------------------------------------
def intent(slot: str, text: str) -> Intent:
    """Что ученик имел в виду. Порядок проверок ВАЖЕН (см. ниже)."""
    ws = tokens(text)
    if not ws:
        return Intent(EMPTY)
    conf = _conf(slot)

    # 1) ЖАЛОБА раньше всего: «sorry, the food is cold» - это не переспрос.
    bad = _find(ws, _words("complaint"))
    if bad:
        return Intent(COMPLAINT, item=bad)
    # 2) Туалет.
    if _find(ws, _words("toilet")):
        return Intent(TOILET)
    # 3) Сколько стоит / что посоветуете - это ВОПРОС, он раньше предмета
    #    («how much is coffee?» - про цену, а не «One coffee»).
    if _find(ws, _words("howmuch")):
        return Intent(PRICE)
    if _find(ws, _words("recommend")):
        return Intent(RECOMMEND)
    # 4) Предмет слота: «just water thanks» - вода, «i will pay by card» - карта.
    item, _key = _find_item(ws, conf)
    if item:
        return Intent(ITEM, item=str(item), count=_find_number(ws, conf))
    # 5) Счёт: «no, thanks, just the bill».
    if _find(ws, _words("bill")):
        return Intent(BILL)
    # 6) «Что у вас есть?» - список слота (если предмет не назван).
    if _find(ws, _words("whatyouhave")):
        return Intent(HAVE)
    # 6) Число: только слот, которому оно нужно (people).
    if conf.get("numbers"):
        count = _find_number(ws, conf)
        if count:
            return Intent(NUMBER, count=count)
    # 7) Свои слова слота (например goodbye: «bye»).
    own = conf.get("words") or {}
    if own:
        key = _find(ws, own.keys())
        if key:
            return Intent(OTHER, item=str(own[key]))
    # 8) Отказ раньше благодарности: «no, thanks» - ОТКАЗ.
    if _find(ws, _words("no")):
        return Intent(NO)
    if _find(ws, _words("thanks")):
        return Intent(THANKS)
    if _find(ws, _words("yes")):
        return Intent(YES)
    # 9) Не знаю - раньше переспроса.
    if _find(ws, _words("dontknow")):
        return Intent(DONTKNOW)
    # 10) Переспрос: «sorry?», «again please». Только если ВСЕ слова знакомы
    #     («sorry, latte» - это про латте, а не «повторите»).
    if _find(ws, _words("repeat")) and _all_known(ws, conf):
        return Intent(REPEAT)
    return Intent(OTHER)


# ---------------------------------------------------------
# Ответ
# ---------------------------------------------------------
def reply(slot: str, text: str) -> Optional[str]:
    """Что сказать ученику. None - окно ПОВТОРЯЕТ вопрос (переспрос)."""
    return reply_to(slot, intent(slot, text))


def reply_to(slot: str, it: Intent) -> Optional[str]:
    """Ответ на готовое намерение (без повторного разбора)."""
    conf = _conf(slot)
    uni = library().get("universal") or {}
    kind = it.kind
    if kind in ("", EMPTY):
        return None
    if kind == REPEAT:
        return None                      # повторит вопрос окно
    if kind == ITEM:
        if it.count > 1:
            plurals = conf.get("plurals") or {}
            many = plurals.get(it.item, it.item)
            return _tpl(conf, "echo_many", "{num} {item}, coming up.",
                        item=many, num=_num_word(it.count))
        return _tpl(conf, "echo_one", conf.get("echo") or "{item}, coming up.",
                    item=it.item, num="")
    if kind == NUMBER:
        if it.count == 1:
            return _tpl(conf, "echo_one", "{num} people. This way, please.",
                        item="", num=_num_word(1))
        return _tpl(conf, "echo", "{num} people. This way, please.",
                    item="", num=_num_word(it.count))
    if kind == OTHER and it.item:
        return _cap(it.item)  # готовый ответ из слов слота (goodbye)
    text = conf.get(kind) or uni.get(kind)
    return _cap(text) if text else None


def slot_hotwords(slot: str, limit: int = 14) -> List[str]:
    """Слова, которых ждём от ученика в этом слоте (подсказка распознаванию).

    Вопрос сцены известен заранее, а в его слоте уже лежат ожидаемые слова
    (jacket, size, card, receipt…). Whisper с таким словарём слышит слово,
    которое собирался сказать ученик, а не похожее (живой урок 09.11.2026:
    «I'm looking for a jacket» → «i'm looking at jacket»).

    Пустой список — подсказки нет (слот неизвестен, словарь пуст).
    """
    conf = _conf(slot)
    if not conf:
        return []
    words: List[str] = []
    # Сначала ФРАЗЫ слота («just looking», «here you are») — они важнее
    # предметов: именно их ученик строит сам.
    extra = conf.get("words") or {}
    if isinstance(extra, dict):
        words.extend(str(k) for k in extra.keys() if k)
    items = conf.get("items") or {}
    if isinstance(items, dict):
        # только нормальные слова: значения, а не варианты написания
        words.extend(str(v) for v in items.values() if v)
    out: List[str] = []
    for word in words:
        word = word.strip()
        if len(word) < 3 or word.lower() in ("the", "and", "you"):
            continue
        if word.lower() not in [w.lower() for w in out]:
            out.append(word)
        if len(out) >= limit:
            break
    return out


def unknown(slot: str) -> str:
    """Не понял: СВОЙ переспрос слота, иначе общий + вопрос слота."""
    conf = _conf(slot)
    uni = library().get("universal") or {}
    own = str(conf.get("fallback") or "")
    if own:
        return own
    base = str(uni.get("repeat") or "Sorry, could you say that again?")
    question = str(conf.get("ask") or "")
    return (base + " " + question).strip()


def _num_word(count: int) -> str:
    table = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
             6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}
    return table.get(int(count), str(count))


def _cap(text: str) -> str:
    """Первая буква заглавная: «soup to start» -> «Soup to start»."""
    text = str(text or "").strip()
    return text[:1].upper() + text[1:] if text else text


def _singular(word: str) -> str:
    """«beers» -> «beer» (множественное число ищем как единственное)."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _all_known(ws, conf: dict) -> bool:
    """Все слова реплики знакомы (иначе это незнакомое слово, а не переспрос)."""
    known = set()
    for table in ("yes", "no", "thanks", "bill", "toilet", "repeat",
                  "dontknow", "recommend", "whatyouhave", "howmuch", "complaint"):
        for phrase in _words(table):
            known.update(tokens(phrase))
    for phrase in (library().get("numbers") or {}):
        known.update(tokens(phrase))
    for word in (conf.get("items") or {}):
        known.update(tokens(word))
    fillers = {"please", "pardon", "could", "you", "say", "that", "it", "me", "i",
               "am", "can", "do", "what", "again", "a", "the", "is", "are", "for",
               "i'd", "like", "want", "have", "some", "would", "and", "of", "us"}
    known.update(fillers)
    return all(w in known for w in ws)


def _tpl(conf: dict, key: str, default: str, item: str, num: str) -> str:
    """Подставить предмет/число в шаблон слота."""
    tpl = str(conf.get(key) or default)
    try:
        return _cap(tpl.format(item=item, num=num))
    except (KeyError, IndexError, ValueError):
        _log.warning("reactions: плохой шаблон %s: %r", key, tpl)
        return tpl
