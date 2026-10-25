# -*- coding: utf-8 -*-
# =========================================================
# ROLES/ANALYST.PY — роль «Аналитик» (разбор реплики ученика)
# =========================================================
# Одна из трёх ролей Джейн (Учитель / Аналитик / Планировщик).
# Аналитик НЕ говорит с учеником: он получает ОДНУ реплику ученика и
# возвращает СТРУКТУРУ (JSON) — что ученик сделал (move_type/move_status по
# таксономии TACT), какие языковые ошибки допустил, какие темы затронул и
# короткую заметку о прогрессе.
#
# Принципы:
#   * узкая задача — только разбор, без реплик ученику;
#   * словарь таксономии (student_move_taxonomy) ВСТРОЕН в промпт:
#     Аналитик НЕ использует rag.py;
#   * безопасные дефолты: битый JSON / таймаут / недоступная модель →
#     нейтральный результат, остальные роли продолжают работать;
#   * новых LLM-клиентов не создаём — используем переданный llm.
# =========================================================

from __future__ import annotations

import json
from collections import Counter
import logging
import re
from typing import Any, Dict, List, Optional

import profile_store

_log = logging.getLogger(__name__)

# --- словарь таксономии (TACT, student_move_taxonomy.md) ---
MOVE_TYPES = ("Q", "A", "S", "F", "O")     # что ученик ДЕЛАЕТ
MOVE_STATUSES = ("A", "P", "N")            # нужно ли ОЦЕНИВАТЬ
ERROR_TYPES = ("grammar", "vocabulary", "spelling", "pronunciation")

MAX_ERRORS = 5
MAX_TOPICS = 3
MAX_MESSAGE_CHARS = 600
MAX_REPLY_CHARS = 200


def default_analysis() -> Dict[str, Any]:
    """Безопасный нейтральный разбор (модель недоступна / битый JSON)."""
    return {
        "move_type": "O",
        "move_status": "N",
        "errors": [],
        "topics": [],
        "note": "",
        "ok": False,
        "source": "fallback",
    }


# Словарь таксономии — ЧАСТЬ промпта (не RAG): Аналитик должен работать
# даже без knowledge_base. Формулировки короткие, чтобы не грузить модель.
ANALYST_PROMPT_TEMPLATE = """You are an English-teaching dialogue ANALYST. You NEVER talk to the student: you only classify ONE student message and return JSON.

What the student DOES (move_type):
- Q = question / inquiry (asks meaning, usage, correctness)
- A = answer / attempt (tries to do the current task in English)
- S = statement / explanation / comment (an idea, not a direct answer)
- F = feedback / acknowledgement (agrees, confirms, signals understanding)
- O = other / social / off-task

Whether it must be EVALUATED (move_status):
- A = adequate / accepted, P = problematic / needs repair  -> ONLY for move_type A
- N = non-evaluable -> ALWAYS for Q, S, F and O

Rules:
- ONLY move_type A can be A or P. For Q, S, F, O the status is ALWAYS N.
- errors: list ONLY real language problems in the student's English.
  Each item: {"type": "grammar|vocabulary|spelling|pronunciation", "wrong": "...", "correct": "...", "note": "short"}.
  Use [] if there are no real errors. Never invent errors.
- Speech hesitations: the student talks ALOUD and may repeat a word or phrase
  ("the park in the park", "I I think"). A repetition, a restart or a stutter is
  NOT an error — never report it, not even as "redundant". Report only real
  language problems.
- The student often writes in RUSSIAN. Analyse ONLY the student's ENGLISH.
  If the message is NOT in English, return "errors": [] (do NOT report Russian
  mistakes as English errors) and do not force status A/P.
- topics: up to 3 short topics of the message (for example "travel", "work and study").
- note: one very short progress note (at most 12 words).
%(context)s
Student message: %(message)s

Return ONLY valid JSON, no markdown, in exactly this shape:
{"move_type": "A", "move_status": "P", "errors": [], "topics": [], "note": ""}
"""

_JSON_RE = re.compile(r"\{.*\}", re.S)


