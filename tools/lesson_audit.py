# -*- coding: utf-8 -*-
# =========================================================
# TOOLS/LESSON_AUDIT.PY — «УЧЕНИК-РОБОТ»: аудит уроков (§92)
# =========================================================
#   python tools\lesson_audit.py                     # быстрый: все уроки x все характеры
#   python tools\lesson_audit.py --chars excellent,offtopic
#   python tools\lesson_audit.py --lessons city/4.3
#   python tools\lesson_audit.py --live --chars excellent
#
# ЗАЧЕМ (слова ученика 22.11.2026): «таких уроков будет полно. Может выработаем
# автотест по паттернам, по которым мы делали проверки, чтобы я не тратил силы
# на живые прогоны?»
#
# Робот проходит урок как ученик с ХАРАКТЕРОМ и проверяет инварианты:
#   1) все вопросы из ask прозвучали, ни один не повторён;
#   2) в фазе «вопросы по сцене» нет хода БЕЗ вопроса, пока вопросы есть;
#   3) урок дошёл до фраз и закрылся (все задания сданы);
#   4) верные ответы не попали в базу ошибок;
#   5) выдуманные вопросы (не про материал) не прозвучали;
#   6) ответ не на вопрос — НЕ зачёт;
#   7) «повтор не помог» не оставляет ученика без задания.
#
# ЧЕГО РОБОТ НЕ ДЕЛАЕТ НИКОГДА: голос (STT/TTS/микрофон/произношение) и
# «звучит ли живо». Это только ученик, живьём.
#
# ДВА РЕЖИМА:
#   --fast (по умолчанию) — модель-заглушка, урок за ~2 секунды. Ловит регрессии.
#   --live               — настоящая модель, 30-60 с на урок. Перед живым уроком.
#
# РЕЗУЛЬТАТ: таблица в консоль (ASCII) и в файл logs/_audit_<дата>_<время>.txt
# =========================================================

import argparse
import datetime
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LOGS = os.path.join(ROOT, "logs")
LIVE_TIMEOUT = 180          # сколько ждём реплику учителя (живой режим)
LIVE_ANALYSIS_WAIT = 3.0    # сколько ждём разбор Аналитика после реплики
MAX_TURNS = 60              # страховка от вечного цикла

# 🔴 ГЛАВНОЕ ПРАВИЛО ИНСТРУМЕНТА: запись в профиль и статистику ВЫКЛЮЧЕНА.
# 22.11.2026 прогон с user_id=1 положил фальшивые «успехи» в живой
# student_profile.json. Здесь считаем ЛЮБУЮ попытку записи — и показываем.
WRITES = {"profile": 0, "stats": 0}


WRITE_CALLS = []


def _no_profile_write(*a, **k):
    WRITES["profile"] += 1
    try:
        tag = str(a[0])[:40] if a else "?"
        errs = 0
        if a and isinstance(a[0], dict):
            errs = len(a[0].get("errors") or [])
        WRITE_CALLS.append((tag, errs))
    except Exception:
        pass
    return []


def _no_stats_write(*a, **k):
    WRITES["stats"] += 1
    return {}


import profile_store                            # noqa: E402
profile_store.record_from_dialogue = _no_profile_write
profile_store.record_analysis = _no_profile_write
profile_store.load = lambda user_id=None: {
    "mistakes": {"grammar": [], "vocabulary": [], "pronunciation": []},
    "strengths": [], "topics_passed": [], "total_lessons": 0,
}

import stats_store                              # noqa: E402
stats_store.drill_ok = _no_stats_write
stats_store.drill_fail = _no_stats_write

import lesson as lesson_mod                     # noqa: E402
import lesson_material                          # noqa: E402
import config                                   # noqa: E402
import llm_client                               # noqa: E402
from roles.analyst import Analyst               # noqa: E402
import scene_material as sm                     # noqa: E402
import translate_task                           # noqa: E402
from controllers import chat_controller as cc   # noqa: E402
from ui import app as app_mod                   # noqa: E402

CHARS = [
    ("excellent", "отличник"),
    ("average", "троечник"),
    ("offtopic", "невпопад"),
    ("silent", "молчун"),
    ("russian", "иностранец"),
    ("provoker", "провокатор"),
]
CHAR_RU = dict(CHARS)

