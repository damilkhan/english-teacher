# -*- coding: utf-8 -*-
# =========================================================
# RAG.PY — маленькая база знаний Джейн (только стандартная библиотека)
# =========================================================
#   Читает knowledge_base/index.json (карту чанков) и умеет:
#     * search(query, top_k)    — найти релевантные чанки;
#     * load_chunk_text(chunk)  — вырезать текст чанка из .md;
#     * build_context(query)    — склеить найденное в блок для промпта.
#
#   Алгоритм поиска простой (без векторов и внешних библиотек):
#     ключевые слова + заголовки чанков, совпадение слов по границам
#     (простой стемминг) и бонус 0.1 × priority. LLM не вызывается.
# =========================================================

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List


class RAG:
    """Локальная база знаний: поиск чанков и извлечение их текста.

    Если index.json отсутствует или повреждён — объект работает в режиме
    «пустой базы»: методы возвращают пустые результаты и не падают.
    """

    # Стоп-слова (RU + EN) — выкидываем шум перед сравнением.
    STOPWORDS = {
        # русские
        "и", "в", "на", "с", "по", "а", "но", "или",
        "я", "ты", "он", "она", "оно", "мы", "вы", "они",
        "что", "как", "где", "когда", "это", "то", "так",
        "же", "бы", "ли", "не", "ни", "да", "нет",
        "у", "о", "об", "от", "до", "за", "для", "при",
        # английские
        "the", "a", "an", "is", "are", "to", "of", "in", "on", "at",
        "and", "or", "if", "then", "than", "that", "this", "these", "those",
        "do", "does", "did", "be", "been", "being",
        "have", "has", "had", "will", "would", "can", "could",
        "should", "may", "might", "must", "not", "no", "so",
        "it", "its", "he", "she", "they", "we", "you", "i",
        "me", "my", "your", "our", "their",
    }
    # Минимальная длина слова для сравнения по границам (защита от мусора).
    MIN_SUBSTR_LEN = 3
    # Выделение слов: латиница, кириллица, цифры.
    _WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
    # Логгер модуля — вывод только через logging, без print.
    _log = logging.getLogger(__name__)

    def __init__(self, base_path: str = "knowledge_base") -> None:
        base = Path(base_path)
        if not base.is_absolute():
            # по умолчанию ищем базу рядом с этим модулем (корень проекта)
            base = Path(__file__).resolve().parent / base
        self.base_path: Path = base
        self.index_path: Path = self.base_path / "index.json"

        self._chunks: List[Dict[str, Any]] = []   # плоский список чанков
        self._file_cache: Dict[str, str] = {}     # кэш прочитанных .md

        self._load_index()

    # =====================================================
    # Загрузка индекса
    # =====================================================
    def _load_index(self) -> None:
        """Прочитать index.json и разложить чанки в плоский список.

        При любой проблеме (нет файла, битый JSON) — логируем WARNING
        и остаёмся с пустой базой.
        """
        if not self.index_path.is_file():
            self._log.warning(
                "RAG: index.json не найден (%s) — работаю с пустой базой",
                self.index_path,
            )
            return

        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._log.warning(
                "RAG: не удалось прочитать index.json (%s) — пустая база", exc
            )
            return

        chunks: List[Dict[str, Any]] = []
        for file_entry in raw.get("files", []) or []:
            file_name = file_entry.get("file")
            if not file_name:
                continue
            for chunk in file_entry.get("chunks", []) or []:
                chunk_id = chunk.get("id")
                heading = chunk.get("heading", "")
                if not chunk_id or not heading:
                    continue
                keywords = list(chunk.get("keywords", []) or [])
                chunks.append({
                    "chunk_id": chunk_id,
                    "file": file_name,
                    "heading": heading,
                    "keywords": keywords,
                    "priority": float(chunk.get("priority", 0) or 0),
                    # предвычисленные токены — ускоряет поиск
                    "_kw_tokens": self._tokens(" ".join(keywords)),
                    "_hd_tokens": self._tokens(heading),
                })

        self._chunks = chunks
        self._log.info("RAG: загружено %d чанков из %s", len(chunks), self.index_path)

    # =====================================================
    # Сравнение слов (простой «стемминг»)
    # =====================================================
    @staticmethod
    def _words(text: str) -> List[str]:
        """Разбить строку на слова в нижнем регистре."""
        if not text:
            return []
        return RAG._WORD_RE.findall(text.lower())

    @classmethod
    def _tokens(cls, text: str) -> List[str]:
        """Слова без стоп-слов (для сравнения запроса и чанков)."""
        return [w for w in cls._words(text) if w not in cls.STOPWORDS]

    @classmethod
    def _match(cls, a: str, b: str) -> bool:
        """Простой стемминг по ГРАНИЦАМ слов (без ложных подсовпадений).

        Совпадает, если слова равны или одно целиком входит в другое на
        границе слова: 'task' → 'task-based' (матч), но 'use' → 'because' и
        'act' → 'practice' (НЕ матч). В Python re дефис — граница слова.
        """
        if not a or not b:
            return False
        if a == b:
            return True
        if len(a) <= len(b):
            short, long_word = a, b
        else:
            short, long_word = b, a
        if len(short) < cls.MIN_SUBSTR_LEN:
            return False
        return re.search(rf"\b{re.escape(short)}\b", long_word) is not None

    # =====================================================
    # Поиск
    # =====================================================
    def search(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """Найти top_k чанков, релевантных запросу.

        Возвращает список словарей вида
        {"chunk_id", "file", "heading", "score"}, отсортированный
        по score по убыванию. Если совпадений нет — пустой список.
        """
        if not self._chunks:
            self._log.info("RAG.search: пустая база — возвращаю []")
            return []

        query_tokens = set(self._tokens(query or ""))
        if not query_tokens:
            self._log.info("RAG.search: пустой/бессмысленный запрос — возвращаю []")
            return []

        results: List[Dict[str, Any]] = []
        for chunk in self._chunks:
            matched = self._count_matches(query_tokens, chunk)
            if matched <= 0:
                continue
            # +1 за каждое совпавшее слово запроса и бонус за priority
            score = matched + 0.1 * chunk["priority"]
            results.append({
                "chunk_id": chunk["chunk_id"],
                "file": chunk["file"],
                "heading": chunk["heading"],
                "score": round(score, 4),
            })

        results.sort(key=lambda item: item["score"], reverse=True)
        top = results[:max(0, int(top_k))]
        self._log.info(
            "RAG.search('%s'): совпадений %d, отдаю %d — %s",
            (query or "").strip(), len(results), len(top),
            [c["chunk_id"] for c in top],
        )
        return top

    @classmethod
    def _count_matches(cls, query_tokens: set, chunk: Dict[str, Any]) -> int:
        """Сколько РАЗНЫХ слов запроса совпало с keywords/заголовком чанка."""
        haystack = chunk["_kw_tokens"] + chunk["_hd_tokens"]
        hits = 0
        for q_token in query_tokens:
            if any(cls._match(q_token, token) for token in haystack):
                hits += 1
        return hits

    # =====================================================
    # Извлечение текста чанка
    # =====================================================
    def _read_file(self, file_name: str) -> str:
        """Прочитать .md-файл (с кэшированием). Пусто, если файла нет."""
        if file_name in self._file_cache:
            return self._file_cache[file_name]
        path = self.base_path / file_name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self._log.warning("RAG: не удалось прочитать %s (%s)", path, exc)
            text = ""
        self._file_cache[file_name] = text
        return text

    @staticmethod
    def _heading_level(line: str) -> int:
        """Уровень markdown-заголовка ('##' → 2). 0, если это не заголовок."""
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            return 0
        hashes = len(stripped) - len(stripped.lstrip("#"))
        rest = stripped[hashes:]
        if rest and not rest[0].isspace():
            return 0   # например '#тег' — не заголовок
        return hashes

    def load_chunk_text(self, chunk: Dict[str, Any]) -> str:
        """Вырезать текст чанка из .md-файла по его заголовку.

        Находит первую строку уровня '##' (или глубже), содержащую
        heading (частичное совпадение, регистронезависимо), и берёт
        всё до следующего заголовка того же уровня или до конца файла.
        Возвращает обрезанный текст либо пустую строку при неудаче.
        """
        if not chunk:
            return ""
        file_name = chunk.get("file")
        heading = chunk.get("heading")
        if not file_name or not heading:
            return ""

        text = self._read_file(file_name)
        if not text:
            return ""

        lines = text.splitlines()
        heading_lower = heading.strip().lower()

        start = None
        level = 0
        for idx, line in enumerate(lines):
            lvl = self._heading_level(line)
            if lvl >= 2 and heading_lower in line.lower():
                start = idx
                level = lvl
                break

        if start is None:
            self._log.warning(
                "RAG: заголовок '%s' не найден в %s", heading, file_name
            )
            return ""

        end = len(lines)
        for idx in range(start + 1, len(lines)):
            if self._heading_level(lines[idx]) == level:
                end = idx
                break

        return "\n".join(lines[start:end]).strip()

    # =====================================================
    # Контекст для промпта
    # =====================================================
    def build_context(self, query: str, top_k: int = 2) -> str:
        """Собрать текст релевантных чанков в один блок для промпта.

        Вызывает search, для каждого чанка берёт текст через
        load_chunk_text и склеивает блоки разделителем.
        Если ничего не найдено — возвращает пустую строку.
        """
        found = self.search(query, top_k=top_k)
        if not found:
            return ""

        blocks: List[str] = []
        for chunk in found:
            text = self.load_chunk_text(chunk)
            if not text:
                continue
            header = "=== %s (%s) ===" % (
                chunk.get("heading", ""), chunk.get("file", "")
            )
            blocks.append(header + "\n" + text)

        if not blocks:
            self._log.info("RAG.build_context: найденные чанки без текста")
            return ""

        context = "\n\n---\n\n".join(blocks)
        self._log.info(
            "RAG.build_context('%s'): собрано %d блоков, %d символов",
            (query or "").strip(), len(blocks), len(context),
        )
        return context
