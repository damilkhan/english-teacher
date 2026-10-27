# -*- coding: utf-8 -*-
# =========================================================
# VOCABULARY.PY — карточки слов для интервального повторения
# =========================================================
# Зачем: ученик переводит ОДИНОЧНОЕ слово в экспресс-переводчике — слово
# копится САМО (без кнопок «сохранить»), и позже Джейн его спрашивает.
#
# Одно ЗНАЧЕНИЕ = одна карточка («ключ» → key / wrench → две карточки).
# Поля карточки:
#   word     — русское слово, которое переводил ученик («ключ»);
#   en       — английское значение («key»);
#   example  — пример из переводчика («Open the door with this key.»);
#   level    — ступень 0..5 (5 = выучено, больше не спрашиваем);
#   next_due — когда спросить в следующий раз («ГГГГ-ММ-ДД»);
#   created / last_ok / hits / misses — статистика.
#
# ЛЕСТНИЦА (интервалы в INTERVALS_DAYS):
#   0 новая → 1 через 1 день → 2 через 3 дня → 3 через 7 дней →
#   4 через 21 день → 5 выучено (не спрашиваем).
#   Удачный ответ (вердикт GOOD) → +1;
#   промах («Почти»/«Попробуй») → уровень НЕ трогаем (решение 53), только
#   «спросить завтра»: одна осечка не отбрасывает слово назад.
#
# Модуль ЧИСТЫЙ: ни Tk, ни файлов, ни модели — только расчёт карточек.
# Читает и пишет их profile_store.py (рядом с ошибками в файле прогресса).
# =========================================================

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, List, Optional, Tuple

import config

LEARNED = 5                       # с этой ступени слово «выучено»
MISS_DELAY_DAYS = 1               # промах → спросить завтра
# Индекс = уровень. 0 дней у новой карточки: её можно спросить уже сегодня.
INTERVALS_DAYS = (0, 1, 3, 7, 21, None)

_CYR_RE = re.compile(r"[\u0400-\u04FF]")
_NUMBERING_RE = re.compile(r"^\s*(\d+[.)]|[-*\u2022])\s*")
# Чем в строке переводчика отделено значение от примера («key — пример»).
_SEPARATORS = ("\u2014", "\u2013", " - ", ":")


# ---------------------------------------------------------
# Даты (всё храним строками «ГГГГ-ММ-ДД», чтобы файл читался глазами)
# ---------------------------------------------------------
def _as_date(value=None) -> date:
    """Дата из строки/date/datetime; None или мусор → сегодня."""
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return date.today()
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return date.today()


def _iso(day: date) -> str:
    return day.isoformat()


def today_text() -> str:
    """Сегодняшняя дата строкой (для тестов можно передать свою)."""
    return _iso(date.today())


# ---------------------------------------------------------
# Разбор ответа переводчика
# ---------------------------------------------------------
def parse_line(line) -> Optional[Tuple[str, str]]:
    """Строка «key — Open the door with this key.» → (значение, пример).

    Возвращает None, если строку нельзя считать переводом (пусто, кириллица).
    """
    text = _NUMBERING_RE.sub("", str(line or "")).strip()
    text = text.strip('"').strip("\u201c\u201d").strip("'").strip()
    if not text or _CYR_RE.search(text):
        return None
    en, example = text, ""
    for sep in _SEPARATORS:
        if sep in text:
            left, right = text.split(sep, 1)
            left = left.strip().strip('"').strip("'").strip()
            right = right.strip().strip('"').strip("'").strip()
            if left:
                en, example = left, right
                break
    if not en or _CYR_RE.search(en):
        return None
    return en, example