# Верные ответы по вопросам урока (для отличника). Уроков пока три; новый урок
# без ответов идёт на общей фразе — прогон всё равно проверяет инварианты.
LIVE_ANSWERS = {
    "city/4.1": {
        "which house is bigger, the blue one or the yellow one":
            "The blue one is bigger.",
        "which house has the biggest garden":
            "The blue house has the biggest garden on the street.",
        "which house would you take and why":
            "I would take the blue house, it is bigger and the garden is great.",
    },
    "city/4.2": {
        "which phone would you take and why":
            "I would take the black phone, the camera is better.",
        "what is worse about the cheap phone":
            "The battery is worse and the camera is bad.",
        "was ann's old phone better or worse than these two":
            "Her old phone was worse than these two.",
    },
    "city/4.3": {
        "which phone did ann take": "She took the black one.",
        "what is worse about the small phone": "The battery is worse.",
        "would you take the expensive phone or the cheap one":
            "I would take the expensive one, the camera is better.",
    },
}
GENERIC_GOOD = "I would take this one, it looks good."


# ---------- материал ----------
def lessons_with_scene():
    """Все уроки, где есть «вопросы по сцене». Список НЕ хардкодим."""
    out = []
    for lesson_id in lesson_material.covered_lessons():
        material = lesson_material.get(lesson_id) or {}
        if material.get("scene") and material.get("ask"):
            out.append(lesson_id)
    return out


def make_session(lesson_id):
    material = lesson_material.get(lesson_id) or {}
    session = lesson_mod.LessonSession(
        lesson_id, lesson_type=lesson_mod.SPEAKING,
        title=str(material.get("title") or ""),
        topic=str(material.get("topic") or ""))
    session.set_tasks_total(lesson_material.tasks_count(lesson_id))
    return session


def make_payload(lesson_id):
    material = lesson_material.get(lesson_id) or {}
    return {
        "title": material.get("title"), "type": lesson_id,
        "topic": material.get("topic"), "lesson_id": lesson_id,
        "scene": material.get("scene"),
        "ask": [str(x) for x in (material.get("ask") or [])],
        "words": material.get("words"),
        "ask_done": 0, "task_phase": "ask",
    }


# ---------- характеры ----------
def _break_form(want):
    """Испортить ФОРМУ верной фразы (троечник): more better, he don't и т.п."""
    pairs = [
        (" is ", " are "), (" was ", " were "), (" has ", " have "),
        (" does ", " do "), (" bigger", " more bigger"),
        (" better", " more better"), (" cheaper", " more cheaper"),
    ]
    for old, new in pairs:
        if old in want:
            return want.replace(old, new, 1)
    return want + " Please."


def scene_answer(char, turn, question_key, lesson_id):
    """Что робот отвечает в части «вопросы по сцене»."""
    good = (LIVE_ANSWERS.get(lesson_id) or {}).get(question_key) or GENERIC_GOOD
    if char == "excellent":
        return {"text": good, "clarify": False}
    if char == "average":
        return {"text": _break_form(good), "clarify": False}
    if char == "offtopic":
        return {"text": ["I like pizza.",
                         "My cat is sleeping now.",
                         "I want a coffee, please."][turn % 3],
                "clarify": False}
    if char == "silent":
        return {"text": ["ok", "yes", "hmm"][turn % 3], "clarify": False}
    if char == "russian":
        return {"text": ["Ya ne znayu, skazhi po-russki.",
                         "Можно ещё раз?",
                         "Я не знаю."][turn % 3],
                "clarify": False}
    # провокатор: через ход переспрашивает, потом отвечает по делу
    if turn % 2 == 1:
        return {"text": ["Why?", "Почему? Не понял.",
                         "Can you say it in Russian?"][turn % 3],
                "clarify": True}
    return {"text": good, "clarify": False}


def phrase_answer(char, turn, phrase):
    """Ответ на русскую фразу в части перевода."""
    want = str((phrase or {}).get("en") or "")
    if char == "excellent":
        return want
    if char == "average":
        return _break_form(want)
    if char == "offtopic":
        return "I like pizza."
    if char == "silent":
        return "ok"
    if char == "russian":
        return "Я не знаю."
    return want if turn % 2 == 0 else "Why?"


