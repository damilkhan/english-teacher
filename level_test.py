# -*- coding: utf-8 -*-
# =========================================================
# LEVEL_TEST.PY — адаптивный тест на определение уровня (A1–C1)
# =========================================================
# Ядро теста. НЕ привязано к конкретной модели: вопросы генерирует
# тот llm-клиент, который активен в приложении (по умолчанию —
# llm_client.LLMClient, т.е. что сейчас крутится на llama.cpp сервере).
#
# Здесь НЕТ tkinter и НЕТ сети напрямую — только вызовы llm_client.
# Поэтому модуль тестируется без окна и без живой модели (set_client).
#
# Алгоритм (адаптивный, «лестница»):
#   * сложность 1..5 соответствует CEFR A1..C1;
#   * старт со сложности 2 (A2 — нейтральная точка);
#   * правильный ответ → сложность +1, ошибка → сложность −1 (clamp 1..5);
#   * тест идёт минимум MIN_QUESTIONS и максимум MAX_QUESTIONS вопросов;
#   * ранняя остановка после MIN_QUESTIONS — если сложность стабилизировалась
#     (последние 3 вопроса заданы на одной сложности).
#
# Публичный интерфейс (ровно по ТЗ):
#   start_test(user_id)                  → первый вопрос
#   get_next_question(user_id, answer)   → следующий вопрос / финал
#   check_answer(user_id, answer)        → проверка ответа
#   get_result(user_id)                  → уровень A1–C1 (+ запись в профиль)
# =========================================================

import json
import random
import re
from datetime import datetime

import user_manager

# ---------------------------------------------------------
# Настройки модели-независимой логики
# ---------------------------------------------------------
DIFFICULTY_TO_LEVEL = {1: "A1", 2: "A2", 3: "B1", 4: "B2", 5: "C1"}
LEVELS = tuple(DIFFICULTY_TO_LEVEL.values())

START_DIFFICULTY = 2      # A2 — нейтральный старт
MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5

MIN_QUESTIONS = 10        # раньше этого не заканчиваем
MAX_QUESTIONS = 15        # дольше этого не задаём
STABLE_WINDOW = 3         # сколько последних вопросов считаем «плато»

# Темы вопросов: выбираются СЛУЧАЙНО из пула (не пользователем — иначе
# ученик уходит в знакомые темы и уровень завышается). В рамках сессии
# тема не повторяется.
TOPIC_POOL = (
    "everyday life and daily routine",
    "travel and transport",
    "work and study",
    "food and cooking",
    "family and friends",
    "health and sport",
    "shopping and money",
    "city life and directions",
    "weather and seasons",
    "technology and the internet",
    "films, music and books",
    "feelings and opinions",
)

# ---------------------------------------------------------
# Промпты. Хранятся ЗДЕСЬ и не зависят от модели: любой llm-клиент
# получит ровно этот текст и должен вернуть строгий JSON.
# ---------------------------------------------------------
QUESTION_JSON_SHAPE = (
    '{"question": "...", "options": ["...", "...", "...", "..."], "correct": 0}'
)

QUESTION_PROMPT_TEMPLATE = (
    "You are an experienced English (CEFR) placement-test generator.\n"
    "Write exactly ONE multiple-choice question that checks a learner's English "
    "at CEFR level %(level)s.\n"
    "Topic: %(topic)s.\n"
    "Rules:\n"
    "- Exactly 4 options; exactly one is correct; three are plausible.\n"
    "- Vocabulary, grammar and sentence length MUST match level %(level)s.\n"
    "- Do NOT add explanations, comments, numbering or markdown.\n"
    "Return ONLY valid JSON in exactly this shape:\n"
    + QUESTION_JSON_SHAPE + "\n"
    "where \"correct\" is the 0-based index of the right option.\n"
)

# Ожидаемая сложность в терминах CEFR — чтобы модель понимала задание.
_LEVEL_INSTRUCTION = {
    "A1": "A1 (beginner): very basic words, present simple, 3–6 words per sentence.",
    "A2": "A2 (elementary): everyday words, past/future simple, short sentences.",
    "B1": "B1 (intermediate): common phrasal verbs, mixed tenses, medium sentences.",
    "B2": "B2 (upper-intermediate): rich vocabulary, complex sentences, nuance.",
    "C1": "C1 (advanced): advanced vocabulary, idioms, sophisticated structures.",
}

