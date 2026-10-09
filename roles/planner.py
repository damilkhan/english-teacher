# -*- coding: utf-8 -*-
# =========================================================
# ROLES/PLANNER.PY — роль «Планировщик» (план урока)
# =========================================================
# Третья роль Джейн (Учитель / Аналитик / Планировщик).
# Планировщик НЕ говорит с учеником: по профилю и уровню он строит КОРОТКИЙ
# план урока (фокус, цели, активности, лексика) в виде JSON. План подключается
# к промпту Учителя отдельным блоком — так у урока появляется цель.
#
# Принципы (как у Аналитика):
#   * узкая задача — только план, без реплик ученику;
#   * методические заметки приходят ГОТОВЫМ текстом (RAG) — Planner их не ищет;
#   * безопасные дефолты: битый JSON / таймаут / нет модели → пустой план
#     (ok=False), Учитель продолжает работать;
#   * новых LLM-клиентов не создаём — используем переданный llm.
# =========================================================

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

MAX_GOALS = 4
MAX_ACTIVITIES = 4
MAX_VOCAB = 12
MAX_CONTEXT_CHARS = 1200


def default_plan() -> Dict[str, Any]:
    """Безопасный пустой план (модель недоступна / битый JSON)."""
    return {
        "focus": "",
        "goals": [],
        "activities": [],
        "target_vocab": [],
        "note": "",
        "ok": False,
        "source": "fallback",
    }


PLANNER_PROMPT_TEMPLATE = """You are an English-teaching LESSON PLANNER. You NEVER talk to the student: you design ONE short lesson plan and return JSON.

Design a short, practical plan for a private online tutor session (live chat).
Use the methodology notes below when given: prefer a task-based cycle (pre-task -> task -> language focus).

Rules:
- Match the difficulty to the CEFR level.
- Build on the weak topics and recent mistakes when they are given.
- 2 to 4 activities, each short (2-6 minutes) and doable in a chat.
- target_vocab: up to 12 useful words/phrases for this lesson.
- Keep every value short. Write field values in English.
%(context)s
Return ONLY valid JSON, no markdown, exactly in this shape:
{"focus": "Present Perfect (daily life)", "goals": ["..."], "activities": [{"name": "Warm-up", "task": "...", "minutes": 3}], "target_vocab": ["..."], "note": "..."}
"""

_JSON_RE = re.compile(r"\{.*\}", re.S)


def _clean_list(value: Any, limit: int, max_len: int) -> List[str]:
    out: List[str] = []
    if not isinstance(value, list):
        return out
    for item in value:
        name = str(item or "").strip()[:max_len]
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def _clean_activities(value: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return out
    for item in value[:MAX_ACTIVITIES]:
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or "").strip()[:160]
        name = str(item.get("name") or "").strip()[:40]
        if not task and not name:
            continue
        try:
            minutes = int(item.get("minutes"))
        except (TypeError, ValueError):
            minutes = 0
        minutes = max(0, min(15, minutes))
        out.append({"name": name or "Activity", "task": task, "minutes": minutes})
    return out


def _normalize_plan(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "focus": str(data.get("focus") or "").strip()[:120],
        "goals": _clean_list(data.get("goals"), MAX_GOALS, 120),
        "activities": _clean_activities(data.get("activities")),
        "target_vocab": _clean_list(data.get("target_vocab"), MAX_VOCAB, 40),
        "note": str(data.get("note") or "").strip()[:120],
        "ok": True,
        "source": "model",
    }


def parse_plan(raw: Optional[str]) -> Optional[Dict[str, Any]]:
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
    return _normalize_plan(data)