def _flat(text: Any) -> str:
    """Текст без регистра, знаков и лишних пробелов — чтобы сравнить «то же».

    Нужен для проверки «ошибка на самом деле не ошибка»: модель иногда пишет
    {"wrong": "in the park", "correct": "in the park"} (ЗАМЕР 25.10.2026:
    такая «ошибка» приходила 4 раза из 4 на запинку ученика).
    """
    t = re.sub(r"[^0-9a-z\u0430-\u044f\u0451' ]", " ", str(text or "").lower())
    return " ".join(t.split())


def _collapse_repeats(text: Any, rounds: int = 3) -> str:
    """Убрать повтор подряд идущих слов/фраз: «in the park in the park» → «in the park».

    Сравниваем «как сказано» и «как правильно» уже БЕЗ повторов: если разница
    только в запинке, это не ошибка (решение ученика 25.10.2026).
    """
    words = _flat(text).split()
    for _ in range(max(1, int(rounds))):
        n = len(words)
        out: List[str] = []
        i = 0
        changed = False
        while i < n:
            for size in range(min(6, (n - i) // 2), 0, -1):
                if words[i:i + size] == words[i + size:i + 2 * size]:
                    out.extend(words[i:i + size])
                    i += 2 * size
                    changed = True
                    break
            else:
                out.append(words[i])
                i += 1
        words = out
        if not changed:
            break
    return " ".join(words)


def is_disfluency(wrong: Any, correct: Any) -> bool:
    """«Ошибка» — это на самом деле запись/повтор? Тогда её не считаем.

    Признаки запинки (решение ученика 25.10.2026: повтор — не ошибка):
      * «как сказано» и «как правильно» совпадают: «in the park» → «in the park»;
      * разница только в повторе: «the park in the park» → «in the park»,
        «I I think» → «I think».
    Настоящая ошибка («go» → «went», «park» → «the park») остаётся ошибкой.
    """
    w, c = _flat(wrong), _flat(correct)
    if not w or not c:
        return False            # пустое «правильно» может быть настоящей ошибкой
    if w == c:
        return True             # «in the park» → «in the park»: ошибки нет
    if _collapse_repeats(wrong) == _collapse_repeats(correct):
        return True
    # ученик сказал ТО ЖЕ плюс лишние слова, и все лишние — повторы уже
    # сказанного: «the park + in the park» → лишние «the», «park».
    said = Counter(w.split())
    right = Counter(c.split())
    extra = said - right
    if extra and all(word in right for word in extra):
        return True             # лишние слова — повторы уже сказанного
    # Ещё форма запинки (ЗАМЕР 25.10.2026, 3 раза из 4): модель предлагает
    # «the park in the park» → «the park», то есть правильный вариант — это
    # КУСОК сказанного, а в сказанном есть повтор.
    said_words = w.split()
    right_words = c.split()
    if len(said_words) != len(set(said_words)):
        for start in range(len(said_words) - len(right_words) + 1):
            if said_words[start:start + len(right_words)] == right_words:
                return True
    return False

def _clean_errors(value: Any) -> List[Dict[str, str]]:
    """Нормализует список ошибок: типы, длины, отбрасывает пустое."""
    out: List[Dict[str, str]] = []
    if not isinstance(value, list):
        return out
    for item in value[:MAX_ERRORS]:
        if isinstance(item, dict):
            wrong = str(item.get("wrong") or "").strip()
            correct = str(item.get("correct") or "").strip()
            etype = str(item.get("type") or "").strip().lower()
            note = str(item.get("note") or "").strip()
        elif isinstance(item, str):
            wrong, correct, etype, note = item.strip(), "", "", ""
        else:
            continue
        if not wrong and not correct:
            continue
        if is_disfluency(wrong, correct):
            continue            # запинка/повтор — не ошибка
        if etype not in ERROR_TYPES:
            etype = "grammar"
        out.append({
            "type": etype,
            "wrong": wrong[:80],
            "correct": correct[:80],
            "note": note[:80],
        })
    return out


def _clean_topics(value: Any) -> List[str]:
    """Список тем: строки без пустых, без дублей, не длиннее MAX_TOPICS."""
    out: List[str] = []
    if not isinstance(value, list):
        return out
    for item in value:
        name = str(item or "").strip()[:40]
        if name and name not in out:
            out.append(name)
        if len(out) >= MAX_TOPICS:
            break
    return out


def _normalize_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
    """Приводит JSON модели к строгому виду и применяет правило таксономии."""
    move_type = str(data.get("move_type") or "").strip().upper()
    if move_type not in MOVE_TYPES:
        move_type = "O"

    raw_status = str(data.get("move_status") or "").strip().upper()
    if move_type != "A":
        # только Answer/Attempt оценивается; всё прочее — Non-evaluable
        move_status = "N"
    else:
        move_status = raw_status if raw_status in ("A", "P") else "N"

    return {
        "move_type": move_type,
        "move_status": move_status,
        "errors": _clean_errors(data.get("errors")),
        "topics": _clean_topics(data.get("topics")),
        "note": str(data.get("note") or "").strip()[:120],
        "ok": True,
        "source": "model",
    }


def parse_analysis(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Достаёт JSON из ответа модели и нормализует его. None — если не вышло."""
    if not raw:
        return None
    match = _JSON_RE.search(raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return _normalize_analysis(data)


class Analyst:
    """Роль-Аналитик: разбирает реплику ученика в структуру (ученику не отвечает)."""

    def __init__(self, llm: Any, timeout: int = 30, max_tokens: int = 260,
                 temperature: float = 0.2) -> None:
        self.llm = llm
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

    def analyze(self, student_text: str, teacher_reply: str = "",
                mode: str = "lesson", level: Optional[str] = None) -> Dict[str, Any]:
        """Классифицирует реплику ученика. Не падает: при проблеме — дефолт."""
        if not str(student_text or "").strip():
            return default_analysis()
        raw = self._ask(self.build_prompt(student_text, teacher_reply, level))
        parsed = parse_analysis(raw)
        if parsed is None:
            _log.warning("Аналитик: ответ модели не разобран — беру нейтральный дефолт")
            return default_analysis()
        # Страховка: если в реплике нет латиницы, английских ошибок там быть
        # не может — не засоряем профиль «ошибками» из русского текста.
        if not re.search(r"[A-Za-z]", str(student_text or "")):
            parsed["errors"] = []
            if parsed.get("move_type") == "A":
                parsed["move_status"] = "N"
        return parsed

    def build_prompt(self, student_text: str, teacher_reply: str = "",
                     level: Optional[str] = None) -> str:
        """Собирает промпт Аналитика (словарь таксономии встроен в текст)."""
        context_parts: List[str] = []
        if level:
            context_parts.append("- CEFR level: %s" % level)
        reply = str(teacher_reply or "").strip().replace("\n", " ")
        if reply:
            context_parts.append("- The teacher's reply (context only): %s"
                                 % reply[:MAX_REPLY_CHARS])
        context = ("\n" + "\n".join(context_parts) + "\n") if context_parts else ""
        return ANALYST_PROMPT_TEMPLATE % {
            "context": context,
            "message": str(student_text or "").strip()[:MAX_MESSAGE_CHARS],
        }

    def apply(self, analysis: Dict[str, Any], user_text: str,
              jane_response: str = "", user_id: Any = None) -> List[str]:
        """Записать разбор в прогресс ученика (делегирует profile_store)."""
        try:
            return profile_store.record_analysis(analysis, user_text, jane_response, user_id)
        except Exception as exc:
            _log.warning("Аналитик: разбор не записан (%s)", exc)
            return []

    def _ask(self, prompt: str) -> Optional[str]:
        """Один вызов модели как ОДНО сообщение пользователя (OpenAI-эндпоинт).

        Разметку под конкретную модель применяет сам сервер llama.cpp, поэтому
        вручную теги Gemma тут не ставим. None — если модели нет/ошибка.
        """
        if self.llm is None:
            return None
        messages = [{"role": "user", "content": prompt}]
        try:
            ok, payload = self.llm.complete(
                messages, max_tokens=self.max_tokens, temperature=self.temperature,
                timeout=self.timeout)
        except Exception as exc:                      # клиент любого типа
            _log.warning("Аналитик: LLM недоступна (%s)", exc)
            return None
        return payload if ok else None
