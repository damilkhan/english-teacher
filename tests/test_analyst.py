# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_ANALYST.PY — проверка роли «Аналитик» (roles/analyst.py)
# =========================================================
#   python tests\test_analyst.py
#
# Что проверяем:
#   1) корректный JSON разбирается (move_type/move_status/errors/topics);
#   2) правило таксономии: только Answer/Attempt (A) оценивается A/P, прочее N;
#   3) JSON вытаскивается из «шумного» ответа модели;
#   4) битый/пустой ответ → нейтральный дефолт, без падений;
#   5) недоступная/падающая/пустая LLM → дефолт; пустая реплика LLM не зовёт;
#   6) record_analysis пишет прогресс (ошибки, темы, история, «занятие»);
#   7) нормализация типов ошибок (spelling→vocabulary, мусор→grammar);
#   8) промпт содержит словарь таксономии; Аналитик НЕ использует RAG;
#   9) интеграция: ChatController зовёт Аналитика и пишет прогресс.
# =========================================================

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# консоль Windows по умолчанию cp1251 — без этого падаем на эмодзи
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import profile_store            # noqa: E402
import user_manager             # noqa: E402
import roles.analyst as analyst_mod  # noqa: E402
from roles.analyst import Analyst    # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


# ---------- подставные LLM-клиенты ----------
class FakeLLM:
    """Всегда возвращает заданную строку (ok=True)."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete(self, prompt, max_tokens=None, temperature=None, stop=None, timeout=None):
        self.calls += 1
        return True, self.payload


class DeadLLM:
    def complete(self, *a, **k):
        return False, "offline"


class BoomLLM:
    def complete(self, *a, **k):
        raise RuntimeError("boom")


class TrapLLM:
    def complete(self, *a, **k):
        raise AssertionError("LLM не должна вызываться")


class temp_profile_dir:
    """Временная папка профилей: реальные файлы учеников не трогаем."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_analyst_")
        self.real = (user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE)
        user_manager.PROFILES_DIR = self.dir
        user_manager.LAST_USER_FILE = os.path.join(self.dir, "last_user.txt")
        profile_store.set_active_user(None)
        return self.dir

    def __exit__(self, *exc):
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE = self.real
        profile_store.set_active_user(None)


# =========================================================
# 1. Корректный JSON
# =========================================================
def test_parse_valid():
    print("\n[1] Разбор корректного JSON")
    raw = ('{"move_type": "A", "move_status": "P", '
           '"errors": [{"type": "spelling", "wrong": "carears", "correct": "careers", "note": "spelling"}], '
           '"topics": ["work and study"], "note": "attempt with a typo"}')
    res = Analyst(FakeLLM(raw)).analyze("I worked as a carears advisor.")
    check("move_type = A", res["move_type"] == "A", res)
    check("move_status = P", res["move_status"] == "P", res)
    check("ошибка разобрана", len(res["errors"]) == 1 and res["errors"][0]["correct"] == "careers", res["errors"])
    check("тема разобрана", res["topics"] == ["work and study"], res["topics"])
    check("ok=True, source=model", res["ok"] is True and res["source"] == "model", res)


# =========================================================
# 2. Правило таксономии
# =========================================================
def test_taxonomy_rule():
    print("\n[2] Правило таксономии: оценивается только Answer/Attempt")
    q = Analyst(FakeLLM('{"move_type": "Q", "move_status": "A", "errors": [], "topics": [], "note": ""}'))
    res = q.analyze("What does flying colours mean?")
    check("Q → статус N", res["move_type"] == "Q" and res["move_status"] == "N", res)

    s = Analyst(FakeLLM('{"move_type": "S", "move_status": "P", "errors": [], "topics": [], "note": ""}'))
    res = s.analyze("I think group one is more emotional.")
    check("S → статус N", res["move_type"] == "S" and res["move_status"] == "N", res)

    a = Analyst(FakeLLM('{"move_type": "A", "move_status": "p", "errors": [], "topics": [], "note": ""}'))
    res = a.analyze("I goed home.")
    check("A + строчная 'p' → P", res["move_status"] == "P", res)

    bad = Analyst(FakeLLM('{"move_type": "A", "move_status": "???", "errors": [], "topics": [], "note": ""}'))
    res = bad.analyze("I goed home.")
    check("A + мусорный статус → N", res["move_status"] == "N", res)

    unknown = Analyst(FakeLLM('{"move_type": "Z", "move_status": "N", "errors": [], "topics": [], "note": ""}'))
    res = unknown.analyze("hello there")
    check("неизвестный move_type → O", res["move_type"] == "O", res)


