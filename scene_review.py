# -*- coding: utf-8 -*-
# =========================================================
# SCENE_REVIEW.PY — разбор ошибок В КОНЦЕ сцены (шаг 4, 02.11.2026)
# =========================================================
# Зачем: в сцене модель не зовётся совсем (шаг 3, вариант А), поэтому ошибки
# ученика никто не ловит по ходу. Ученик решил: правку в моменте НЕ делаем
# (закрыто навсегда), а показываем 1–3 ошибки В КОНЦЕ, с цитатой его же фразы.
#
# Как сделано (по образцу photo_check.py, §42):
#   * ОДИН вызов модели на всю сцену — в конце, а не в каждой реплике;
#   * модель возвращает JSON: «что сказал» → «как надо» → «почему»;
#   * ЦИТАТУ проверяет КОД: если модель переписала фразу ученика, такая
#     «ошибка» выбрасывается. Вранья в цитате быть не может по построению
#     (модель 4B, ей верить в дословность нельзя);
#   * «как надо» должно ОТЛИЧАТЬСЯ от сказанного, иначе это не правка;
#   * пустой ответ / битый JSON / нет модели → ok=False, и разбора просто нет
#     (лучше тишина, чем выдумка — правило проекта).
#
# Модуль чистый: ни Tk, ни сети, ни модели. Только текст на входе и выходе.
# =========================================================

from __future__ import annotations

import json
import re

MAX_MISTAKES = 3          # больше трёх правок за раз ученику не показываем
MAX_SAID = 60             # длиннее — уже не «фраза», а кусок рассказа
MAX_FIX = 60
MAX_WHY = 120
MAX_ANSWER = 200          # защита промпта: одна реплика ученика


SYSTEM = (
    "You check the short answers of ONE student of English (level {level}). "
    "The student talked to a waiter in a restaurant. His answers are short: "
    "two or three words is normal and correct. Reply with JSON only, no text "
    "before or after it.\n"
    "A mistake is: grammar, a wrong word, a missing small word, wrong word "
    "order, spelling.\n"
    "Not a mistake: a short but correct answer (\"Yes\", \"No thanks\", "
    "\"Card\", \"Two people\"), another correct way to say the same thing, "
    "a missing long sentence.\n"
    "Rules:\n"
    "- At most {most} mistakes, the most useful first.\n"
    "- \"said\" = the student's words copied EXACTLY, letter by letter.\n"
    "- \"fix\" = the smallest correct version of the SAME answer.\n"
    "- \"why\" = one short sentence in RUSSIAN, simple words.\n"
    "- No real mistake -> {{\"mistakes\": []}}\n"
    "Answer format: {{\"mistakes\": [{{\"said\": \"<student's words>\", "
    "\"fix\": \"<correct version>\", \"why\": \"<one short sentence>\"}}]}}"
)


def _answers(rows):
    """Только настоящие ответы: (вопрос, что сказал ученик)."""
    clean = []
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        said = str(row.get("a") or row.get("said") or "").strip()
        if not said:
            continue
        clean.append((str(row.get("q") or "").strip(), said))
    return clean


def build_messages(rows, level="A2"):
    """Сообщения для модели: правила + пронумерованные ответы ученика."""
    system = SYSTEM.format(level=(str(level or "").strip() or "A2"),
                           most=MAX_MISTAKES)
    lines = ["Student's answers in the scene:"]
    for number, (question, said) in enumerate(_answers(rows), 1):
        if question:
            lines.append("%d) Waiter: %s" % (number, question))
            lines.append("   Student: %s" % said[:MAX_ANSWER])
        else:
            lines.append("%d) Student: %s" % (number, said[:MAX_ANSWER]))
    if len(lines) == 1:
        lines.append("(no answers)")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(lines)},
    ]


# ---------- нормализация для честной сверки цитаты ----------
def _norm(text):
    """Текст без регистра, знаков и лишних пробелов — для сверки цитаты."""
    value = str(text or "").lower()
    keep = []
    for ch in value:
        keep.append(ch if (ch.isalnum() or ch == "'") else " ")
    return " ".join("".join(keep).split())