def analyst_for(char, text, question, clarify=False):
    """Разбор «Аналитика» для быстрого режима (его играем мы, модель не зовём)."""
    result = {
        "ok": True, "answer_state": lesson_mod.ANSWER_CORRECT,
        "errors": [], "question_ok": True, "question": question,
        "move_type": "A", "move_status": "Y",
    }
    if clarify:
        result["move_type"] = "Q"
    if char == "average":
        result["errors"] = [{"type": "grammar", "wrong": "are", "correct": "is",
                             "note": "форма", "rule": "comparison"}]
    # «молчун» отвечает «ok» / «yes» / «hmm» — это НЕ ответ на вопрос, и
    # настоящий Аналитик вернул бы question_ok=False. 24.11.2026 робот
    # показал, что при True (§93) такие реплики засчитывались.
    if char in ("offtopic", "russian", "silent"):
        result["question_ok"] = False
    return result


# ---------- модель-заглушка (злой сценарий) ----------
class ScriptLLM:
    """Модель-заглушка: ведёт урок, но нарочно ошибается.

    Паттерн повторяет три живые аварии 22.11.2026: повтор вопроса, реплика без
    вопроса, вопрос не про материал. Код обязан выкрутиться сам.
    """

    PATTERN = ["good", "repeat", "good", "silent", "offmaterial", "good"]

    def __init__(self, ask):
        self.ask = [str(x) for x in (ask or [])] or ["Which one?"]
        self.calls = 0
        self.last = ""

    def complete(self, messages, max_tokens=None, **kwargs):
        if max_tokens is not None and int(max_tokens) <= 4:
            return True, "YES"          # короткий вызов — судья §89
        kind = self.PATTERN[self.calls % len(self.PATTERN)]
        self.calls += 1
        if kind == "repeat" and self.last:
            return True, self.last
        if kind == "silent":
            return True, "That is correct."
        if kind == "offmaterial":
            return True, "That is correct. What colour is it?"
        question = self.ask[(self.calls - 1) % len(self.ask)]
        self.last = question
        return True, "Good. " + question


# ---------- заглушка окна ----------
class FakeBar:
    def set_progress(self, *a, **k):
        return None


class FakeLesson:
    def __init__(self, session):
        self.session = session

    def current(self):
        return self.session

    def credit_finished(self):
        return True


class FakeApp:
    """Только то, что нужно уроку. Логика — НАСТОЯЩАЯ (методы из ui/app.py)."""

    _material_of = app_mod.EnglishTeacherApp._material_of
    _material_ask_left = app_mod.EnglishTeacherApp._material_ask_left
    _scene_asked_count = app_mod.EnglishTeacherApp._scene_asked_count
    _start_material_translate = app_mod.EnglishTeacherApp._start_material_translate
    _translate_ask = app_mod.EnglishTeacherApp._translate_ask
    _current_phrase = app_mod.EnglishTeacherApp._current_phrase
    _translate_reply = app_mod.EnglishTeacherApp._translate_reply
    _translate_pass = app_mod.EnglishTeacherApp._translate_pass
    _translate_miss = app_mod.EnglishTeacherApp._translate_miss
    _after_credit = app_mod.EnglishTeacherApp._after_credit
    _credit_task = app_mod.EnglishTeacherApp._credit_task
    _close_lesson_after_credit = app_mod.EnglishTeacherApp._close_lesson_after_credit
    _task_from_analysis = app_mod.EnglishTeacherApp._task_from_analysis
    _off_topic_miss = app_mod.EnglishTeacherApp._off_topic_miss

    teacher_name = "Verbot"

    def __init__(self, session):
        self.session = session
        self.lesson = FakeLesson(session)
        self.lesson_bar = FakeBar()
        self.chat = None
        self.messages = []
        self.records = []
        self._last_student_text = ""
        self._speech_busy = False
        self._reply_in_flight = False
        self._lesson_closing = False
        self._asked_repeat = ""
        self._lesson_payload = None
        self.current_user = {"id": None}

    # --- заглушки окна: звук, панели, промпт ---
    def add_message(self, who, text):
        self.messages.append((who, text))

    def _say(self, *a, **k):
        return None

    def _say_after_current(self, *a, **k):
        return None

    def _offer_alts(self, *a, **k):
        return None

    def _sync_lesson_prompt(self, *a, **k):
        return None

    def _meaning_second_look(self, *a, **k):
        """«Похоже, но не точно» — в аудите модель НЕ зовём (это не голос)."""
        return False

    def _translate_record(self, session, text, phrase):
        self.records.append({"text": text, "want": (phrase or {}).get("en")})
        return True