# =========================================================
# 3. JSON из «шумного» ответа
# =========================================================
def test_noisy_json():
    print("\n[3] JSON вытаскивается из шума")
    fence = chr(96) * 3          # тройной бэктик, но без литералов в исходнике
    raw = ("Sure! Here it is:\n" + fence + "json\n"
           '{"move_type": "S", "move_status": "N", "errors": [], "topics": ["opinions"], "note": "comment"}\n'
           + fence + "\nHope that helps.")
    res = Analyst(FakeLLM(raw)).analyze("I think group one is more emotional.")
    check("разобрано сквозь markdown/текст", res["ok"] and res["move_type"] == "S", res)


# =========================================================
# 4. Битый ответ
# =========================================================
def test_broken_json():
    print("\n[4] Битый/пустой ответ → нейтральный дефолт")
    for raw in ("{ not json", "", "no braces here", "[]", None, "[1, 2, 3]"):
        res = Analyst(FakeLLM(raw)).analyze("I goed home.")
        ok = (res["ok"] is False and res["move_type"] == "O"
              and res["move_status"] == "N" and res["errors"] == [] and res["source"] == "fallback")
        check("дефолт для %r" % (raw,), ok, res)


# =========================================================
# 5. Проблемы LLM
# =========================================================
def test_llm_failures():
    print("\n[5] Недоступная LLM → дефолт, без исключений")
    for llm in (DeadLLM(), BoomLLM(), None):
        res = Analyst(llm).analyze("I goed home.")
        name = type(llm).__name__ if llm is not None else "None"
        check("%s → дефолт" % name, res["ok"] is False and res["move_type"] == "O", res)

    trap = TrapLLM()
    res = Analyst(trap).analyze("    ")
    check("пустая реплика → дефолт и LLM не вызвана", res["ok"] is False)


# =========================================================
# 6. record_analysis пишет прогресс
# =========================================================
def test_record_analysis():
    print("\n[6] record_analysis пишет прогресс")
    with temp_profile_dir():
        uid = 1
        analysis = {
            "move_type": "A", "move_status": "P",
            "errors": [{"type": "grammar", "wrong": "go", "correct": "went", "note": "tense"}],
            "topics": ["travel"], "note": "past tense", "ok": True, "source": "model",
        }
        notes = Analyst(None).apply(analysis, "I go to school yesterday", "Try past simple.", uid)
        prog = profile_store.load(uid)
        check("ошибка grammar записана", len(prog["mistakes"]["grammar"]) == 1, prog["mistakes"]["grammar"])
        check("детали ошибки сохранены",
              prog["mistakes"]["grammar"][0].get("correct") == "went", prog["mistakes"]["grammar"][0])
        check("тема записана в topics_passed", "travel" in prog["topics_passed"], prog["topics_passed"])
        check("total_lessons увеличен (+1 за занятие)", prog["total_lessons"] >= 1, prog["total_lessons"])
        check("заметка для чата непустая", bool(notes), notes)
        check("analysis_log заполнен", len(prog.get("analysis_log", [])) == 1, prog.get("analysis_log"))

        accepted = {"move_type": "A", "move_status": "A", "errors": [],
                    "topics": [], "note": "", "ok": True, "source": "model"}
        Analyst(None).apply(accepted, "I have been learning English for many years now.", "", uid)
        prog = profile_store.load(uid)
        check("принятый ответ без ошибок → strength", len(prog["strengths"]) == 1, prog["strengths"])


# =========================================================
# 7. Нормализация типов ошибок
# =========================================================
def test_error_type_normalization():
    print("\n[7] Нормализация типов ошибок при записи")
    with temp_profile_dir():
        uid = 2
        analysis = {
            "move_type": "A", "move_status": "P",
            "errors": [{"type": "spelling", "wrong": "carears", "correct": "careers"},
                       {"type": "weird", "wrong": "x", "correct": "y"}],
            "topics": [], "note": "", "ok": True, "source": "model",
        }
        Analyst(None).apply(analysis, "a long enough student reply", "", uid)
        prog = profile_store.load(uid)
        check("spelling → vocabulary", len(prog["mistakes"]["vocabulary"]) == 1, prog["mistakes"]["vocabulary"])
        check("неизвестный тип → grammar", len(prog["mistakes"]["grammar"]) == 1, prog["mistakes"]["grammar"])


