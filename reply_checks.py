# -*- coding: utf-8 -*-
"""ПАКЕТ ПРОВЕРОК ОТВЕТА МОДЕЛИ (шаг 2 плана §72, 11.11.2026).

Зачем. Правило в промпте — просьба, проверка в коде — гарантия. До этого
проверки жили двумя кусками внутри ChatController (_repeats_done_task,
_asks_same_question) и срабатывали только по флагу «задание только что
сдано». Замер §73 показал: даже после чистки промпта остаются повтор
задания (6-8 на 32 реплики) и повтор вопроса (5 на 32).

Здесь — ОДНО место. Каждая проверка чистАя: текст + контекст -> код
нарушения. Повторный запрос делает контроллер (он знает, как звать
модель), а не этот модуль.

Проверки общие для уроков И сцен: сцена передаёт свой контекст, код тот же.
"""

import re

import lesson as lesson_mod

CYRILLIC = re.compile(u"[\u0430-\u044f\u0410-\u042f\u0451\u0401]")

# Метки-разделы, которые модель иногда пишет в начале («Praising: Good job!»).
# Живой случай (замер §73, Qwen): метка попадала и в чат, и в озвучку.
LABEL_RE = re.compile(
    r"^\s*[-*\u2022]?\s*(praising|praise|feedback|reaction|response|"
    r"answer|note|comment|task|question|hint|student|assistant)\s*[:\u2014-]\s*",
    re.IGNORECASE)

# Чем должен заканчиваться нормальный ответ: иначе он обрублен на лимите
# токенов (LLM_CHAT_MAX_TOKENS=80 — живой случай §66: вопрос без «?»).
END_OK = u'.!?\u2026)"]\u201d\u2019'

# Насколько длинным должен быть текст, чтобы считать «обрубком» по концу.
MIN_FOR_END = 12

NAMES = {
    "empty": "пустой ответ",
    "not_english": "ответ не по-английски",
    "label": "метка-раздел в ответе",
    "two_questions": "два вопроса в реплике",
    "question_when_closed": "вопрос при закрытом уроке",
    "same_question": "повтор вопроса",
    "repeat_task": "повтор уже сданного задания",
}

NOTES = {
    "empty": "Your last reply was empty. Say ONE short sentence to the student.",
    "not_english": "Answer in ENGLISH only: the student spoke English.",
    "label": "Do NOT start your reply with a label like \"Praising:\" or "
             "\"Feedback:\". Just talk to the student.",
    "two_questions": "Ask ONE question only. Drop the other question and end "
                     "the reply after a single question.",
    "question_when_closed": "The lesson is over: do NOT ask any question. "
                            "Praise the last answer in one short line and stop.",
    "same_question": "The student has just answered this question. Do NOT ask "
                     "it again, not even in other words or with \"or not?\". "
                     "Accept the answer and move one step forward.",
    "repeat_task": "The student has already done this task in this lesson. "
                   "Give a DIFFERENT small task on the same topic, one short "
                   "line, then wait.",
}


def question_of(text):
    """Вопрос из реплики преподавателя. Пусто — вопроса нет."""
    value = str(text or "")
    if "?" not in value:
        return ""
    parts = []
    for piece in value.split("?"):
        if not piece.strip():
            continue
        # вопрос — ПОСЛЕДНЕЕ предложение перед «?»: отрезаем похвалу
        tail = piece
        for mark in (".", ";", ":"):
            if mark in tail:
                tail = tail.rsplit(mark, 1)[-1]
        tail = tail.strip().strip('"').strip("'").strip()
        if tail:
            parts.append(tail)
    return " ".join(parts)[-200:]


QUESTION_WORDS = ("tell me", "say ", "ask me", "make ", "use ", "give me",
                  "imagine", "describe", "try ", "repeat", "complete",
                  "answer", "what ", "where ", "why ", "how ", "when ",
                  "who ", "do you", "can you", "could you", "please ")


def tasks_in(text):
    """Предложения, похожие на ЗАДАНИЕ для ученика (что сказать/сделать)."""
    out = []
    for raw in re.split(r"(?<=[.!?])\s+", str(text or "")):
        low = raw.strip().lower()
        if len(low) < 8:
            continue
        if any(low.startswith(mark) or (" " + mark) in low
               for mark in QUESTION_WORDS):
            out.append(raw.strip())
    return out


def build_context(lesson=None, last_question="", lang="en"):
    """Контекст проверок из словаря урока (как его видит контроллер).

    closed          — урок закрыт: вопросов быть не должно;
    asked_tasks     — «эталоны» уже отработанного (список строк);
    last_question   — вопрос, заданный в прошлой реплике;
    student_lang    — на каком языке говорил ученик («en»/«ru»).
    """
    data = lesson if isinstance(lesson, dict) else {}
    asked = data.get("asked_tasks") or ""
    if isinstance(asked, str):
        asked = [x for x in asked.split(" \u00b7 ") if x.strip()]
    phase = str(data.get("task_phase") or "").strip().lower()
    closed = bool(data.get("lesson_closing")) or phase == "done"
    return {
        "closed": closed,
        "asked_tasks": [str(x).strip() for x in asked if str(x).strip()],
        "last_question": str(last_question or "").strip(),
        "student_lang": str(lang or "en").strip().lower(),
        "phase": phase,
    }


def check(text, ctx):
    """Список кодов нарушений. Пустой список — ответ чистый."""
    ctx = ctx or {}
    value = str(text or "").strip()
    found = []
    if not value:
        return ["empty"]
    if CYRILLIC.search(value) and ctx.get("student_lang", "en") == "en":
        found.append("not_english")
    if LABEL_RE.match(value):
        found.append("label")
    marks = value.count("?")
    if marks >= 2:
        found.append("two_questions")
    if marks and ctx.get("closed"):
        found.append("question_when_closed")
    question = question_of(value)
    last = ctx.get("last_question") or ""
    if question and last and _same(question, last):
        found.append("same_question")
    asked = ctx.get("asked_tasks") or []
    if asked and str(ctx.get("phase") or "") == "ask":
        for task in tasks_in(value):
            if any(_same(task, old) for old in asked):
                found.append("repeat_task")
                break
    # «обрубок»: ответ длинный, а не кончается ни точкой, ни знаком вопроса.
    # Короткие «Nice!» не считаем: они законны.
    if len(value) >= MIN_FOR_END and value[-1] not in END_OK:
        found.append("truncated")
    return found


def _same(first, second):
    """Одно и то же по СМЫСЛОВЫМ словам (та же логика, что §70)."""
    try:
        if lesson_mod.same_task(first, second):
            return True
    except Exception:
        pass
    try:
        return lesson_mod._flat(first) == lesson_mod._flat(second)
    except Exception:
        return False


def note(problems):
    """Добавка к промпту для повторного запроса — по всем нарушениям сразу."""
    lines = []
    for code in problems:
        text = NOTES.get(code)
        if text and text not in lines:
            lines.append(text)
    if not lines:
        return ""
    return "\nNOTE: reshape your reply: " + " ".join(lines)


def names(problems):
    """Человеческие имена нарушений для лога и теста."""
    return [NAMES.get(code, code) for code in problems]