# ---------------------------------------------------------
# Резервный банк вопросов (на случай, если модель недоступна/вернула мусор).
# Тест обязан работать всегда — даже без готового сервера.
# ---------------------------------------------------------
_QUESTION_BANK = {
    1: [  # A1
        {"question": "Choose the correct sentence.",
         "options": ["She is a teacher.", "She are a teacher.",
                     "She am a teacher.", "She be a teacher."], "correct": 0},
        {"question": "What ___ your name?",
         "options": ["is", "are", "am", "be"], "correct": 0},
    ],
    2: [  # A2
        {"question": "I ___ to the cinema yesterday.",
         "options": ["went", "go", "goed", "going"], "correct": 0},
        {"question": "She is older ___ me.",
         "options": ["than", "then", "as", "that"], "correct": 0},
    ],
    3: [  # B1
        {"question": "If I ___ more time, I would travel more.",
         "options": ["had", "have", "will have", "having"], "correct": 0},
        {"question": "He's looking forward to ___ his new job.",
         "options": ["starting", "start", "started", "starts"], "correct": 0},
    ],
    4: [  # B2
        {"question": "Hardly ___ the meeting begun when the power went out.",
         "options": ["had", "has", "did", "was"], "correct": 0},
        {"question": "The proposal was turned ___ by the committee.",
         "options": ["down", "off", "up", "over"], "correct": 0},
    ],
    5: [  # C1
        {"question": "___ the adverse weather, the expedition reached the summit.",
         "options": ["Notwithstanding", "Despite of", "Although", "Even though"],
         "correct": 0},
        {"question": "His argument, however ___ , failed to convince the panel.",
         "options": ["cogent", "cogently", "cogency", "cogency's"], "correct": 0},
    ],
}

# ---------------------------------------------------------
# Внутреннее состояние
# ---------------------------------------------------------
_SESSIONS = {}          # user_id → сессия
_client = None          # ленивый llm-клиент (можно подменить в тестах)


def set_client(client):
    """Подменить llm-клиент (для тестов и для «любой модели»)."""
    global _client
    _client = client


def _get_client():
    global _client
    if _client is None:
        # импорт внутри: на случай, если тестам llm_client не нужен вовсе
        from llm_client import LLMClient
        _client = LLMClient()
    return _client


# ---------------------------------------------------------
# Генерация вопроса через активную модель
# ---------------------------------------------------------
def _ask_llm(prompt):
    """Возвращает текст ответа модели или None (оффлайн/ошибка)."""
    client = _get_client()
    if client is None:
        return None
    try:
        ok, payload = client.complete(
            prompt, max_tokens=300, temperature=0.5,
            stop=["\n\n", "<end_of_turn>"], timeout=90)
    except Exception as exc:                       # клиент любого типа
        print("⚠️ level_test: LLM недоступна (%s)" % exc)
        return None
    return payload if ok else None


def _parse_question(raw, difficulty, topic):
    """Разбирает JSON-ответ модели в вопрос. Мусор → None."""
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except Exception:
        return None

    question = str(data.get("question") or "").strip()
    options = data.get("options")
    correct = data.get("correct")

    if not question or not isinstance(options, list) or len(options) != 4:
        return None
    options = [str(o).strip() for o in options]
    if any(not o for o in options):
        return None

    if isinstance(correct, str):
        c = correct.strip().upper()
        if len(c) == 1 and c in "ABCD":
            correct = "ABCD".index(c)
        else:
            try:
                correct = int(c)
            except ValueError:
                return None
    try:
        correct = int(correct)
    except (TypeError, ValueError):
        return None
    if not 0 <= correct <= 3:
        return None

    return {"question": question, "options": options,
            "correct": correct, "difficulty": difficulty, "topic": topic,
            "source": "model"}


def _bank_question(difficulty, topic, used_texts):
    """Вопрос из резервного банка (без повторов, если возможно)."""
    pool = _QUESTION_BANK.get(difficulty) or _QUESTION_BANK[START_DIFFICULTY]
    fresh = [q for q in pool if q["question"] not in used_texts]
    chosen = random.choice(fresh or pool)
    item = dict(chosen)
    item.update({"difficulty": difficulty, "topic": topic, "source": "bank"})
    return item


