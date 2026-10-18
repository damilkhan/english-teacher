# -*- coding: utf-8 -*-
# =========================================================
# TRANSLATE.PY — перевод реплики ученика RU → EN (для подсказки)
# =========================================================
# Зачем: ученик не знает, как сказать фразу по-английски, и пишет
# по-русски. Приложение показывает ПОДСКАЗКУ с английским вариантом —
# ученик сам решает: переписать, произнести вслух или отправить как есть.
#
# Почему переводим НАШЕЙ моделью, а не отдельным переводчиком:
#   * модель уже загружена — замер дал ~0.3 с на фразу (не «нагрузка»);
#   * она знает уровень ученика, поэтому фразы звучат естественно
#     (Argos перевёл бы буквально);
#   * ноль новых зависимостей и памяти (Argos — ещё ~200 МБ моделей).
#
# Ускорители:
#   * КЭШ: одинаковые фразы не переводятся второй раз;
#   * ФРАЗНИК: частые фразы A0 берутся из готового словаря — там, где
#     ошибиться нельзя, модель не спрашиваем вообще.
#
# Модуль чистый: ни Tk, ни потоков — вызывается из фонового потока.
# =========================================================

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from typing import Optional, Tuple

_log = logging.getLogger(__name__)

# Сколько переводов держим в памяти.
CACHE_LIMIT = 200

# Инструкция модели: короткий естественный английский, без пояснений.
SYSTEM_PROMPT = (
    "You translate a Russian sentence into natural spoken English for an "
    "A0-A1 learner. Keep it simple and friendly, the way a teacher would say "
    "it. Reply with the English sentence ONLY: no explanations, no quotes, "
    "no Russian, no notes. If the input is already English, repeat it as is."
)

_CYR_RE = re.compile(r"[А-Яа-яЁё]")

# Инструкция для ОДНОГО СЛОВА: до трёх значений с примером — у слова
# обычно несколько смыслов («ключ» — key / wrench), и без примеров
# ученик не поймёт, какое значение ему нужно.
WORD_SYSTEM_PROMPT = (
    "The user gives ONE Russian word. Give up to {n} DIFFERENT English words "
    "for its DIFFERENT meanings — never repeat the same English word twice. "
    "Most frequent meaning first. Format, one meaning per line:\n"
    "    english word — short example sentence showing THIS meaning\n"
    "Rules:"
    "\n- The example must make the meaning clear (not «This is a key»)."
    "\n- Examples: 4-7 words, beginner level, natural English."
    "\n- No numbering, no bullets, no Russian text, no explanations."
    "\n- If the word has only ONE common meaning, return exactly one line."
    "\n- If a meaning is a part of speech or a phrase, still give the word "
    "and one example."
)

# Сколько значений показываем максимум.
WORD_MEANINGS = 3

# Частые фразы: мгновенно и без ошибок. Ключ — фраза в нижнем регистре
# без знаков препинания по краям.
PHRASES = {
    "привет": "Hi!",
    "здравствуй": "Hello!",
    "спасибо": "Thank you!",
    "пожалуйста": "Please.",
    "не за что": "You're welcome.",
    "как дела": "How are you?",
    "как ты": "How are you?",
    "меня зовут": "My name is",
    "я не понимаю": "I don't understand.",
    "я не знаю": "I don't know.",
    "повтори пожалуйста": "Can you repeat that, please?",
    "можно повторить": "Can you say it again?",
    "помедленнее": "Slower, please.",
    "как сказать": "How do you say",
    "что это значит": "What does it mean?",
    "я устал": "I'm tired.",
    "я голоден": "I'm hungry.",
    "да": "Yes.",
    "нет": "No.",
    "хорошо": "Okay.",
    "конечно": "Of course.",
    "извините": "Sorry.",
    "прости": "I'm sorry.",
    "до свидания": "Goodbye!",
    "пока": "See you!",
    "доброе утро": "Good morning!",
    "добрый день": "Good afternoon!",
    "добрый вечер": "Good evening!",
    "спокойной ночи": "Good night!",
}


def has_cyrillic(text: str) -> bool:
    """Есть ли в тексте русские буквы (значит, нужен перевод)."""
    return bool(_CYR_RE.search(str(text or "")))


def _normalize(text: str) -> str:
    """Ключ кэша/фразника: нижний регистр, без лишних знаков и пробелов."""
    low = str(text or "").strip().lower()
    low = low.strip(" .,!?…;:—-\u00ab\u00bb\"'")
    return re.sub(r"\s+", " ", low)


def phrase_lookup(text: str) -> Optional[str]:
    """Готовая фраза из словаря (или None)."""
    return PHRASES.get(_normalize(text))