# ---------- прогон ----------
def _say(app, ctl, replies, text, send):
    """Отправить реплику ученика и дождаться ответа учителя."""
    before = len(replies)
    if send is None:
        ctl._worker(text)
        return replies[-1] if len(replies) > before else None
    send(text)
    started = time.time()
    while len(replies) == before and time.time() - started < LIVE_TIMEOUT:
        time.sleep(0.2)
    return replies[-1] if len(replies) > before else None


def _driver(app, ctl, session, lesson_id, char, ask, replies, payload, send=None,
            analyses=None):
    """Прогнать урок целиком: вопросы по сцене -> фразы -> закрытие."""
    ask_keys = set(sm.norm_question(q) for q in ask)
    out = {
        "lesson": lesson_id, "char": char, "question": "",
        "ask_total": len(ask), "asked": 0, "repeats": 0, "silence": 0,
        "invented": 0, "transitioned": False,
        "done": 0, "total": int(getattr(session, "tasks_total", 0) or 0),
        "problems": [], "invented_list": [],
    }
    seen = []
    turns = 0
    student_text = "Hello!"

    while turns < MAX_TURNS:
        turns += 1
        payload["ask_done"] = int(getattr(session, "tasks_done", 0) or 0)
        ctl.set_lesson(payload)
        # живому Аналитику нужен текст, который сейчас отправляем (§89)
        app._last_student_text = student_text
        try:
            session.register_reply()
        except Exception:
            pass
        reply = _say(app, ctl, replies, student_text, send)
        if reply is None:
            out["problems"].append("учитель не ответил (ход %d)" % turns)
            break

        question = ctl._question_of(reply)
        key = sm.norm_question(question)
        left = app._material_ask_left(session)

        if key:
            if key in seen:
                out["repeats"] += 1
                out["problems"].append("ПОВТОР вопроса (ход %d)" % turns)
            if key not in ask_keys:
                # Инвариант 5 — про ВЫДУМАННЫЕ вопросы (о том, чего нет в
                # сцене). Вопрос ПРО материал задавать можно, даже если его
                # нет в ask: так решил ученик 22.11.2026 (§91.7).
                outside, culprit = sm.outside_material(question, payload)
                if outside:
                    out["invented"] += 1
                    out["invented_list"].append(question)
                    out["problems"].append(
                        "выдуманный вопрос (%s, ход %d): %s"
                        % (culprit, turns, question[:60]))
            seen.append(key)
        elif left > 0:
            out["silence"] += 1
            out["problems"].append(
                "ход БЕЗ вопроса, а вопросов ещё %d (ход %d)" % (left, turns))

        if left == 0:
            out["transitioned"] = bool(app._start_material_translate(session))
            if not out["transitioned"]:
                out["problems"].append("вопросы кончились, а на фразы не перешёл")
            break

        # ученик отвечает
        answer = scene_answer(char, turns, key, lesson_id)
        student_text = answer["text"]
        if send is None:
            before_done = int(session.tasks_done or 0)
            tries_before = int(session.task_attempts or 0)
            app._task_from_analysis(
                analyst_for(char, student_text, question, answer["clarify"]))
            credited = int(session.tasks_done or 0) > before_done
            on_topic = (bool(key) and not answer["clarify"]
                        and char in ("excellent", "average", "provoker"))
            if credited and not on_topic:
                if tries_before + 1 < lesson_mod.MAX_TASK_ATTEMPTS:
                    out["problems"].append(
                        "ответ НЕ на вопрос засчитан (ход %d, попытка %d)"
                        % (turns, tries_before + 1))
        else:
            if analyses is not None:
                wait_analysis(analyses, turns)

    # ---- часть 2: русские фразы на перевод ----
    if out["transitioned"]:
        guard = 0
        while getattr(session, "is_active", False) and guard < MAX_TURNS:
            guard += 1
            phrase = app._current_phrase(session) or {}
            text = phrase_answer(char, guard, phrase)
            app._last_student_text = text
            try:
                session.register_reply()
            except Exception:
                pass
            app._translate_reply(text)
        if not getattr(session, "finished", False):
            out["problems"].append(
                "урок НЕ закрылся: %d/%d" % (session.tasks_done,
                                             session.tasks_total))

    out["done"] = int(getattr(session, "tasks_done", 0) or 0)
    out["asked"] = len(set(seen))
    if out["asked"] < len(ask):
        out["problems"].append("прозвучало вопросов %d из %d"
                               % (out["asked"], len(ask)))
    return out