def _generate_question(difficulty, topic, used_texts):
    """Сначала — модель; при неудаче — резервный банк."""
    level = DIFFICULTY_TO_LEVEL[difficulty]
    prompt = QUESTION_PROMPT_TEMPLATE % {
        "level": _LEVEL_INSTRUCTION[level],
        "topic": topic,
    }
    question = _parse_question(_ask_llm(prompt), difficulty, topic)
    if question is None:
        question = _bank_question(difficulty, topic, used_texts)
    return question


def _public_question(session):
    """Вопрос наружу — БЕЗ правильного ответа."""
    q = session["current"]
    return {
        "question": q["question"],
        "options": list(q["options"]),
        "difficulty": q["difficulty"],
        "difficulty_label": DIFFICULTY_TO_LEVEL[q["difficulty"]],
        "index": session["index"],
        "total_max": MAX_QUESTIONS,
        "finished": False,
        "result": None,
    }


def _pick_topic(session):
    """Случайная тема из пула, не повторяющаяся в этой сессии."""
    used = set(session["asked_topics"])
    fresh = [t for t in TOPIC_POOL if t not in used]
    topic = random.choice(fresh or list(TOPIC_POOL))
    session["asked_topics"].append(topic)
    return topic


def _queue_question(session, difficulty):
    """Кладёт новый вопрос в сессию, возвращает его публичное представление."""
    topic = _pick_topic(session)
    used_texts = {h["question"] for h in session["history"]}
    session["current"] = _generate_question(difficulty, topic, used_texts)
    session["index"] += 1
    session["evaluated"] = False
    session["last_check"] = None
    return _public_question(session)


# ---------------------------------------------------------
# Публичный интерфейс
# ---------------------------------------------------------
def start_test(user_id):
    """Начинает тест: сбрасывает сессию и отдаёт первый вопрос."""
    user_id = int(user_id)
    session = {
        "user_id": user_id,
        "difficulty": START_DIFFICULTY,
        "index": 0,
        "history": [],          # [{"difficulty", "correct", "topic", "question"}]
        "asked_topics": [],
        "current": None,
        "evaluated": False,
        "last_check": None,
        "finished": False,
        "result": None,
    }
    _SESSIONS[user_id] = session
    return _queue_question(session, session["difficulty"])


def check_answer(user_id, answer):
    """Проверяет ответ на ТЕКУЩИЙ вопрос. Детерминированно, без модели.

    Идемпотентно: повторный вызов на том же вопросе отдаёт тот же результат,
    но НЕ добавляет запись в историю ещё раз.
    """
    session = _require_session(user_id)
    if session["evaluated"]:
        return session["last_check"]
    return _evaluate(session, answer)


def get_next_question(user_id, last_answer=None):
    """Следующий вопрос (адаптивно) или финальный результат.

    last_answer можно передать сюда вместо отдельного check_answer —
    тогда текущий вопрос будет оценён здесь.
    """
    session = _require_session(user_id)

    if session["finished"]:
        return {"finished": True, "result": session["result"]}

    # оценка текущего вопроса (если ещё не оценивали)
    if last_answer is not None and not session["evaluated"]:
        _evaluate(session, last_answer)

    # ещё не отвечали на текущий? тогда отдаём его же
    if not session["evaluated"]:
        return _public_question(session)

    # --- адаптация сложности ---
    if session["last_check"]["correct"]:
        session["difficulty"] = min(MAX_DIFFICULTY, session["difficulty"] + 1)
    else:
        session["difficulty"] = max(MIN_DIFFICULTY, session["difficulty"] - 1)

    if _should_stop(session):
        session["finished"] = True
        session["result"] = _build_result(session)
        return {"finished": True, "result": session["result"]}

    return _queue_question(session, session["difficulty"])


def get_result(user_id):
    """Итоговый уровень (A1–C1). Один раз сохраняет его в профиль ученика."""
    session = _SESSIONS.get(_int_or_none(user_id))
    if session is None:
        return None
    if session["result"] is None:
        session["result"] = _build_result(session)
    session["finished"] = True
    session["result"]["saved"] = _save_result(session["user_id"], session["result"])
    return session["result"]