class Translator:
    """Перевод RU → EN через уже загруженную модель, с кэшем и фразником."""

    def __init__(self, llm, max_tokens: int = 90, cache_limit: int = CACHE_LIMIT) -> None:
        self.llm = llm
        self.max_tokens = int(max_tokens)
        self.cache_limit = max(1, int(cache_limit))
        self._cache: "OrderedDict[str, str]" = OrderedDict()
        self.stats = {"hits": 0, "phrase": 0, "model": 0, "failed": 0}

    # -----------------------------------------------------
    def translate(self, text: str) -> Tuple[bool, str]:
        """Перевести фразу. Возвращает (ok, перевод | причина сбоя).

        • уже по-английски (нет кириллицы) → отдаём как есть;
        • есть в фразнике/кэше → мгновенно, без модели;
        • иначе → один короткий вызов модели.
        """
        raw = str(text or "").strip()
        if not raw:
            return False, "пустая фраза"
        if not has_cyrillic(raw):
            self.stats["hits"] += 1
            return True, raw                      # уже английский

        key = _normalize(raw)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            self.stats["hits"] += 1
            return True, cached

        phrase = PHRASES.get(key)
        if phrase:
            self._remember(key, phrase)
            self.stats["phrase"] += 1
            return True, phrase

        ok, result = self._ask_model(raw)
        if not ok:
            self.stats["failed"] += 1
            return False, result
        self._remember(key, result)
        self.stats["model"] += 1
        return True, result

    # -----------------------------------------------------
    def translate_word(self, text: str) -> Tuple[bool, list]:
        """Перевод ОДНОГО слова: до трёх значений с примерами.

        Возвращает (ok, [строки]) — каждая строка вида
        «key — Open the door with this key.».
        """
        raw = str(text or "").strip()
        if not raw:
            return False, ["пустое слово"]

        key = "word:" + _normalize(raw)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            self.stats["hits"] += 1
            return True, list(cached)

        if self.llm is None:
            return False, ["нет модели"]
        messages = [
            {"role": "system",
             "content": WORD_SYSTEM_PROMPT.format(n=WORD_MEANINGS)},
            {"role": "user", "content": raw},
        ]
        try:
            ok, answer = self.llm.complete(
                messages, max_tokens=160, temperature=0.0)
        except Exception as exc:                 # noqa: BLE001
            _log.warning("Перевод слова: модель недоступна (%s)", exc)
            return False, ["модель недоступна"]
        if not ok:
            self.stats["failed"] += 1
            return False, [_short_error(answer)]

        lines = _clean_word_lines(answer)
        if not lines:
            self.stats["failed"] += 1
            return False, ["не удалось перевести"]
        self._remember(key, lines)
        self.stats["model"] += 1
        return True, lines

    # -----------------------------------------------------
    def _ask_model(self, text: str) -> Tuple[bool, str]:
        """Один короткий запрос к модели. Ошибки → (False, причина)."""
        if self.llm is None:
            return False, "нет модели"
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}]
        try:
            ok, raw = self.llm.complete(
                messages, max_tokens=self.max_tokens, temperature=0.0)
        except Exception as exc:                 # noqa: BLE001
            _log.warning("Перевод: модель недоступна (%s)", exc)
            return False, "модель недоступна"
        if not ok:
            return False, _short_error(raw)

        clean = _clean_answer(raw)
        if not clean:
            return False, "пустой перевод"
        return True, clean

    def _remember(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_limit:
            self._cache.popitem(last=False)

    def clear_cache(self) -> None:
        self._cache.clear()


def _short_error(value) -> str:
    """Короткая причина сбоя (для строки-подсказки, а не для лога).

    Клиент отдаёт текст исключения целиком (иногда на несколько строк:
    «Connection error: HTTPConnectionPool(host=...) ...»). Ученику это
    ничего не говорит — превращаем в понятную фразу.
    """
    text = str(value or "").strip()
    low = text.lower()
    if not text:
        return "ошибка модели"
    if ("connection" in low or "refused" in low or "max retries" in low
            or "newconnectionerror" in low or "timeout" in low):
        return "модель не отвечает"
    if "403" in text or "401" in low:
        return "модель отклонила запрос"
    return text.splitlines()[0][:70]


def is_single_word(text: str) -> bool:
    """Одно слово (без пробелов) — значит, нужен словарный перевод."""
    body = str(text or "").strip().strip(".,!?…;:—-«»\"'()")
    if not body:
        return False
    return " " not in body and len(body) <= 24


def _clean_word_lines(text: str) -> list:
    """Разобрать ответ модели на строки «слово — пример» (до 3)."""
    out = []
    for line in str(text or "").splitlines():
        clean = line.strip()
        if not clean:
            continue
        # нумерацию и маркеры убираем
        clean = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", clean).strip()
        clean = clean.strip('"').strip()
        if not clean:
            continue
        # если модель вставила кириллицу — это пояснение, не перевод
        if has_cyrillic(clean):
            continue
        out.append(clean)
        if len(out) >= WORD_MEANINGS:
            break
    return out


def _clean_answer(text: str) -> str:
    """Убрать кавычки, пояснения и пустые строки из ответа модели."""
    out = str(text or "").strip()
    if not out:
        return ""
    # модель иногда добавляет «Here is:» или пояснение в скобках
    out = out.split("\n")[0].strip()
    out = re.sub(r"^(here('s| is)[^:]*:|translation[^:]*:)\s*", "", out,
                 flags=re.IGNORECASE)
    out = out.strip().strip('"').strip("\u201c\u201d").strip("'").strip()
    out = out.strip()
    # если в переводе осталась кириллица — скорее всего это пояснение
    if has_cyrillic(out):
        return ""
    return out