# =========================================================
# 8. Промпт и изоляция от RAG
# =========================================================
def test_prompt_and_isolation():
    print("\n[8] Промпт содержит словарь; Аналитик не тянет RAG")
    prompt = Analyst(None).build_prompt("I goed home.", "Try again.", "B1")
    check("словарь move_type в промпте",
          all(t in prompt for t in ("Q = question", "A = answer", "S = statement",
                                    "F = feedback", "O = other")), prompt[:200])
    check("правило статуса в промпте", "ONLY move_type A" in prompt)
    check("требуется только JSON", "Return ONLY valid JSON" in prompt)
    check("уровень попал в контекст", "CEFR level: B1" in prompt)
    check("Аналитик не использует RAG (модуль не импортирует rag)",
          "rag" not in vars(analyst_mod))


# =========================================================
# 9. Интеграция с ChatController
# =========================================================
def test_chat_controller_integration():
    print("\n[9] Интеграция: ChatController + Аналитик")
    from controllers.chat_controller import ChatController

    with temp_profile_dir():
        uid = 1
        payload = ('{"move_type": "A", "move_status": "P", '
                   '"errors": [{"type": "grammar", "wrong": "go", "correct": "went", "note": "tense"}], '
                   '"topics": ["travel"], "note": "past tense"}')
        llm = FakeLLM(payload)
        chat = ChatController(llm=llm, analyst=Analyst(llm), mode="lesson",
                              lang="en", user_id=uid)

        messages, analyses = [], []
        chat.on_message = lambda sender, text: messages.append((sender, text))
        chat.on_status = lambda *a: None
        chat.on_busy = lambda *a: None
        chat.on_response = lambda *a: None
        chat.on_analysis = lambda result: analyses.append(result)

        chat.send("I go to school yesterday")
        deadline = time.time() + 5
        while chat.busy and time.time() < deadline:
            time.sleep(0.02)

        check("ответ Учителя показан", any(s == "Джейн" for s, _ in messages), messages)
        check("история диалога заполнена", len(chat.history) >= 2, chat.history)
        check("Аналитик вернул разбор", bool(analyses) and analyses[-1] and analyses[-1].get("ok"), analyses)
        prog = profile_store.load(uid)
        check("прогресс обновлён Аналитиком (grammar)",
              len(prog["mistakes"]["grammar"]) == 1, prog["mistakes"]["grammar"])

        # когда Аналитик «падает» — Учитель всё равно отвечает
        chat2 = ChatController(llm=FakeLLM(payload), analyst=Analyst(DeadLLM()),
                               mode="lesson", lang="en", user_id=uid)
        messages2 = []
        chat2.on_message = lambda s, t: messages2.append((s, t))
        chat2.on_status = lambda *a: None
        chat2.on_busy = lambda *a: None
        chat2.send("Another turn please")
        deadline = time.time() + 5
        while chat2.busy and time.time() < deadline:
            time.sleep(0.02)
        check("Учитель отвечает даже при мёртвом Аналитике",
              any(s == "Джейн" for s, _ in messages2), messages2)


def test_russian_guard():
    print("\n[10] Аналитик не выдумывает английские ошибки в русском тексте")
    raw = ('{"move_type": "A", "move_status": "P", '
           '"errors": [{"type": "grammar", "wrong": "спорсил", "correct": "спросил"}], '
           '"topics": [], "note": ""}')
    res = Analyst(FakeLLM(raw)).analyze("Ты странно мне ответила. Я тебя спорсил")
    check("русский текст → errors=[]", res["errors"] == [], res["errors"])
    check("русский текст → статус N (не оцениваем)", res["move_status"] == "N", res)

    raw2 = ('{"move_type": "A", "move_status": "P", '
            '"errors": [{"type": "grammar", "wrong": "go", "correct": "went"}], '
            '"topics": [], "note": ""}')
    res2 = Analyst(FakeLLM(raw2)).analyze("I go to school yesterday")
    check("английский текст → ошибка и P сохраняются",
          len(res2["errors"]) == 1 and res2["move_status"] == "P", res2)


def main():
    print("=" * 60)
    print("Проверка роли «Аналитик» (roles/analyst.py)")
    print("=" * 60)

    test_parse_valid()
    test_taxonomy_rule()
    test_noisy_json()
    test_broken_json()
    test_llm_failures()
    test_record_analysis()
    test_error_type_normalization()
    test_prompt_and_isolation()
    test_russian_guard()
    test_chat_controller_integration()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