def parse_meanings(lines) -> List[dict]:
    """Список строк переводчика → [{"en": …, "example": …}, …] без повторов."""
    out: List[dict] = []
    seen = set()
    for line in (lines or []):
        if isinstance(line, dict):
            en = str(line.get("en") or "").strip()
            example = str(line.get("example") or "").strip()
            parsed = (en, example) if en else None
        else:
            parsed = parse_line(line)
        if not parsed:
            continue
        en, example = parsed
        key = en.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"en": en, "example": example})
    return out


def card_key(word, en) -> str:
    """Ключ уникальности карточки: одно слово + одно значение."""
    return "%s|%s" % (str(word or "").strip().lower(),
                      str(en or "").strip().lower())


# ---------------------------------------------------------
# Карточки
# ---------------------------------------------------------
def new_card(word, en, example="", today=None) -> dict:
    """Новая карточка уровня 0 (её можно спросить уже сегодня)."""
    day = _as_date(today)
    return {
        "word": str(word or "").strip(),
        "en": str(en or "").strip(),
        "example": str(example or "").strip(),
        "level": 0,
        "created": _iso(day),
        "last_ok": None,
        "next_due": _iso(day),
        "hits": 0,
        "misses": 0,
    }


def add_meanings(cards, word, meanings, today=None, limit=None) -> List[dict]:
    """Добавить значения слова в список карточек → список НОВЫХ карточек.

    • дубликаты (то же слово + то же значение) не добавляются — поэтому
      уже выученное слово повторным переводом НЕ сбрасывается: для него
      просто нет новой карточки;
    • meanings — строки переводчика («key — пример») или готовые словари.
    """
    parsed = parse_meanings(meanings)
    existing = set()
    for card in (cards or []):
        if isinstance(card, dict):
            existing.add(card_key(card.get("word"), card.get("en")))
    added: List[dict] = []
    for item in parsed:
        en = str(item.get("en") or "").strip()
        if not en:
            continue
        key = card_key(word, en)
        if key in existing:
            continue
        cards.append(new_card(word, en, item.get("example") or "", today))
        existing.add(key)
        added.append(cards[-1])
    if added:
        trim(cards, limit)
    return added


def find_card(cards, word, en) -> Optional[dict]:
    """Карточка по паре «слово + значение» (или None)."""
    key = card_key(word, en)
    for card in (cards or []):
        if isinstance(card, dict) and card_key(card.get("word"), card.get("en")) == key:
            return card
    return None


def level_of(card) -> int:
    """Уровень карточки, приведённый к 0..5 (битые данные не ломают работу)."""
    try:
        level = int((card or {}).get("level", 0))
    except (TypeError, ValueError):
        level = 0
    return max(0, min(LEARNED, level))


def is_learned(card) -> bool:
    """Слово выучено — больше не спрашиваем."""
    return level_of(card) >= LEARNED


def interval_days(level) -> Optional[int]:
    """Сколько дней ждать до следующего вопроса (None — больше не спрашиваем)."""
    return INTERVALS_DAYS[level_of({"level": level})]


def next_due_text(level, base=None) -> Optional[str]:
    """Дата следующего вопроса для уровня (None — «выучено»)."""
    step = interval_days(level)
    if step is None:
        return None
    return _iso(_as_date(base) + timedelta(days=step))


# ---------------------------------------------------------
# Ответы ученика: лестница вверх и вниз
# ---------------------------------------------------------
def register_success(card, today=None):
    """Удачный ответ (вердикт GOOD): +1 к уровню и новая дата вопроса."""
    if not isinstance(card, dict):
        return None
    day = _as_date(today)
    level = min(LEARNED, level_of(card) + 1)
    card["level"] = level
    card["last_ok"] = _iso(day)
    card["hits"] = _int(card.get("hits")) + 1
    card["next_due"] = next_due_text(level, day)
    return card


