"""GLOSSARY.PY — подсказки-переводы к словам в репликах Вербота.

Зачем: ученик наводит курсор на английское слово в чате и видит короткий
русский перевод. Устойчивые выражения (look forward to, nice to meet you)
переводятся ОДНИМ куском по смыслу, а не тремя словами по отдельности.

Как устроено (производительность — главное):
  * модель зовётся ТОЛЬКО из prime() — один раз на реплику, в фоне;
  * наведение курсора модель не трогает вообще: lookup() читает словарь
    в памяти (микросекунды);
  * всё выученное лежит в data/glossary.json и живёт между занятиями:
    повторная реплика стоит ноль запросов к модели;
  * модуль без Tk, без потоков: очередь и «паузы» — забота вызывающего кода.

Замер 25.10.2026 (Gemma-4-E4B, 10 реплик): разбор реплики 2.9–10.1 с
(среднее 5.0 с), 8 из 10 ответов годны сразу, 1 из 5 требует повтора из-за
битого JSON. Жёсткая схема (json_schema) даёт 15.8–25.4 с — ОТКАЗ, слишком
медленно.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading

import config

_log = logging.getLogger(__name__)

GLOSSARY_PATH = os.path.join(config.BASE_DIR, "data", "glossary.json")

# Сколько слов максимум может занимать одно устойчивое выражение.
# Замер 25.10.2026: при свободе модель склеивала «look forward to seeing you
# there» (6 слов) и «your umbrella» — подсказка на слове показывала целую
# фразу. Поэтому максимум 4 слова и запрет притяжательных ниже.
MAX_PHRASE_WORDS = 4

# Притяжательное + существительное — НЕ устойчивое выражение ("your umbrella").
_POSSESSIVE = {"my", "your", "his", "her", "its", "our", "their",
              "mine", "yours", "ours", "theirs"}

# Токен: буквы + внутренний апостроф (don't, I'm, let's, o'clock).
# Русские буквы сюда НЕ попадают: кириллицу в чате не переводим.
WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*")

# Просьба к модели. Отдельный мини-промпт: базовый промпт урока не тронут.
_SYSTEM = (
    "You build a bilingual glossary for a Russian-speaking learner of English "
    "(level A2).\n"
    'Return ONLY compact JSON on one line: '
    '{"items":[{"en":"word","ru":"перевод","phrase":false}]}\n'
    "Rules:\n"
    "1. Include EVERY word of the sentence, in order of appearance (repeats once).\n"
    "2. 'ru' is a SHORT literal translation of that word, 1-2 words, no "
    "explanations, in Russian.\n"
    "3. If words form a set phrase, idiom or phrasal verb (look forward to, "
    "nice to meet you, how are you, I'd rather, as soon as, well done, "
    "take the bus), make ONE item for that phrase ONLY: en = exactly those "
    "words, phrase = true, ru = its MEANING (look forward to -> с нетерпением "
    "ждать).\n"+
    "3a. A phrase is at most 4 words. Never glue the rest of the sentence to "
    "it (NOT \"look forward to seeing you there\").\n"+
    "3b. A possessive or article with a noun is NOT a phrase (your umbrella = "
    "two separate words).\n"
    "4. Do NOT add separate items for words already inside a phrase item.\n"
    "5. Contractions (I'm, don't, let's) are ONE word.\n"
    "6. No markdown, no comments, no extra keys."
)

_MAX_TOKENS = 1200          # замер: 700 мало — JSON обрывался
_TEMPERATURE = 0.2


# ---------------------------------------------------------
# Токены и ключи
# ---------------------------------------------------------
def normalize(word: str) -> str:
    """Ключ словаря: нижний регистр, «ёлочка» → обычный апостроф, без знаков."""
    text = str(word or "").replace("\u2019", "'").replace("\u02bc", "'")
    return text.strip().strip(".,!?;:\"'()[]{}—–-").lower()


def tokenize(sentence: str) -> list:
    """Список слов с позициями: [{"word","key","start","end"}, …].

    Позиции — в символах строки (для Tk это «N.0 + индекс»).
    """
    out = []
    for m in WORD_RE.finditer(str(sentence or "")):
        key = normalize(m.group(0))
        if key:
            out.append({"word": m.group(0), "key": key,
                        "start": m.start(), "end": m.end()})
    return out


def _locate(sentence: str, index: int):
    """(все токены, номер токена под символом index | None)."""
    tokens = tokenize(sentence)
    for pos, token in enumerate(tokens):
        if token["start"] <= index < token["end"]:
            return tokens, pos
    return tokens, None


def word_at(sentence: str, index: int):
    """Токен под символом index или None (пробел, знак, кириллица)."""
    tokens, pos = _locate(sentence, index)
    return None if pos is None else tokens[pos]


# ---------------------------------------------------------
# Словарь
# ---------------------------------------------------------
class Glossary:
    """Словарь переводов: слова + устойчивые выражения, с файловым кэшем."""

    def __init__(self, llm=None, path: str = None, autosave: bool = True) -> None:
        self.llm = llm
        self.path = path or GLOSSARY_PATH
        self.autosave = autosave
        self.words = {}          # key -> ru
        self.phrases = {}        # (key, key, …) -> ru
        self.stats = {"requests": 0, "failed": 0, "retries": 0,
                      "hits": 0, "misses": 0, "rejected": 0}
        self._lock = threading.Lock()
        self.load()

    # ---------- файл ----------
    def load(self) -> bool:
        """Читает кэш с диска. Битый/отсутствующий файл — не ошибка."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False
        words = data.get("words") or {}
        phrases = data.get("phrases") or {}
        self.words = {str(k): str(v) for k, v in words.items() if k and v}
        self.phrases = {}
        if isinstance(phrases, dict):
            for key, value in phrases.items():
                parts = tuple(p for p in str(key).split("|") if p)
                if len(parts) >= 2 and value:
                    self.phrases[parts] = str(value)
        return True

    def save(self) -> bool:
        """Пишет кэш на диск (атомарно: temp + replace)."""
        payload = {
            "words": dict(sorted(self.words.items())),
            "phrases": {"|".join(k): v
                        for k, v in sorted(self.phrases.items())},
        }
        folder = os.path.dirname(self.path)
        try:
            if folder:
                os.makedirs(folder, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            return True
        except OSError as exc:                       # noqa: BLE001
            _log.warning("Глоссарий: не удалось сохранить (%s)", exc)
            return False

    # ---------- чтение (дёшево, без модели) ----------
    def lookup(self, sentence: str, index: int):
        """Что показать при наведении на символ index.

        Возвращает {"en","ru","start","end","phrase"} или None.
        Модель НЕ вызывается: только словарь в памяти.
        """
        tokens, pos = _locate(sentence, index)
        if pos is None:
            return None
        token = tokens[pos]

        # 1) устойчивое выражение — самое длинное совпадение
        longest = min(MAX_PHRASE_WORDS, len(tokens) - pos)
        for size in range(longest, 1, -1):
            keys = tuple(t["key"] for t in tokens[pos:pos + size])
            ru = self.phrases.get(keys)
            if ru:
                self.stats["hits"] += 1
                return {"en": " ".join(t["word"] for t in tokens[pos:pos + size]),
                        "ru": ru, "phrase": True,
                        "start": tokens[pos]["start"],
                        "end": tokens[pos + size - 1]["end"]}

        # 2) отдельное слово
        ru = self.words.get(token["key"])
        if ru:
            self.stats["hits"] += 1
            return {"en": token["word"], "ru": ru, "phrase": False,
                    "start": token["start"], "end": token["end"]}

        # 3) слово входит в выражение ГЛУБЖЕ (курсор на 2-м слове фразы)
        for keys, value in self.phrases.items():
            for offset in range(len(keys)):
                if pos - offset >= 0 and tuple(
                        t["key"] for t in tokens[pos - offset:pos - offset + len(keys)]
                ) == keys:
                    self.stats["hits"] += 1
                    first, last = pos - offset, pos - offset + len(keys) - 1
                    return {"en": " ".join(t["word"] for t in tokens[first:last + 1]),
                            "ru": value, "phrase": True,
                            "start": tokens[first]["start"],
                            "end": tokens[last]["end"]}
        self.stats["misses"] += 1
        return None

    def known(self, sentence: str) -> bool:
        """Все слова реплики уже есть в словаре? Тогда модель не нужна."""
        for token in tokenize(sentence):
            if token["key"] in self.words:
                continue
            if any(token["key"] in keys for keys in self.phrases):
                continue
            return False
        return True

    # ---------- запись (дорого: одна реплика = один запрос) ----------
    def prime(self, sentence: str, timeout: int = 120):
        """Разбирает реплику моделью и кладёт переводы в словарь.

        Возвращает (ok, добавлено_пар | причина). Один повтор при битом JSON —
        замер показал, что так бывает на ~1 реплике из 5.
        """
        text = str(sentence or "").strip()
        if not text or not tokenize(text):
            return False, "нечего разбирать"
        if self.known(text):
            return True, 0
        if self.llm is None:
            return False, "нет модели"

        with self._lock:
            self.stats["requests"] += 1
        messages = [{"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": "Sentence: " + text}]
        items = []
        for attempt in (1, 2):
            try:
                ok, raw = self.llm.complete(
                    messages, max_tokens=_MAX_TOKENS,
                    temperature=_TEMPERATURE, timeout=timeout)
            except Exception as exc:                 # noqa: BLE001
                _log.warning("Глоссарий: модель недоступна (%s)", exc)
                return False, "модель недоступна"
            if not ok:
                with self._lock:
                    self.stats["failed"] += 1
                return False, str(raw)[:120]
            items = parse_items(raw)
            if items:
                break
            if attempt == 1:
                with self._lock:
                    self.stats["retries"] += 1

        if not items:
            with self._lock:
                self.stats["failed"] += 1
            return False, "не разобрал JSON"

        added = self.add(items)
        if added and self.autosave:
            self.save()
        return True, added

    def add(self, items) -> int:
        """Кладёт разобранные пары в словарь. Возвращает число новых пар."""
        added = 0
        for item in items:
            en = str(item.get("en") or "").strip()
            ru = str(item.get("ru") or "").strip()
            if not en or not ru:
                continue
            keys = tuple(t["key"] for t in tokenize(en))
            if not keys:
                continue
            with self._lock:
                if len(keys) == 1:
                    if self.words.get(keys[0]) == ru:
                        continue
                    self.words[keys[0]] = ru
                    added += 1
                else:
                    if len(keys) > MAX_PHRASE_WORDS or any(
                            k in _POSSESSIVE for k in keys):
                        # мы уже под self._lock: вложенный захват = самоблокировка
                        self.stats["rejected"] += 1
                        continue
                    if self.phrases.get(keys) == ru:
                        continue
                    self.phrases[keys] = ru
                    added += 1
        return added


# ---------------------------------------------------------
# Разбор ответа модели
# ---------------------------------------------------------
def parse_items(raw: str) -> list:
    """Достаёт список пар из ответа модели. Битый JSON → [].

    Модель иногда добавляет ```json, пояснения или рвёт строку — поэтому
    сначала пробуем как есть, потом вырезаем {...}.
    """
    text = str(raw or "").strip()
    if not text:
        return []
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    data = None
    try:
        data = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            chunk = match.group(0)
            try:
                data = json.loads(chunk)
            except ValueError:
                data = None
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    clean = []
    for item in items:
        if isinstance(item, dict) and item.get("en") and item.get("ru"):
            clean.append({"en": str(item["en"]), "ru": str(item["ru"]),
                          "phrase": bool(item.get("phrase"))})
    return clean
