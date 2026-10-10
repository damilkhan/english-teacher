# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PLANNER.PY — проверка роли «Планировщик» (roles/planner.py)
# =========================================================
#   python tests\test_planner.py
#
# Что проверяем:
#   1) корректный JSON плана разбирается (focus/goals/activities/vocab);
#   2) нормализация: лимиты, отсев мусора, обрезка длины;
#   3) JSON вытаскивается из «шумного» ответа модели;
#   4) битый/пустой ответ → пустой план (ok=False), без падений;
#   5) недоступная/падающая LLM → пустой план; не-урок → LLM не зовётся;
#   6) промпт содержит уровень, слабые темы и методичку;
#   7) format_plan собирает текст; для пустого плана — пусто;
#   8) интеграция: ChatController строит план 1 раз и вставляет в промпт.
# =========================================================

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import roles.planner as planner_mod          # noqa: E402
from roles.planner import Planner, parse_plan, format_plan, default_plan  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0
        self.prompts = []

    def complete(self, prompt, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
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


PROFILE = {
    "weak_topics": [{"topic": "family and friends", "correct": 0, "total": 2},
                    {"topic": "food and cooking", "correct": 1, "total": 2}],
    "mistakes": {"grammar": [{"wrong": "go", "correct": "went"}], "vocabulary": []},
    "topics_passed": ["greeting", "identity"],
    "total_lessons": 7,
}


# =========================================================
# 1. Корректный JSON
# =========================================================
def test_parse_valid():
    print("\n[1] Разбор корректного плана")
    raw = ('{"focus": "Present Perfect (daily life)", '
           '"goals": ["Form questions"], '
           '"activities": [{"name": "Warm-up", "task": "Ask about the day", "minutes": 3}], '
           '"target_vocab": ["yet", "already"], "note": "review tense"}')
    plan = Planner(FakeLLM(raw)).plan(PROFILE, level="A2")
    check("focus разобран", plan["focus"] == "Present Perfect (daily life)", plan)
    check("цели разобраны", plan["goals"] == ["Form questions"], plan["goals"])
    check("активность разобрана", plan["activities"][0]["name"] == "Warm-up"
          and plan["activities"][0]["minutes"] == 3, plan["activities"])
    check("лексика разобрана", plan["target_vocab"] == ["yet", "already"], plan["target_vocab"])
    check("ok=True, source=model", plan["ok"] is True and plan["source"] == "model", plan)


# =========================================================
# 2. Нормализация
# =========================================================
def test_normalize():
    print("\n[2] Нормализация (лимиты и мусор)")
    raw = ('{"focus": "X", "goals": ["a","b","c","d","e","a"], '
           '"activities": [{"name":"A","task":"t","minutes":99}, {"name":"","task":""}, '
           '"bad", {"task":"only task"}, {"name":"B","task":"t2","minutes":"abc"}], '
           '"target_vocab": [' + ",".join('"w%d"' % i for i in range(20)) + '], "note": "n"}')
    plan = parse_plan(raw)
    check("цели ограничены 4 и без дублей", len(plan["goals"]) == 4 and "a" in plan["goals"], plan["goals"])
    check("минуты зажаты в 0..15", plan["activities"][0]["minutes"] == 15, plan["activities"][0])
    check("пустые активности отброшены", all(a.get("task") or a.get("name") for a in plan["activities"]), plan["activities"])
    check("активность без имени → 'Activity'", plan["activities"][0]["name"] == "A", plan["activities"])
    check("нечисловые минуты → 0", any(a["minutes"] == 0 for a in plan["activities"]), plan["activities"])
    check("лексика ограничена 12", len(plan["target_vocab"]) == 12, len(plan["target_vocab"]))


# =========================================================
# 3. JSON из шума
# =========================================================
def test_noisy_json():
    print("\n[3] JSON из «шумного» ответа")
    fence = chr(96) * 3
    raw = ("Sure!\n" + fence + "json\n"
           '{"focus": "Travel", "goals": [], "activities": [], "target_vocab": [], "note": ""}\n'
           + fence)
    plan = Planner(FakeLLM(raw)).plan(PROFILE)
    check("разобрано сквозь markdown", plan["ok"] and plan["focus"] == "Travel", plan)


# =========================================================
# 4. Битый ответ
# =========================================================
def test_broken():
    print("\n[4] Битый/пустой ответ → пустой план")
    for raw in ("{ not json", "", "no braces", "[]", None, "[1,2,3]"):
        plan = Planner(FakeLLM(raw)).plan(PROFILE)
        ok = (plan["ok"] is False and plan["focus"] == "" and plan["goals"] == []
              and plan["source"] == "fallback")
        check("пустой план для %r" % (raw,), ok, plan)


# =========================================================
# 5. Проблемы LLM и режим
# =========================================================
def test_llm_failures():
    print("\n[5] Недоступная LLM → пустой план; не-урок LLM не зовёт")
    for llm in (DeadLLM(), BoomLLM(), None):
        name = type(llm).__name__ if llm is not None else "None"
        plan = Planner(llm).plan(PROFILE)
        check("%s → пустой план" % name, plan["ok"] is False, plan)

    trap = TrapLLM()
    plan = Planner(trap).plan(PROFILE, mode="free")
    check("свободный режим → LLM не вызвана", plan["ok"] is False)


# =========================================================
# 6. Промпт
# =========================================================
def test_prompt():
    print("\n[6] Промпт Планировщика")
    p = Planner(None).build_prompt(PROFILE, level="B1",
                                   context="TASK CYCLE: pre-task, task, language focus")
    check("уровень в промпте", "CEFR level: B1" in p, p[:120])
    check("слабые темы в промпте", "family and friends" in p and "food and cooking" in p)
    check("ошибки в промпте", "go -> went" in p)
    check("методичка в промпте", "METHODOLOGY NOTES" in p and "TASK CYCLE" in p)
    check("требуется только JSON", "Return ONLY valid JSON" in p)
    check("Планировщик не тянет RAG сам (модуль не импортирует rag)",
          "rag" not in vars(planner_mod))


# =========================================================
# 7. format_plan
# =========================================================
def test_format():
    print("\n[7] format_plan")
    plan = {"focus": "Past Simple", "goals": ["g1", "g2"],
            "activities": [{"name": "Warm-up", "task": "talk", "minutes": 3}],
            "target_vocab": ["yesterday"], "note": "aim", "ok": True, "source": "model"}
    text = format_plan(plan)
    check("есть фокус", "Focus: Past Simple" in text, text)
    check("есть цели", "Goals: g1; g2" in text, text)
    check("есть активность с минутами", "Warm-up: talk (3 min)" in text, text)
    check("есть лексика", "Target vocabulary: yesterday" in text, text)
    check("пустой план → пустой текст", format_plan(default_plan()) == "")
    check("None → пустой текст", format_plan(None) == "")


# =========================================================
# 8. Интеграция с ChatController
# =========================================================
def test_chat_integration():
    print("\n[8] Интеграция: ChatController + Планировщик")
    from controllers.chat_controller import ChatController
    import profile_store
    import user_manager

    class CaptureLLM:
        def __init__(self):
            self.prompts = []
        def complete(self, prompt, **kwargs):
            self.prompts.append(prompt)
            return True, "ok"

    class StubPlanner:
        def __init__(self):
            self.calls = 0
        def plan(self, profile, level=None, mode="lesson", context=""):
            self.calls += 1
            return {"focus": "Past Simple", "goals": ["g1"],
                    "activities": [{"name": "Warm-up", "task": "talk", "minutes": 3}],
                    "target_vocab": ["yesterday"], "note": "", "ok": True, "source": "model"}
        def format_plan(self, plan):
            return format_plan(plan)

    real_dir, real_last = user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE
    tmp = tempfile.mkdtemp(prefix="et_planner_")
    try:
        user_manager.PROFILES_DIR = tmp
        user_manager.LAST_USER_FILE = os.path.join(tmp, "last_user.txt")
        profile_store.set_active_user(None)
        uid = user_manager.create_user("Тест", "other", 20, "A2", "", "🙂")["id"]

        def mute(chat):
            for cb in ("on_message", "on_status", "on_busy", "on_response", "on_analysis"):
                setattr(chat, cb, lambda *a: None)

        def send_and_wait(chat, text):
            chat.send(text)
            deadline = time.time() + 5
            while chat.busy and time.time() < deadline:
                time.sleep(0.02)

        def wait_for(pred, timeout=5.0):
            end = time.time() + timeout
            while time.time() < end:
                if pred():
                    return True
                time.sleep(0.02)
            return pred()

        llm = CaptureLLM()
        stub = StubPlanner()
        chat = ChatController(llm=llm, dispatch=lambda fn: fn(), mode="lesson",
                              lang="en", user_id=uid, planner=stub)
        mute(chat)
        send_and_wait(chat, "Hello Jane")
        check("первый ответ БЕЗ плана (план — в фоне после ответа)",
              "TODAY'S LESSON PLAN" not in llm.prompts[0], llm.prompts[0][-160:])
        wait_for(lambda: stub.calls >= 1)     # ждём фоновое построение плана
        check("план строится один раз за сессию (в фоне)", stub.calls == 1, stub.calls)
        send_and_wait(chat, "Let's continue")
        check("со 2-го хода план в промпте",
              "TODAY'S LESSON PLAN" in llm.prompts[-1]
              and "Past Simple" in llm.prompts[-1], llm.prompts[-1][-200:])

        # смена ученика → новый план
        user_manager.create_user("Второй", "other", 20, "B1", "", "🙂")
        chat.set_user(2)
        send_and_wait(chat, "Hi again")
        wait_for(lambda: stub.calls >= 2)
        check("после смены ученика план строится заново", stub.calls == 2, stub.calls)

        # свободный режим — плана нет
        llm2 = CaptureLLM()
        stub2 = StubPlanner()
        chat2 = ChatController(llm=llm2, dispatch=lambda fn: fn(), mode="free",
                               lang="en", user_id=uid, planner=stub2)
        mute(chat2)
        send_and_wait(chat2, "just chatting")
        check("в свободном режиме плана нет",
              "TODAY'S LESSON PLAN" not in llm2.prompts[0], llm2.prompts[0][-200:])
        check("в свободном режиме Планировщик не зовётся", stub2.calls == 0, stub2.calls)
    finally:
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE = real_dir, real_last
        profile_store.set_active_user(None)


def main():
    print("=" * 60)
    print("Проверка роли «Планировщик» (roles/planner.py)")
    print("=" * 60)

    test_parse_valid()
    test_normalize()
    test_noisy_json()
    test_broken()
    test_llm_failures()
    test_prompt()
    test_format()
    test_chat_integration()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