def register_miss(card, today=None):
    """Промах («Почти»/«Попробуй»): уровень НЕ меняем, спросить завтра.

    Решение ученика 53 (27.10.2026): промах только переносит вопрос на
    завтра (MISS_DELAY_DAYS += 1 день). Причина — осечка распознавания не
    должна отбрасывать слово назад. Уровень двигает ТОЛЬКО удачный ответ.
    """
    if not isinstance(card, dict):
        return None
    day = _as_date(today)
    card["misses"] = _int(card.get("misses")) + 1
    card["next_due"] = _iso(day + timedelta(days=MISS_DELAY_DAYS))
    return card


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------
# Что спрашивать сегодня
# ---------------------------------------------------------
def _due_date(card) -> date:
    """Дата «пора спросить» из карточки (пусто/мусор → «давно пора»)."""
    text = str((card or {}).get("next_due") or "").strip()
    if not text:
        return date.min
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return date.min


def due_cards(cards, today=None, limit=None) -> List[dict]:
    """Карточки, которые пора спросить: сначала самые «просроченные».

    limit — сколько слов за один заход (по умолчанию config.VOCAB_SESSION_SIZE).
    """
    day = _as_date(today)
    pairs = []
    for card in (cards or []):
        if not isinstance(card, dict) or is_learned(card):
            continue
        if not str(card.get("en") or "").strip():
            continue
        due = _due_date(card)
        if due <= day:
            # порядок: дата → уровень → когда заведена (стабильно и понятно)
            pairs.append((due, level_of(card), str(card.get("created") or ""), card))
    pairs.sort(key=lambda item: item[:3])
    out = [item[3] for item in pairs]
    if limit is None:
        limit = session_size()
    if limit:
        out = out[:int(limit)]
    return out


def session_size() -> int:
    """Сколько слов за один заход (config.VOCAB_SESSION_SIZE)."""
    try:
        return max(1, int(getattr(config, "VOCAB_SESSION_SIZE", 5)))
    except (TypeError, ValueError):
        return 5


def stats(cards, today=None) -> dict:
    """Сводка для вкладки «Профиль»: всего / к повторению / выучено."""
    cards = [c for c in (cards or []) if isinstance(c, dict)]
    learned = sum(1 for c in cards if is_learned(c))
    return {
        "total": len(cards),
        "learned": learned,
        "learning": len(cards) - learned,
        "due": len(due_cards(cards, today, limit=0)),
    }


# ---------------------------------------------------------
# Слова для промпта (этап C): вплести в разговор 1-2 слова ученика
# ---------------------------------------------------------
# Джейн получает НЕБОЛЬШОЙ список слов ученика и может естественно
# использовать их в ответе или попросить ученика их употребить. Это не
# экзамен: модель сама решает, уместно ли слово в текущей теме.
def prompt_words(cards, limit=None) -> List[str]:
    """Слова для необязательного блока промпта: ["ключ — key", …].

    Берём «трудные» слова: сначала нижние уровни, потом те, где больше
    промахов, потом давно не спрашивали. Выученные (5) не берём — их
    повторять не нужно, а в разговоре они уже не тянут вниз.
    """
    if limit is None:
        try:
            import config
            limit = int(getattr(config, "VOCAB_PROMPT_LIMIT", 4))
        except Exception:
            limit = 4
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 4

    prepared = []
    for card in (cards or []):
        if not isinstance(card, dict) or is_learned(card):
            continue
        word = str(card.get("word") or "").strip()
        en = str(card.get("en") or "").strip()
        if not word or not en:
            continue
        prepared.append((level_of(card), -_int(card.get("misses")), _due_date(card),
                         "%s — %s" % (word, en)))
    prepared.sort(key=lambda item: item[:3])
    return [item[3] for item in prepared[:limit]]


# ---------------------------------------------------------
# Окно повторения (этап B): задание, эталон, «сегодня уже было»
# ---------------------------------------------------------
# Задание для ученика: русское слово + английский пример с ПРОПУСКОМ
# («Open the door with this ___.»). Пропуск не выдумываем: если в примере
# нет самого слова (переводчик дал другую форму) — примера не показываем,
# честнее спросить одно слово.
_WORD_IN_TEXT_RE = re.compile(r"[A-Za-z']+")


