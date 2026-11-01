# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_SCENE_REVIEW.PY — разбор ошибок В КОНЦЕ сцены (шаг 4)
# =========================================================
#   python tests\test_scene_review.py
#
# Что проверяем:
#   1) промпт: правила + пронумерованные ответы, «не больше 3»;
#   2) разбор JSON: обычный, в ```-блоке, битый, пустой;
#   3) ЦИТАТА сверяется кодом: придуманная фраза выбрасывается;
#   4) «как надо» = «что сказал» → это не правка;
#   5) больше 3 правок не берём, повторы не дублируются;
#   6) текст для чата: цитата в «ёлочках», «ошибок не нашёл» по-русски;
#   7) запись в базу: errors в формате profile_store (rule подберёт gaps);
#   8) окно: разбор запускается В КОНЦЕ и в фоне, по ходу сцены модели нет.
# Модель и Tk не нужны.
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

import config                     # noqa: E402
import lesson                     # noqa: E402
import scene_review as review     # noqa: E402

FAILED = []

ROWS = [
    {"q": "How many people are with you?", "a": "two peoples", "step": 1},
    {"q": "Would you like a table by the window?", "a": "yes please", "step": 1},
    {"q": "And for the main course?", "a": "I want a chicken", "step": 3},
]


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def payload(items):
    return json.dumps({"mistakes": items}, ensure_ascii=False)


print("1) промпт")
messages = review.build_messages(ROWS, "A2")
check("два сообщения (system + user)", len(messages) == 2, len(messages))
system = messages[0]["content"]
check("в правилах «не больше 3»", "At most 3 mistakes" in system, system[:80])
check("уровень подставлен", "level A2" in system, system[:80])
check("формат ответа описан",
      '"said"' in system and '"fix"' in system and '"why"' in system)
check("short answer не ошибка", "Not a mistake" in system)
user = messages[1]["content"]
check("вопрос официанта в промпте", "Waiter: How many people are with you?" in user)
check("ответы ученика в промпте", "Student: two peoples" in user)
check("нумерация по порядку", "2) Waiter:" in user and "3) Waiter:" in user, user)
check("пустой список ответов не ломает",
      "(no answers)" in review.build_messages([], "A2")[1]["content"])
check("мусор в ответах пропускается",
      review.build_messages([{"q": "x", "a": "  "}, "строка", None], "A2") ==
      review.build_messages([], "A2"))

print("2) разбор JSON")
raw = payload([{"said": "two peoples", "fix": "two people",
                "why": "people — уже «люди»."}])
data = review.parse(raw, ROWS)
check("обычный JSON разобран", data.get("ok") is True, data)
check("правка одна", len(data["mistakes"]) == 1, data.get("mistakes"))
check("поля на месте",
      data["mistakes"][0]["fix"] == "two people"
      and data["mistakes"][0]["why"].startswith("people"), data["mistakes"][0])
fenced = "```json\n" + raw + "\n```"
check("в ```-блоке тоже разбирается",
      review.parse(fenced, ROWS).get("ok") is True)
check("битый JSON — не показываем",
      review.parse("не json вовсе", ROWS).get("ok") is False)
check("пустой ответ — не показываем", review.parse("", ROWS).get("ok") is False)
check("нет модели — не показываем", review.parse(None, ROWS).get("ok") is False)
empty = review.parse('{"mistakes": []}', ROWS)
check("пустой список правок — это «ошибок нет»",
      empty.get("ok") is True and empty["mistakes"] == [], empty)

print("3) цитата сверяется кодом")
mixed = payload([
    {"said": "two peoples", "fix": "two people", "why": "без -s"},
    {"said": "I want chicken please", "fix": "I would like chicken",
     "why": "выдуманная фраза — ученик так не говорил"},
])
data = review.parse(mixed, ROWS)
check("придуманная цитата выброшена", len(data["mistakes"]) == 1, data.get("mistakes"))
check("настоящая осталась", data["mistakes"][0]["said"] == "two peoples")
check("регистр и знаки не мешают сверке",
      review.parse(payload([{"said": "Two Peoples.", "fix": "two people",
                             "why": "x"}]), ROWS).get("ok") is True)
check("совсем чужая фраза — разбор не показываем",
      review.parse(payload([{"said": "I like pizza", "fix": "I like a pizza",
                             "why": "x"}]), ROWS).get("ok") is False)
check("часть фразы ученика засчитывается",
      review.parse(payload([{"said": "a chicken", "fix": "the chicken",
                             "why": "x"}]), ROWS).get("ok") is True)

print("4) «как надо» = «что сказал» — не правка")
same = payload([{"said": "yes please", "fix": "Yes please", "why": "x"}])
check("регистр не считается правкой", review.parse(same, ROWS).get("ok") is False,
      review.parse(same, ROWS))