def _json_object(raw):
    """Вытащить JSON-объект из ответа модели (снимает ``` и болтовню)."""
    text = str(raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```[a-zA-Z]*\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    chunk = text[start:end + 1]
    try:
        data = json.loads(chunk)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def parse(raw, rows):
    """Разбор ответа модели: {"ok": bool, "mistakes": [...]}.

    ok=False — ответ не разобран или ни одной ЧЕСТНОЙ цитаты не нашлось:
    разбор не показываем, ученику ничего не врём.
    """
    data = _json_object(raw)
    if data is None:
        return {"ok": False, "mistakes": [], "why": "json"}
    items = data.get("mistakes")
    if not isinstance(items, list):
        return {"ok": False, "mistakes": [], "why": "no-list"}
    said_all = [_norm(said) for _question, said in _answers(rows)]
    cleaned = []
    seen = set()
    dropped = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        said = str(item.get("said") or "").strip().strip("`\"'«»").strip()
        fix = str(item.get("fix") or "").strip().strip("`\"'«»").strip()
        why = str(item.get("why") or "").strip().replace("\n", " ")
        if not said or not fix:
            dropped += 1
            continue
        # ЦИТАТА ПРОВЕРЯЕТСЯ КОДОМ: модель обязана взять слова ученика как есть
        said_norm = _norm(said)
        if not said_norm or not any(said_norm in row for row in said_all):
            dropped += 1
            continue
        # «как надо» = то же самое → это не правка
        if _norm(fix) == said_norm:
            dropped += 1
            continue
        if said_norm in seen:
            continue
        seen.add(said_norm)
        cleaned.append({"said": said[:MAX_SAID], "fix": fix[:MAX_FIX],
                        "why": why[:MAX_WHY]})
        if len(cleaned) >= MAX_MISTAKES:
            break
    if dropped:
        print("🔎 Разбор сцены: пропущено правок %d (цитата не из ответа)" % dropped)
    if not cleaned:
        if items:
            # правки были, но ни одна цитата не подтвердилась — не показываем
            return {"ok": False, "mistakes": [], "why": "quotes"}
        return {"ok": True, "mistakes": [], "why": "empty"}
    return {"ok": True, "mistakes": cleaned, "why": ""}


def review_text(data):
    """Текст разбора для чата (по-русски, цитата в кавычках-ёлочках)."""
    mistakes = list((data or {}).get("mistakes") or [])
    if not mistakes:
        return "🔎 Разбор сцены: ошибок в ответах не нашёл. Молодцом!"
    lines = ["🔎 Разбор сцены — %d %s:" % (
        len(mistakes), "место" if len(mistakes) == 1 else "места")]
    for number, item in enumerate(mistakes, 1):
        lines.append('%d. «%s» → %s' % (number, item.get("said") or "",
                                       item.get("fix") or ""))
        why = str(item.get("why") or "").strip()
        if why:
            lines.append("   " + why)
    return "\n".join(lines)


def analysis_from(data, lesson_id="", step=None):
    """Разбор в виде, который понимает profile_store.record_analysis.

    Нужен, чтобы ошибки сцены попали в базу пробелов: тогда следующее
    занятие начнётся с дрилла по ним (§55). Правило подберёт gaps.pick_rule.
    """
    errors = []
    for item in ((data or {}).get("mistakes") or []):
        errors.append({
            "type": "grammar",
            "wrong": str(item.get("said") or "")[:80],
            "correct": str(item.get("fix") or "")[:80],
            "rule": "",
            "note": str(item.get("why") or "")[:80],
        })
    return {
        "move_type": "A",
        "move_status": "P" if errors else "A",
        "errors": errors,
        "topics": [],
        "note": "scene",
        "lesson": str(lesson_id or ""),
        "scene": str(step or ""),
        "ok": bool(errors),
    }