def word_forms(en) -> List[str]:
    """Формы английского слова для поиска в примере (key → keys, keyed…)."""
    text = str(en or "").strip().lower()
    if not text:
        return []
    if " " in text:            # «look for» — ищем фразу целиком, форм не делаем
        return [text]
    forms = {text, text + "s", text + "es", text + "ed", text + "d", text + "ing"}
    if text.endswith("e"):
        forms.add(text[:-1] + "ing")
    if text.endswith("y") and len(text) > 1:
        forms.add(text[:-1] + "ies")
        forms.add(text[:-1] + "ied")
    # длинные формы первыми: «keys» должно проверяться раньше «key»
    return sorted(forms, key=len, reverse=True)


def example_with_gap(card) -> str:
    """Пример с пропуском вместо слова: «Open the door with this ___.»

    Пустая строка — если примера нет или в нём не нашлось само слово
    (тогда окно покажет только русское слово, без выдуманного пропуска).
    """
    card = card or {}
    example = str(card.get("example") or "").strip()
    if not example:
        return ""
    forms = word_forms(card.get("en"))
    if not forms:
        return ""
    low = example.lower()
    for form in forms:
        if " " in form:                       # значение из нескольких слов
            index = low.find(form)
            if index >= 0:
                return example[:index] + "___" + example[index + len(form):]
            continue
        for match in _WORD_IN_TEXT_RE.finditer(low):
            if match.group(0) == form:
                start, end = match.span()
                return example[:start] + "___" + example[end:]
    return ""


def reference_texts(card) -> List[str]:
    """Что ученик может произнести: пример и само слово.

    Сверяем с ОБОИМИ: «key» и «Open the door with this key.» — оба правильные
    ответы. Если примером сверять только фразу, короткий ответ «key» выглядел
    бы как «сказал своё» и вердикт не показался бы.
    """
    card = card or {}
    out: List[str] = []
    example = str(card.get("example") or "").strip()
    en = str(card.get("en") or "").strip()
    if example:
        out.append(example)
    if en and en.lower() not in [text.lower() for text in out]:
        out.append(en)
    return out




# ---------------------------------------------------------
# Синонимы: любые равнозначные английские ответы — верные
# ---------------------------------------------------------
# Решение ученика 24.10.2026: на карточку «привет» правильны и «Hey», и
# «Hi», и «Hello». Раньше сверка была буквальная, и живой ответ «hello»
# считался «сказал своё» (замерено: Hey ← hello = unrelated, 0.045).
#
# Таблица ЗАКРЫТАЯ и ручная — принципиально: синонимы даёт человек, а не
# модель (иначе программа начнёт принимать что попало и «выучит» неверное).
# Слева — русское слово карточки, справа — равнозначные английские ответы.
# Американский вариант первым; британские формы намеренно не добавляем.
SYNONYM_GROUPS = (
    ("привет", ("hi", "hello", "hey")),
    ("здравствуй", ("hello", "hi")),
    ("здравствуйте", ("hello", "hi")),
    ("пока", ("bye", "goodbye", "see you", "later")),
    ("до свидания", ("goodbye", "bye", "see you")),
    ("спасибо", ("thanks", "thank you")),
    ("извините", ("sorry", "excuse me")),
    ("прости", ("sorry", "excuse me")),
    ("да", ("yes", "yeah", "yep", "sure")),
    ("нет", ("no", "nope")),
    ("хорошо", ("okay", "ok", "all right", "fine")),
    ("конечно", ("of course", "sure", "certainly")),
    ("как дела", ("how are you", "how's it going", "how are you doing")),
    ("как ты", ("how are you", "how's it going")),
    ("я не понимаю", ("i don't understand", "i don't get it")),
    ("я не знаю", ("i don't know", "i have no idea")),
    ("я устал", ("i'm tired", "i am tired")),
    ("я голоден", ("i'm hungry", "i am hungry")),
    ("доброе утро", ("good morning", "morning")),
    ("добрый день", ("good afternoon", "good day")),
    ("добрый вечер", ("good evening",)),
    ("спокойной ночи", ("good night", "night")),
    ("мама", ("mom", "mommy", "mother")),
    ("папа", ("dad", "daddy", "father")),
    ("ребёнок", ("kid", "child")),
    ("дети", ("kids", "children")),
    ("дом", ("house", "home")),
    ("квартира", ("apartment",)),
    ("машина", ("car", "automobile")),
    ("магазин", ("store", "shop")),
    ("фильм", ("movie", "film")),
    ("отпуск", ("vacation", "holiday")),
    ("работа", ("work", "job")),
    ("деньги", ("money", "cash")),
    ("туалет", ("bathroom", "restroom")),
    ("лифт", ("elevator",)),
    ("большой", ("big", "large")),
    ("маленький", ("small", "little")),
    ("быстрый", ("fast", "quick")),
    ("красивый", ("beautiful", "pretty", "nice")),
    ("начинать", ("start", "begin")),
    ("заканчивать", ("finish", "end")),
    ("разговаривать", ("talk", "speak")),
    ("смотреть", ("watch", "look")),
    ("слушать", ("listen",)),
    ("есть", ("eat", "have")),
)