def wait_analysis(analyses, turns):
    """Живой режим: дождаться разбора Аналитика (он ставит зачёт)."""
    if analyses is None:
        return
    started = time.time()
    before = analyses[0]
    while analyses[0] == before and time.time() - started < LIVE_ANALYSIS_WAIT:
        time.sleep(0.1)


def run_fast(lesson_id, char):
    ask = [str(x) for x in (lesson_material.ask(lesson_id) or [])]
    session = make_session(lesson_id)
    ctl = cc.ChatController(ScriptLLM(ask), dispatch=lambda fn: fn(),
                            mode="lesson", lang="en", user_id=None)
    payload = make_payload(lesson_id)
    ctl.set_lesson(payload)
    replies = []
    ctl.on_response = lambda user_text, reply: replies.append(reply)
    app = FakeApp(session)
    app.chat = ctl
    return _driver(app, ctl, session, lesson_id, char, ask, replies, payload)


def run_live(lesson_id, char):
    ask = [str(x) for x in (lesson_material.ask(lesson_id) or [])]
    session = make_session(lesson_id)
    llm = llm_client.LLMClient()
    analyst = Analyst(llm) if getattr(config, "ANALYST_ENABLED", True) else None
    ctl = cc.ChatController(llm, dispatch=lambda fn: fn(),
                            mode="lesson", lang="en", user_id=None,
                            analyst=analyst)
    payload = make_payload(lesson_id)
    ctl.set_lesson(payload)
    replies = []
    analyses = [0]
    ctl.on_response = lambda user_text, reply: replies.append(reply)
    app = FakeApp(session)
    app.chat = ctl

    def _on_analysis(result):
        analyses[0] += 1
        if not result:
            return None
        # Фразы на перевод засчитывает ПРИЛОЖЕНИЕ по эталону (§82); разбор
        # Аналитика к ним не применяем, иначе зачёт придёт дважды.
        if str(getattr(session, "task_phase", "")) != lesson_mod.TASK_ASK:
            return None
        return app._task_from_analysis(result)

    ctl.on_analysis = _on_analysis
    return _driver(app, ctl, session, lesson_id, char, ask, replies, payload,
                   send=ctl.send, analyses=analyses)


# ---------- проверка «ложные правки в базу» ----------
FALSE_ONCE = [
    {"wrong": "bad", "correct": "poor",
     "note": "More natural adjective for battery life", "rule": "word_choice"},
    {"wrong": "took", "correct": "take",
     "note": "Should use base form if context implies present",
     "rule": "verb_form"},
    {"wrong": "the expensive phone", "correct": "an expensive phone",
     "note": "Use 'an' before a vowel sound.", "rule": "article"},
    {"wrong": "the small phone", "correct": "a small phone",
     "note": "Use 'a' for non-specific thing", "rule": "article"},
    {"wrong": "take", "correct": "buy",
     "note": "buy is more natural here", "rule": "word_choice"},
]
REAL_ONCE = [
    {"wrong": "he don't", "correct": "he doesn't", "note": "do/does",
     "rule": "verb_form"},
    {"wrong": "i am go", "correct": "i am going", "note": "время",
     "rule": "tense"},
]


def check_soft_errors():
    """Инвариант 4: подсказки и артикли в фазе вопросов в базу НЕ идут."""
    ctl = cc.ChatController.__new__(cc.ChatController)
    ctl._lesson = {"scene": [{"en": "x"}], "task_phase": "ask"}

    def kept(errors):
        return ctl._drop_soft_errors({"ok": True, "errors": list(errors)})["errors"]

    bad = [item for item in FALSE_ONCE if kept([item])]
    lost = [item for item in REAL_ONCE if not kept([item])]
    return bad, lost


# ---------- отчёт ----------
def verdict_of(res):
    return "FAIL" if res["problems"] else "OK"


