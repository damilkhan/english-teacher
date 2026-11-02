# -*- coding: utf-8 -*-
# =========================================================
# TEST_SCENE_LIVE.PY - живые реплики ученика и повторы в диалоге
# =========================================================
# Две живые поломки 03.11.2026 (скриншоты ученика):
#   1) «i'm ready» на «Are you ready to order?» -> переспрос;
#   2) официант говорил одно и то же дважды: переспрос уже содержал вопрос,
#      а окно задавало его ещё раз.
# Здесь замок на оба: типичные ответы A2 по слотам ресторана понимаются,
# а реакция слота НЕ содержит текст следующего вопроса сцены.
# =========================================================
import os
import re
import sys

sys.stdout.reconfigure(errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scene_reactions as R
import scenes

FAILED = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "FAIL") + " | " + name
          + ("" if ok else "  <<< " + str(detail)))
    if not ok:
        FAILED.append(name)


# Типичные ответы ученика A2 по слотам ресторана (живая речь, не чипы).
LIVE = {
    "people": ["two", "just me", "two people", "me and my wife", "a table for two"],
    "table": ["yes please", "no thanks", "by the window", "sure"],
    "drink": ["two beers", "i'd like a coffee", "just water", "a coke please",
              "nothing thanks", "orange juice"],
    "menu": ["i'm ready", "yes please", "give me a few minutes", "we are ready",
             "no, we are ready"],
    "ready": ["yes", "i'm ready", "yes we are", "one more minute",
              "can i have the menu again"],
    "starter": ["soup please", "i'll have a salad", "nothing thanks",
                "onion rings", "what do you recommend"],
    "main": ["steak please", "i'd like fish", "chicken for me", "a burger", "pasta"],
    "side": ["salad please", "soup", "both please", "no thanks"],
    "thanks": ["thank you", "thanks", "you are welcome"],
    "food_ok": ["yes it's delicious", "everything is fine", "the food is cold",
                "no, it's too salty"],
    "bread": ["yes please", "no thanks", "no more bread"],
    "dessert": ["yes please", "no thanks", "i'd like ice cream"],
    "anything": ["no that's all", "the bill please", "yes, some water"],
    "payment": ["by card", "cash", "card please", "i'll pay in cash"],
    "goodbye": ["goodbye", "thank you", "have a nice evening", "bye"],
}


def test_live_answers():
    total, bad = 0, []
    for slot, rows in LIVE.items():
        for text in rows:
            total += 1
            if R.reply(slot, text) is None:
                bad.append((slot, text, R.intent(slot, text).kind))
    check("живых реплик проверено: %d" % total, total >= 60, total)
    check("всё понято (не понято: %d)" % len(bad), not bad, bad)


def _questions(scene_id):
    data = scenes.scene(scene_id)
    out = []
    for step in data.get("steps") or []:
        for q in step.get("questions") or []:
            out.append(q)
    return out


def test_no_double_question():
    """Реакция слота не должна повторять текст СЛЕДУЮЩЕГО вопроса."""
    bad = []
    for scene_id in scenes.scene_ids():
        rows = _questions(scene_id)
        for i, q in enumerate(rows[:-1]):
            slot = str(q.get("slot") or "")
            nxt = str((rows[i + 1] or {}).get("en") or "").strip().lower()
            if not slot or not nxt:
                continue
            conf = R._conf(slot)
            for key in ("yes", "no", "echo", "echo_one", "thanks", "fallback"):
                val = conf.get(key)
                if not val or isinstance(val, dict):
                    continue
                if nxt in str(val).strip().lower():
                    bad.append((scene_id, slot, key, str(val)))
    check("реакции не повторяют следующий вопрос (повторов: %d)" % len(bad),
          not bad, bad)


def _norm(text):
    words = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).split()
    return " ".join(words)


def test_no_repeated_sentence():
    """Реакция не повторяет фразу текущего или следующего вопроса.

    Живой скриншот 03.11.2026: «Here is your table. Can I get you something
    to drink?» шло сразу после реакции «This way, please. Here is your table.»
    - ученик видел одно и то же дважды. Fallback не проверяем: он и есть
    переспрос, где вопрос повторяется нарочно.
    """
    bad = []
    for scene_id in scenes.scene_ids():
        rows = _questions(scene_id)
        for i, q in enumerate(rows):
            slot = str(q.get("slot") or "")
            if not slot:
                continue
            nxt = _norm(rows[i + 1].get("en")) if i + 1 < len(rows) else ""
            if not nxt:
                continue          # последний вопрос — реакции прощаться можно
            conf = R._conf(slot)
            for key in ("yes", "no", "echo", "echo_one", "thanks"):
                val = conf.get(key)
                if not val or isinstance(val, dict):
                    continue
                for sent in re.split(r"[.!?;]", str(val)):
                    words = _norm(sent)
                    if len(words.split()) < 3:
                        continue
                    if words in nxt or nxt in words:
                        bad.append((scene_id, slot, key, sent.strip()))
    check("реакции не повторяют фразы вопросов (повторов: %d)" % len(bad),
          not bad, bad)


def test_unknown_has_question():
    """Переспрос содержит вопрос сам — окно его больше НЕ повторяет."""
    src = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
    body = src[src.find("def _scene_reply"):src.find("def _replay_after")]
    check("переспрос идёт без повторного вопроса, «повторите» — с ним",
          'self._scene_say(session, line, ask=(again != "unknown"))' in body)
    check("у _scene_say есть параметр ask",
          "def _scene_say(self, session, line, finish=False, ask=True)"
          in src)
    check("без ask вопрос не задаётся", "elif ask:" in src)
    line = R.unknown("bread")
    check("переспрос слота без fallback содержит вопрос",
          "?" in line and "bread" in line.lower(), line)


def test_live_flow():
    """Сцена из скриншота: «i'm ready» на «Are you ready to order?»."""
    line = R.reply("ready", "i'm ready")
    check("«i'm ready» понято на слоте ready", bool(line), line)
    check("реакция не спрашивает «What would you like to start with?»",
          "start with" not in str(line).lower(), line)
    line2 = R.reply("menu", "i'm ready")
    check("на слоте menu «i'm ready» — короткая реакция", bool(line2), line2)


def main():
    print("1) живые ответы ученика")
    test_live_answers()
    print("2) одно и то же не спрашиваем дважды")
    test_no_double_question()
    print("3) реакции не повторяют вопросы")
    test_no_repeated_sentence()
    print("4) переспрос содержит вопрос")
    test_unknown_has_question()
    print("5) реплика со скриншота")
    test_live_flow()
    print("")
    if FAILED:
        print("ПРОВАЛОВ: %d" % len(FAILED))
        for name in FAILED:
            print("   •", name)
        return 1
    print("ВСЁ ПРОШЛО: сцена понимает живую речь и не повторяется")
    return 0


if __name__ == "__main__":
    sys.exit(main())
