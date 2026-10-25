# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_ANALYST_DISFLUENCY.PY — Аналитик не считает запинку ошибкой
# =========================================================
#   python tests\test_analyst_disfluency.py
#
# ЗАЧЕМ. Жалоба ученика 25.10.2026: он запнулся («the park in the park»), а
# ошибка попала в счёт. ЗАМЕР на живой модели: Аналитик возвращал «ошибку»
# 4 раза из 4, причём в одном ответе было
#   {"wrong": "in the park", "correct": "in the park"}  ← ошибки НЕТ ВООБЩЕ
# Такая «ошибка» уходила в счётчик ошибок занятия и в профиль («что закрепить»).
#
# Решения ученика: запинку НЕ склеивать (текст уходит модели как сказан), на
# всех уровнях НЕ замечать.
#
# Проверяем:
#   1) запись — не ошибка: «in the park» → «in the park»;
#   2) чистый повтор — не ошибка: «in the park in the park» → «in the park»;
#   3) форма «правильный вариант — кусок сказанного» — не ошибка;
#   4) НАСТОЯЩИЕ ошибки остаются (go→went, park→the park, don't→doesn't);
#   5) _clean_errors выбрасывает запинку и оставляет живую ошибку;
#   6) в промпте Аналитика есть правило про запинки;
#   7) цепочка analyze(): модель вернула запинку → errors=[] в разборе.
# Модель, микрофон и Tk не нужны.
# =========================================================

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from roles.analyst import Analyst, is_disfluency, _clean_errors   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete(self, prompt, max_tokens=None, temperature=None, stop=None,
                 timeout=None):
        return True, self.payload


HESITATION = "sometimes we meet in the city center or the park in the park"


def main():
    # ---------- 1-2. формы запинки ----------
    print("[1] Запись и повтор — не ошибка")
    pairs = [
        ("in the park", "in the park"),
        ("in the park in the park", "in the park"),
        ("the park in the park", "the park"),
        ("the park in the park", "in the park"),
        ("or the park in the park", "or the park"),
        ("I I think so", "I think so"),
        ("very very good", "very good"),
        ("in the park.", "In the park"),
    ]
    for wrong, correct in pairs:
        check("%r → %r" % (wrong, correct), is_disfluency(wrong, correct),
              is_disfluency(wrong, correct))

    # ---------- 3-4. настоящие ошибки не глушим ----------
    print("\n[2] Настоящие ошибки остаются ошибками")
    real = [
        ("go", "went"),
        ("park", "the park"),
        ("the park", "park"),
        ("I goed home", "I went home"),
        ("I goed to school yesterday", "I went to school yesterday"),
        ("She don't like it", "She doesn't like it"),
        ("I like dogs", "I like cats"),
        ("", "to"),
        ("to", ""),
    ]
    for wrong, correct in real:
        check("%r → %r остаётся ошибкой" % (wrong, correct),
              not is_disfluency(wrong, correct), is_disfluency(wrong, correct))

    # ---------- 5. фильтр в нормализации ----------
    print("\n[3] _clean_errors выбрасывает запинку")
    got = _clean_errors([
        {"type": "grammar", "wrong": "in the park", "correct": "in the park",
         "note": "Redundant preposition use"},          # ровно то, что вернула модель
        {"type": "grammar", "wrong": "the park in the park",
         "correct": "the park", "note": "Redundant use of 'the park'"},
        {"type": "grammar", "wrong": "goed", "correct": "went", "note": "tense"},
    ])
    check("осталась ровно одна ошибка", len(got) == 1, got)
    check("осталась настоящая (goed → went)",
          got and got[0].get("wrong") == "goed", got)

    # ---------- 6. правило в промпте ----------
    print("\n[4] Правило в промпте Аналитика")
    prompt = Analyst(None).build_prompt(HESITATION, "That sounds fun!", "A2")
    check("есть пункт про запинки", "Speech hesitations" in prompt,
          prompt[:200])
    check("сказано: повтор — НЕ ошибка", "NOT an error" in prompt)
    check("старые правила целы", "Never invent errors" in prompt
          and "ONLY move_type A" in prompt)

    # ---------- 7. цепочка analyze ----------
    print("\n[5] analyze(): запинка от модели → errors=[]")
    payload = json.dumps({
        "move_type": "A", "move_status": "P",
        "errors": [{"type": "grammar", "wrong": "the park in the park",
                    "correct": "the park", "note": "Redundant use"}],
        "topics": ["park"], "note": ""})
    res = Analyst(FakeLLM(payload)).analyze(HESITATION)
    check("ошибок нет", res["errors"] == [], res["errors"])
    check("тема сохранилась", "park" in (res.get("topics") or []),
          res.get("topics"))

    payload2 = json.dumps({
        "move_type": "A", "move_status": "P",
        "errors": [{"type": "grammar", "wrong": "goed", "correct": "went",
                    "note": "tense"}], "topics": [], "note": ""})
    res2 = Analyst(FakeLLM(payload2)).analyze("I goed to school yesterday")
    check("настоящая ошибка доходит", len(res2["errors"]) == 1, res2["errors"])

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