def cancel_test(user_id):
    """Прерывает тест: сессию выкидываем, профиль НЕ трогаем."""
    return _SESSIONS.pop(_int_or_none(user_id), None) is not None


def is_running(user_id):
    session = _SESSIONS.get(_int_or_none(user_id))
    return bool(session and not session["finished"])


# ---------------------------------------------------------
# Внутренняя логика оценки
# ---------------------------------------------------------
def _require_session(user_id):
    session = _SESSIONS.get(_int_or_none(user_id))
    if session is None:
        raise KeyError("Тест не запущен для пользователя %r" % (user_id,))
    return session


def _int_or_none(user_id):
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


def _resolve_choice(question, answer):
    """Ответ пользователя → индекс варианта (0..3) или None.

    Понимает: 0..3, 'A'..'D', '1'..'4' и текст самого варианта.
    """
    options = question["options"]
    if isinstance(answer, bool):
        return None
    if isinstance(answer, int):
        return answer if 0 <= answer <= 3 else None

    text = str(answer or "").strip()
    if not text:
        return None
    if len(text) == 1 and text.upper() in "ABCD":
        return "ABCD".index(text.upper())
    if len(text) == 1 and text in "1234":
        return int(text) - 1
    low = text.lower()
    for i, opt in enumerate(options):
        if opt.strip().lower() == low:
            return i
    return None


def _evaluate(session, answer):
    """Оценивает текущий вопрос, пишет в историю, возвращает результат."""
    question = session["current"]
    chosen = _resolve_choice(question, answer)
    correct = (chosen == question["correct"])

    session["history"].append({
        "difficulty": question["difficulty"],
        "correct": correct,
        "topic": question["topic"],
        "question": question["question"],
    })
    session["evaluated"] = True
    session["last_check"] = {
        "correct": correct,
        "correct_index": question["correct"],
        "correct_answer": question["options"][question["correct"]],
        "chosen_index": chosen,
        "chosen": question["options"][chosen] if chosen is not None else None,
        "question": question["question"],
    }
    return session["last_check"]


def _should_stop(session):
    """Хватит ли вопросов, чтобы уверенно назвать уровень."""
    n = len(session["history"])
    if n >= MAX_QUESTIONS:
        return True
    if n >= MIN_QUESTIONS:
        recent = session["history"][-STABLE_WINDOW:]
        if len({h["difficulty"] for h in recent}) == 1:     # «плато» сложности
            return True
    return False


def _build_result(session):
    """Считает уровень по истории ответов.

    Оценка: каждый ответ даёт балл = сложность вопроса (верно) либо
    сложность−1 (неверно). Средний балл усредняем с ФИНАЛЬНОЙ сложностью
    (сильный сигнал адаптации) и округляем до ближайшего уровня.
    """
    history = session["history"]
    if not history:
        idx = START_DIFFICULTY
        correct = total = 0
    else:
        values = [h["difficulty"] if h["correct"] else max(MIN_DIFFICULTY,
                                                           h["difficulty"] - 1)
                  for h in history]
        avg = sum(values) / float(len(values))
        idx = round((avg + session["difficulty"]) / 2.0)
        idx = int(max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, idx)))
        correct = sum(1 for h in history if h["correct"])
        total = len(history)

    breakdown = {}
    for h in history:
        cell = breakdown.setdefault(DIFFICULTY_TO_LEVEL[h["difficulty"]],
                                    {"correct": 0, "total": 0})
        cell["total"] += 1
        if h["correct"]:
            cell["correct"] += 1

    return {
        "level": DIFFICULTY_TO_LEVEL[idx],
        "difficulty": idx,
        "correct": correct,
        "total": total,
        "breakdown": breakdown,
        "date": datetime.now().isoformat(timespec="seconds"),
        "saved": False,
    }


def _save_result(user_id, result):
    """Пишет уровень в profiles/user_N.json (личность — во владении user_manager)."""
    if user_manager.get_user(user_id) is None:
        return False
    payload = {
        "level": result["level"],
        "level_test": {
            "level": result["level"],
            "correct": result["correct"],
            "total": result["total"],
            "date": result["date"],
        },
    }
    return bool(user_manager.update_user(user_id, payload))