def format_report(results, mode, args_line):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    bad_soft, lost_real = check_soft_errors()
    lines = []
    lines.append("=" * 78)
    lines.append("УЧЕНИК-РОБОТ: АУДИТ УРОКОВ — %s (режим: %s)" % (now, mode))
    lines.append("Запуск: %s" % args_line)
    lines.append("=" * 78)
    lines.append("")
    lines.append("урок        характер    вопросов  повтор  молчание  выдумка  "
                 "фразы  сдано  вердикт")
    lines.append("-" * 78)
    for res in results:
        lines.append("%-11s %-10s %d/%-7d %-7d %-9d %-8d %-6s %d/%-4d %s"
                     % (res["lesson"], CHAR_RU.get(res["char"], res["char"]),
                        res["asked"], res["ask_total"], res["repeats"],
                        res["silence"], res["invented"],
                        "да" if res["transitioned"] else "НЕТ",
                        res["done"], res["total"], verdict_of(res)))
    lines.append("-" * 78)
    lines.append("")
    lines.append("ПРОВЕРКА «ЛОЖНЫЕ ПРАВКИ В БАЗУ» (инвариант 4):")
    if not bad_soft:
        lines.append("  ✅ 5 ложных правок 22.11.2026 (bad->poor, took->take, "
                     "the->a, the small phone, take->buy) отсекаются")
    else:
        lines.append("  ❌ ПРОШЛИ В БАЗУ: %s"
                     % ", ".join("%s->%s" % (i["wrong"], i["correct"])
                                 for i in bad_soft))
    if not lost_real:
        lines.append("  ✅ настоящие ошибки (he don't, i am go) НЕ отсекаются")
    else:
        lines.append("  ❌ ПОТЕРЯНЫ настоящие: %s"
                     % ", ".join("%s->%s" % (i["wrong"], i["correct"])
                                 for i in lost_real))
    if WRITES["profile"] or WRITES["stats"]:
        with_err = sum(1 for _t, errs in WRITE_CALLS if errs)
        lines.append("  ⚠️ перехвачено попыток записи: профиль %d "
                     "(с ошибками %d), статистика %d — в базу НЕ пошли"
                     % (WRITES["profile"], with_err, WRITES["stats"]))
    else:
        lines.append("  ✅ записей в профиль/статистику НЕТ (0 попыток)")
    lines.append("")
    fails = [r for r in results if r["problems"]]
    if fails:
        lines.append("ЧТО НЕ ТАК (%d):" % len(fails))
        for res in fails:
            lines.append("  [%s / %s]" % (res["lesson"],
                                          CHAR_RU.get(res["char"], res["char"])))
            for item in res["problems"]:
                lines.append("    - %s" % item)
    else:
        lines.append("ВСЕ ПРОГОНЫ ПРОЙДЕНЫ: инварианты 1-7 держатся.")
    lines.append("")
    lines.append("НАПОМИНАНИЕ: голос (STT/TTS/микрофон/произношение) робот "
                 "НЕ проверяет — это только живьём.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Ученик-робот: аудит уроков по инвариантам (§92)")
    parser.add_argument("--live", action="store_true",
                        help="живой режим: настоящая модель (медленно)")
    parser.add_argument("--lessons", default="all",
                        help="город/урок через запятую или all")
    parser.add_argument("--chars", default="all",
                        help="характеры через запятую или all")
    args = parser.parse_args()

    lessons = lessons_with_scene()
    if args.lessons != "all":
        wanted = [s.strip() for s in args.lessons.split(",") if s.strip()]
        lessons = [s for s in lessons if s in wanted]
    chars = [k for k, _ in CHARS]
    if args.chars != "all":
        wanted = [s.strip() for s in args.chars.split(",") if s.strip()]
        chars = [c for c in chars if c in wanted]

    if not lessons:
        print("Нет уроков со сценой и вопросами — проверять нечего.")
        return 1
    if not chars:
        print("Нет таких характеров: %s" % args.chars)
        return 1

    mode = "живой" if args.live else "быстрый"
    runner = run_live if args.live else run_fast
    print("УЧЕНИК-РОБОТ (%s): уроков %d, характеров %d"
          % (mode, len(lessons), len(chars)))
    results = []
    for lesson_id in lessons:
        for char in chars:
            started = time.time()
            result = runner(lesson_id, char)
            result["seconds"] = round(time.time() - started, 1)
            results.append(result)
            print("%-11s %-10s ask %d/%d rep %d sil %d inv %d done %d/%d  %s"
                  % (lesson_id, char, result["asked"], result["ask_total"],
                     result["repeats"], result["silence"], result["invented"],
                     result["done"], result["total"], verdict_of(result)))

    report = format_report(results, mode, " ".join(sys.argv[1:]) or "(без ключей)")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(LOGS, "_audit_%s.txt" % stamp)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print()
    print("отчёт: %s" % path)
    fails = [r for r in results if r["problems"]]
    print("итог: %d прогонов, %d с замечаниями" % (len(results), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