print("5) не больше трёх, без повторов")
many = payload([
    {"said": "two peoples", "fix": "two people", "why": "1"},
    {"said": "yes please", "fix": "yes, please.", "why": "2"},
    {"said": "a chicken", "fix": "chicken", "why": "3"},
    {"said": "two peoples", "fix": "two people", "why": "1"},
    {"said": "I want a chicken", "fix": "I would like chicken", "why": "4"},
])
data = review.parse(many, ROWS)
check("максимум 3 правки", len(data["mistakes"]) <= 3, len(data["mistakes"]))
check("правки не повторяются",
      len({m["said"] for m in data["mistakes"]}) == len(data["mistakes"]))
check("длина цитаты ограничена",
      all(len(m["said"]) <= review.MAX_SAID for m in data["mistakes"]))

print("6) текст для чата")
text = review.review_text(review.parse(raw, ROWS))
check("заголовок разбора", text.startswith("🔎 Разбор сцены"), text)
check("цитата в ёлочках", "«two peoples»" in text, text)
check("стрелка и правка", "→ two people" in text, text)
check("объяснение под правкой", "people — уже «люди»." in text, text)
check("без правок — по-русски",
      "ошибок в ответах не нашёл" in review.review_text({"mistakes": []}))
check("одна правка — «1 место»",
      "1 место" in review.review_text({"mistakes": [
          {"said": "a", "fix": "b", "why": "c"}]}))

print("7) запись в базу пробелов")
analysis = review.analysis_from(review.parse(raw, ROWS), "city/2.1")
check("формат для record_analysis", analysis.get("move_type") == "A"
      and analysis.get("move_status") == "P", analysis)
check("урок указан", analysis.get("lesson") == "city/2.1", analysis.get("lesson"))
check("ошибка размечена как грамматика",
      analysis["errors"][0]["type"] == "grammar", analysis["errors"])
check("правило не выдумываем (пусто → gaps.pick_rule)",
      analysis["errors"][0]["rule"] == "", analysis["errors"][0])
check("цитата и правка на месте",
      analysis["errors"][0]["wrong"] == "two peoples"
      and analysis["errors"][0]["correct"] == "two people", analysis["errors"][0])
check("без правок — move_status A",
      review.analysis_from({"mistakes": []}).get("move_status") == "A")
try:
    import gaps
    rule = gaps.pick_rule("two peoples", "two people", "")
    check("gaps.pick_rule не падает на такой паре", isinstance(rule, str), rule)
except Exception as exc:                          # noqa: BLE001
    check("gaps.pick_rule работает", False, exc)

print("8) окно: разбор в конце и в фоне")
src = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
check("метод запуска есть", "def _start_scene_review" in src)
check("фон-воркер есть", "def _scene_review_worker" in src)
check("показ разбора есть", "def _apply_scene_review" in src)
check("разбор идёт в отдельном потоке",
      "threading.Thread(target=self._scene_review_worker" in src)
check("вызов ровно в конце сцены",
      src.find("self._start_scene_review(session)") > src.find("def _scene_finish")
      and src.find("self._start_scene_review(session)") > 0)
check("пока разбор в пути, итог не показывают",
      "return                   # итог покажет _apply_scene_review" in src)
_reply_at = src.find("def _scene_reply")
_next_at = src.find("def _scene_credit")
check("модель по ходу сцены не зовётся",
      0 < _reply_at < _next_at
      and "llm.complete" not in src[_reply_at:_next_at], (_reply_at, _next_at))
check("ответы копятся в сессии", "session.scene_note(question, text)" in src)
check("ошибки сцены идут в базу", "profile_store.record_analysis(" in src
      and "review_mod.analysis_from(data, session.lesson_id)" in src)
check("флаг в config", getattr(config, "SCENE_REVIEW_ENABLED", None) is True,
      getattr(config, "SCENE_REVIEW_ENABLED", None))
check("флаг выключает разбор",
      'if not getattr(config, "SCENE_REVIEW_ENABLED", True):' in src)

print("9) сессия копит ответы правильно")
session = lesson.LessonSession("city/2.1", point_id="city/point_2",
                               lesson_type=lesson.SCENE, title="x")
import scenes                      # noqa: E402
session.start_scene("a2.restaurant", scenes.counts("a2.restaurant"))
check("сначала пусто", session.scene_said == [])
check("английский ответ записан",
      session.scene_note("How many people are with you?", "two people") is True)
check("пустой не записан", session.scene_note("Q", "   ") is False)
check("русский не записан", session.scene_note("Q", "двое") is False)
check("в записи есть вопрос и шаг",
      session.scene_said[0]["q"].startswith("How many")
      and session.scene_said[0]["step"] == 1, session.scene_said)
check("длинный ответ обрезан",
      session.scene_note("Q", "yes " * 200) is True
      and len(session.scene_said[-1]["a"]) <= 200)

print()
if FAILED:
    print("❌ ПРОВАЛОВ: %d" % len(FAILED))
    for name in FAILED:
        print("   •", name)
    sys.exit(1)
print("🎉 ВСЕ ПРОВЕРКИ РАЗБОРА СЦЕНЫ ПРОШЛИ")