def format_plan(plan: Optional[Dict[str, Any]]) -> str:
    """Компактный текст плана для промпта Учителя. Пусто, если плана нет."""
    if not plan or not plan.get("ok"):
        return ""
    lines: List[str] = []
    if plan.get("focus"):
        lines.append("Focus: %s" % plan["focus"])
    goals = plan.get("goals") or []
    if goals:
        lines.append("Goals: " + "; ".join(goals))
    activities = plan.get("activities") or []
    if activities:
        lines.append("Activities:")
        for act in activities:
            minutes = act.get("minutes")
            tail = (" (%s min)" % minutes) if minutes else ""
            lines.append("- %s: %s%s" % (act.get("name", ""), act.get("task", ""), tail))
    vocab = plan.get("target_vocab") or []
    if vocab:
        lines.append("Target vocabulary: " + ", ".join(vocab))
    if plan.get("note"):
        lines.append("Note: %s" % plan["note"])
    return "\n".join(lines)


def _profile_summary(profile: Dict[str, Any], level: Optional[str]) -> str:
    """Короткая сводка профиля ученика для промпта Планировщика."""
    profile = profile or {}
    parts: List[str] = []
    if level:
        parts.append("- CEFR level: %s" % level)

    weak = []
    for item in (profile.get("weak_topics") or [])[:5]:
        name = item.get("topic") if isinstance(item, dict) else item
        name = str(name or "").strip()
        if name:
            weak.append(name)
    if weak:
        parts.append("- Weak topics (placement test): %s" % ", ".join(weak))

    for label, key in (("Recent grammar mistakes", "grammar"),
                       ("Recent vocabulary issues", "vocabulary")):
        pairs = []
        for err in (profile.get("mistakes", {}).get(key, []) or [])[-4:]:
            if not isinstance(err, dict):
                continue
            wrong = str(err.get("wrong") or "").strip()
            correct = str(err.get("correct") or "").strip()
            if wrong or correct:
                pairs.append(("%s -> %s" % (wrong, correct)) if (wrong and correct) else (wrong or correct))
        if pairs:
            parts.append("- %s: %s" % (label, "; ".join(pairs)))

    covered = [str(t) for t in (profile.get("topics_passed") or [])[-6:] if str(t).strip()]
    if covered:
        parts.append("- Already covered: %s" % ", ".join(covered))
    parts.append("- Lessons so far: %s" % profile.get("total_lessons", 0))
    return "\n".join(parts)


class Planner:
    """Роль-Планировщик: строит короткий план урока (ученику не отвечает)."""

    def __init__(self, llm: Any, timeout: int = 40, max_tokens: int = 500,
                 temperature: float = 0.4) -> None:
        self.llm = llm
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature

    format_plan = staticmethod(format_plan)

    def plan(self, profile: Dict[str, Any], level: Optional[str] = None,
             mode: str = "lesson", context: str = "") -> Dict[str, Any]:
        """Строит план урока. Не падает: при проблеме — пустой план (ok=False)."""
        if mode != "lesson":
            return default_plan()
        raw = self._ask(self.build_prompt(profile, level, context))
        parsed = parse_plan(raw)
        if parsed is None:
            _log.warning("Планировщик: ответ модели не разобран — пустой план")
            return default_plan()
        return parsed

    def build_prompt(self, profile: Dict[str, Any], level: Optional[str] = None,
                     context: str = "") -> str:
        """Собирает промпт Планировщика: шаблон + (методичка) + профиль ученика."""
        context = str(context or "").strip()[:MAX_CONTEXT_CHARS]
        ctx_block = ("\nMETHODOLOGY NOTES (guide the design):\n%s\n" % context) if context else ""
        head = PLANNER_PROMPT_TEMPLATE % {"context": ctx_block}
        return head + "\nSTUDENT PROFILE:\n" + _profile_summary(profile, level) + "\n"

    def _ask(self, prompt: str) -> Optional[str]:
        """Один вызов модели в разметке Gemma. None — если модели нет/ошибка."""
        if self.llm is None:
            return None
        text = ("<start_of_turn>user\n" + prompt + "<end_of_turn>\n"
                "<start_of_turn>model\n")
        try:
            ok, payload = self.llm.complete(
                text, max_tokens=self.max_tokens, temperature=self.temperature,
                stop=["<end_of_turn>"], timeout=self.timeout)
        except Exception as exc:
            _log.warning("Планировщик: LLM недоступна (%s)", exc)
            return None
        return payload if ok else None
