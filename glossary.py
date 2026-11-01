"""GLOSSARY.PY — подсказки-переводы КУСКАМИ ПО СМЫСЛУ (03.11.2026).

Зачем переделали. Пословный перевод давал бред: в реплике «Would you like a
table by the window?» наведение на слово показывало «Было бы ты хотеть а стол
у окна (определенный) окно». Решение ученика 03.11.2026: переводить КУСКАМИ
ПО СМЫСЛУ — [Would you like] хотели бы вы [a table] столик [by the window] у
окна. Длина куска НЕ ограничена: её решает смысл, а не число слов.

Как устроено (производительность — главное):
  * модель режет реплику на куски и переводит каждый кусок ЦЕЛИКОМ;
  * КОД проверяет, что куски покрывают ВСЕ слова реплики по порядку. Не
    покрыли → один повтор, потом отказ: лучше пусто, чем бред;
  * наведение курсора модель не трогает вообще: lookup() читает готовый
    разбор из памяти (микросекунды);
  * разбор лежит в data/glossary.json и живёт между занятиями: повторная
    реплика стоит ноль запросов;
  * пока реплика не разобрана — подсказки НЕТ (пословного бреда не бывает);
  * модуль без Tk, без потоков: очередь и паузы — забота вызывающего кода.

Замер 25.10.2026 (Gemma-4-E4B, 10 реплик): разбор реплики 2.9–10.1 с
(среднее 5.0 с). Жёсткая схема (json_schema) — 15.8–25.4 с, отказ.
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

# Слово: буквы, внутри апостроф (don't, I'd, let's).
WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*")

# ── Промпт. Главное правило — 3: кусок переводится ЦЕЛИКОМ по смыслу, ─────
# ── а не слово за словом. Пункт 4 снимает ЛЮБОЙ предел длины.        ─────
_SYSTEM = (
    "You split an English sentence into MEANING CHUNKS and translate each "
    "chunk into Russian for a Russian-speaking learner (level A2).\n"
    'Return ONLY compact JSON on one line: '
    '{"chunks":[{"en":"Would you like","ru":"хотели бы вы"}]}\n'
    "Rules:\n"
    "1. Chunks go in text order and cover EVERY word of the sentence exactly "
    "once: nothing skipped, nothing repeated, nothing added.\n"
    "2. 'en' is copied EXACTLY from the sentence — same words, same order, "
    "same spelling.\n"
    "3. Translate each chunk AS A WHOLE by its meaning, the way a Russian "
    "person says it. NEVER word-by-word: \"Would you like\" -> хотели бы вы "
    "(NOT \"было бы ты хотеть\"), \"by the window\" -> у окна (NOT \"у окно\"), "
    "\"a table\" -> столик (NOT \"а стол\").\n"
    "4. Chunk length is decided by MEANING, not by a word count: one word "
    "(table -> столик), several words (by the window -> у окна) or a long "
    "phrase (I'd like to book a table for two -> я хотел бы забронировать "
    "столик на двоих) are all fine.\n"
    "5. 'ru' is natural spoken Russian: no brackets, no explanations, no "
    "grammar notes, no variants like \"a / b\".\n"
    "6. Do not leave an article or preposition alone as its own chunk — glue "
    "it to the noun or phrase it belongs to.\n"
    "7. No markdown, no comments, no extra keys."
)

_MAX_TOKENS = 700           # перевода кусков хватает с запасом
_TEMPERATURE = 0.0          # «en» должно совпасть с репликой буква в букву


# ---------------------------------------------------------
# Токены и ключи
# ---------------------------------------------------------
def normalize(word: str) -> str:
    """Ключ слова: нижний регистр, «ёлочка» → обычный апостроф, без знаков."""
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


def sentence_key(sentence: str) -> str:
    """Ключ реплики в кэше: её слова через пробел («would you like a table»)."""
    return " ".join(t["key"] for t in tokenize(sentence))


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
# Разбор ответа модели и проверка покрытия
# ---------------------------------------------------------
def parse_chunks(raw: str) -> list:
    """Достаёт куски из ответа модели: [["Would you like","хотели бы вы"], …].

    Битый JSON, ограждение ```json, пояснения — переживаем. Мусор → [].
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
            try:
                data = json.loads(match.group(0))
            except ValueError:
                data = None
    if not isinstance(data, dict):
        return []
    items = data.get("chunks")
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        en = " ".join(str(item.get("en") or "").split())
        ru = " ".join(str(item.get("ru") or "").split())
        if en and ru:
            out.append([en, ru])
    return out


def bounds_of(sentence: str, chunks) -> list:
    """Куски с ПОЗИЦИЯМИ в реплике или [] — если покрытие не сходится.

    Проверка железная и без модели: складываем слова кусков подряд и
    сравниваем со словами реплики. Не совпало хотя бы одно слово (или
    остались лишние) — разбор негоден, подсказки не будет.
    """
    text = str(sentence or "")
    tokens = tokenize(text)
    if not tokens or not chunks:
        return []
    out = []
    pos = 0
    for pair in chunks:
        try:
            en, ru = str(pair[0]), str(pair[1])
        except (TypeError, IndexError, ValueError):
            return []
        keys = [t["key"] for t in tokenize(en)]
        if not keys:
            return []
        part = tokens[pos:pos + len(keys)]
        if [t["key"] for t in part] != keys:
            return []
        out.append({
            # «en» берём ИЗ РЕПЛИКИ: регистр и знаки как у неё
            "en": text[part[0]["start"]:part[-1]["end"]],
            "ru": ru,
            "start": part[0]["start"],
            "end": part[-1]["end"],
            "n": len(keys),
        })
        pos += len(keys)
    if pos != len(tokens):
        return []                 # остались непокрытые слова
    return out


# Служебные слова не могут быть куском В ОДИНОЧКУ: артикль или предлог,
# оторванный от существительного, — это и есть пословный перевод («а стол»,
# «у окно»). Такие куски считаем браком и просим модель заново.
_ALONE_BAD = {"a", "an", "the", "of", "to", "in", "on", "at", "by", "for",
              "with", "from", "and", "or", "some", "any"}


def looks_word_by_word(chunks) -> bool:
    """Похоже ли на перевод слово-в-слово (брак, который не показываем)."""
    for pair in chunks:
        try:
            en, ru = str(pair[0]), str(pair[1])
        except (TypeError, IndexError):
            return True
        keys = [t["key"] for t in tokenize(en)]
        if len(keys) == 1 and keys[0] in _ALONE_BAD:
            return True
        if normalize(ru) == normalize(en):
            return True          # «table» -> «table» — это не перевод
    return False


def covers(sentence: str, chunks) -> bool:
    """Куски покрывают реплику целиком и по порядку? (проверка кодом)"""
    return bool(bounds_of(sentence, chunks))


# ---------------------------------------------------------
# Словарь
# ---------------------------------------------------------
class Glossary:
    """Подсказки-переводы: разбор реплики на куски, с файловым кэшем."""

    def __init__(self, llm=None, path: str = None, autosave: bool = True) -> None:
        self.llm = llm
        self.path = path or GLOSSARY_PATH
        self.autosave = autosave
        self.chunks = {}         # ключ реплики -> [["Would you like","хотели бы вы"], …]
        self._bounds = {}        # ключ реплики -> готовые позиции (кэш в памяти)
        self.stats = {"requests": 0, "failed": 0, "retries": 0,
                      "hits": 0, "misses": 0, "rejected": 0}
        self._lock = threading.Lock()
        self.load()

    # ---------- файл ----------
    def load(self) -> bool:
        """Читает кэш с диска. Битый/отсутствующий файл — не ошибка.

        Старый формат (пословные «words»/«phrases») НЕ используется: именно
        он давал перевод слово за словом. Файл не падает, он игнорируется.
        """
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False
        chunks = data.get("chunks") if isinstance(data, dict) else None
        self.chunks = {}
        if isinstance(chunks, dict):
            for key, value in chunks.items():
                pairs = []
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            item = [item.get("en"), item.get("ru")]
                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                            en, ru = str(item[0] or ""), str(item[1] or "")
                            if en and ru:
                                pairs.append([en, ru])
                if pairs and str(key).strip():
                    self.chunks[str(key)] = pairs
        return True

    def save(self) -> bool:
        """Пишет кэш на диск (атомарно: temp + replace)."""
        payload = {"chunks": {k: self.chunks[k] for k in sorted(self.chunks)}}
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
    def bounds(self, sentence: str) -> list:
        """Позиции кусков для реплики (из кэша в памяти или с проверкой)."""
        key = sentence_key(sentence)
        if not key:
            return []
        ready = self._bounds.get(key)
        if ready is not None:
            return ready
        stored = self.chunks.get(key)
        if not stored:
            return []
        out = bounds_of(sentence, stored)
        if out:
            self._bounds[key] = out
        return out

    def lookup(self, sentence: str, index: int):
        """Что показать при наведении на символ index.

        Возвращает {"en","ru","word","start","end","phrase"} или None.
        Модель НЕ вызывается: только готовый разбор в памяти.

        «en» — весь КУСОК (его подсвечиваем и переводим), «word» — слово под
        курсором (его произносим по клику, решение ученика 03.11.2026).
        """
        text = str(sentence or "")
        tokens, pos = _locate(text, index)
        if pos is None:
            return None
        items = self.bounds(text)
        if not items:
            self.stats["misses"] += 1
            return None
        for item in items:
            if item["start"] <= index < item["end"]:
                self.stats["hits"] += 1
                return {"en": item["en"], "ru": item["ru"],
                        "word": tokens[pos]["word"],
                        "phrase": item["n"] > 1,
                        "start": item["start"], "end": item["end"]}
        self.stats["misses"] += 1
        return None

    def known(self, sentence: str) -> bool:
        """Реплика уже разобрана? Тогда модель не нужна."""
        return sentence_key(sentence) in self.chunks

    # ---------- запись (дорого: одна реплика = один запрос) ----------
    def prime(self, sentence: str, timeout: int = 120):
        """Разбирает реплику моделью и кладёт куски в словарь.

        Возвращает (ok, добавлено_реплик | причина). Один повтор, если JSON
        битый ИЛИ куски не покрыли реплику — замер показал, что так бывает
        на ~1 реплике из 5.
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
        pairs = []
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
            pairs = parse_chunks(raw)
            if (pairs and covers(text, pairs)
                    and not looks_word_by_word(pairs)):
                break
            pairs = []
            if attempt == 1:
                with self._lock:
                    self.stats["retries"] += 1

        if not pairs:
            with self._lock:
                self.stats["failed"] += 1
            return False, "куски не покрыли реплику"

        added = self.add_chunks(text, pairs)
        if added and self.autosave:
            self.save()
        return True, added

    def add_chunks(self, sentence: str, pairs) -> int:
        """Кладёт разбор реплики. Возвращает 1 (новая) или 0 (не взяли)."""
        text = str(sentence or "")
        key = sentence_key(text)
        if not key or not pairs:
            return 0
        clean = []
        for pair in pairs:
            try:
                en, ru = str(pair[0]).strip(), str(pair[1]).strip()
            except (TypeError, IndexError):
                continue
            if en and ru:
                clean.append([en, ru])
        if (not clean or not bounds_of(text, clean)
                or looks_word_by_word(clean)):
            with self._lock:
                self.stats["rejected"] += 1
            return 0
        with self._lock:
            if self.chunks.get(key) == clean:
                return 0
            self.chunks[key] = clean
            self._bounds.pop(key, None)
        return 1