def _plain(text) -> str:
    """Текст для сравнения: нижний регистр, только буквы, цифры, пробелы."""
    low = str(text or "").lower()
    for bad in ("\u2019", "\u0060", "\u00b4"):
        low = low.replace(bad, "'")
    out = []
    for ch in low:
        out.append(ch if (ch.isalnum() or ch == "'" or ch == " ") else " ")
    return " ".join("".join(out).split())


def same_text(left, right) -> bool:
    """Одинаковый ли текст (без регистра, знаков препинания, лишних пробелов)."""
    return _plain(left) == _plain(right)


def alternatives(card) -> List[str]:
    """Другие равнозначные английские ответы на карточку (синонимы).

    Группу ищем по русскому слову карточки ИЛИ по её английскому значению —
    поэтому старое слово «привет → Hey» тоже принимает «hi» и «hello», хотя
    таблицу завели позже. Своё собственное значение в список не попадает.
    """
    card = card or {}
    ru = _plain(card.get("word"))
    en = _plain(card.get("en"))
    if not en:
        return []
    out: List[str] = []
    for russian, english in SYNONYM_GROUPS:
        plain_ru = _plain(russian)
        plain_en = [_plain(item) for item in english]
        if ru != plain_ru and en not in plain_en:
            continue
        for item, plain in zip(english, plain_en):
            if plain == en or plain in out:
                continue
            out.append(item)
    return out

def session_today(value, today=None) -> bool:
    """Был ли заход повторения уже сегодня (дата из поля профиля).

    Мусор и пустое значение → False: лучше спросить лишний раз, чем молча
    потерять повторение из-за испорченного поля.
    """
    text = str(value or "").strip()
    if not text:
        return False
    try:
        day = datetime.fromisoformat(text).date()
    except ValueError:
        return False
    return day == _as_date(today)


# ---------------------------------------------------------
# Служебное
# ---------------------------------------------------------
def trim(cards, limit=None) -> list:
    """Ограничить число карточек (защита от бесконечного роста файла).

    Первыми уходят ВЫУЧЕННЫЕ (старые), слова в учёбе остаются.
    """
    limit = _int(limit) or _int(getattr(config, "VOCAB_MAX_CARDS", 500)) or 500
    if len(cards) <= limit:
        return cards
    order = sorted(cards, key=lambda c: (1 if is_learned(c) else 0,
                                         str((c or {}).get("created") or "")))
    cards[:] = order[:limit]
    return cards
