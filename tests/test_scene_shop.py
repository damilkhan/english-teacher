# -*- coding: utf-8 -*-
# =========================================================
# TEST_SCENE_SHOP.PY - вторая сцена «В магазине»: движок без правки кода
# =========================================================
# Проверяем ТОЛЬКО данные: сцена a2.shop, слоты магазина и то, что движок
# отвечает на живые реплики без единой правки scene_reactions.py.
# =========================================================
import io
import json
import os
import sys

sys.stdout.reconfigure(errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import lesson
import scenes
import scene_reactions as react

FAILED = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "FAIL") + " | " + name
          + ("" if ok else "  <<< " + str(detail)))
    if not ok:
        FAILED.append(name)


SHOP = "a2.shop"
LESSON = "city/3.1"

print("1) сцена в данных и на карте")
raw = json.load(open(os.path.join(ROOT, "data", "scenes_a2.json"),
                     encoding="utf-8"))
row = [s for s in raw["scenes"] if s.get("id") == SHOP]
check("сцена a2.shop есть", len(row) == 1, [s.get("id") for s in raw["scenes"]])
row = row[0] if row else {}
check("привязана к уроку city/3.1", row.get("lesson") == LESSON, row.get("lesson"))
check("точка city/point_3", row.get("point") == "city/point_3", row.get("point"))
check("название по-русски", row.get("title_ru") == "В магазине", row.get("title_ru"))
check("шагов ровно 6", len(row.get("steps") or []) == 6)
check("номеров шагов 1..6",
      [st.get("n") for st in row.get("steps") or []] == [1, 2, 3, 4, 5, 6])
qs = [q for st in row.get("steps") or [] for q in st.get("questions") or []]
check("вопросов ровно 15", len(qs) == 15, len(qs))
check("счёт по шагам [2,3,3,2,2,3]",
      scenes.counts(SHOP) == [2, 3, 3, 2, 2, 3], scenes.counts(SHOP))
check("сцена находится по уроку", scenes.for_lesson(LESSON) == SHOP,
      scenes.for_lesson(LESSON))
check("ресторан на месте", scenes.for_lesson("city/2.1") == "a2.restaurant")
check("у каждого вопроса есть подсказка",
      all(str(q.get("hint") or "").strip() for q in qs),
      [q.get("en") for q in qs if not q.get("hint")])
check("вопросы короткие (до 65 знаков)",
      all(len(q["en"]) <= 65 for q in qs),
      max(len(q["en"]) for q in qs))
check("вопросы по-английски (латиница + знаки)",
      all(all("a" <= ch.lower() <= "z" or ch in " ?!.,'-" for ch in q["en"])
          for q in qs))
check("каждый вопрос кончается знаком",
      all(q["en"].strip()[-1] in ".!?" for q in qs))
card = row.get("card") or {}
check("карточка роли есть (ru и en)", card.get("ru") and card.get("en"))
check("сказано, что продавец НЕ друг",
      "НЕ друг" in card.get("ru", "") and "NOT a friend" in card.get("en", ""))
check("у каждого вопроса известная метка slot",
      all(react.has_slot(q.get("slot") or "") for q in qs),
      [q.get("slot") for q in qs if not react.has_slot(q.get("slot") or "")])

print("2) слоты магазина: движок отвечает СВОИМИ словами")
SAMPLE = [
    ("Good morning! Can I help you?", "a jacket please",
     "Jacket? This way, please."),
    ("What are you looking for?", "jeans", "Jeans? Over here, please."),
    ("What size do you wear?", "medium", "Size medium. Here you are."),
    ("What colour would you like?", "black", "In black. Here you are."),
    ("We have this one in black. Do you like it?", "yes",
     "Great! Would you like to try it on?"),
    ("Would you like to try it on?", "yes",
     "The changing room is over there, on the right."),
    ("The changing room is over there. Is the size OK?", "yes",
     "Very good! Do you want to take it?"),
    ("Do you want a bigger size?", "yes",
     "Here is a bigger size. Try this one."),
    ("It costs forty dollars. Is that OK?", "how much is it?",
     "It costs forty dollars."),
    ("Do you want to take it?", "i'll take it",
     "Great! How would you like to pay?"),
    ("How would you like to pay?", "by card", "By card. Fine, thank you."),
    ("Can I have your card, please?", "here you are",
     "Thank you. Please enter your PIN."),
    ("Do you need a bag?", "no", "OK, no bag. Here is your receipt."),
    ("Would you like a receipt?", "yes", "Here you are. Thank you!"),
    ("Thank you for your visit. Have a nice day!", "thank you",
     "You're welcome. Have a nice day!"),
]
universal = set((react.library().get("universal") or {}).values())
for number, (question, said, want) in enumerate(SAMPLE, 1):
    item = scenes.question(SHOP, *[(st, i) for st in range(1, 7)
                                   for i in range(scenes.counts(SHOP)[st - 1])][number - 1])
    check("вопрос №%d совпал с данными" % number, item.get("en") == question,
          item.get("en"))
    slot = item.get("slot") or ""
    got = react.reply(slot, said)
    check("№%d %r -> %r" % (number, said, want), got == want, got)
    check("№%d ответ не общая заглушка" % number, got not in universal, got)

print("3) магазин: отказы и «не понял» не молчат")
check("«no, thanks» — отказ, а не благодарность",
      react.intent("shop_like", "no, thanks").kind == react.NO)
check("незнакомое слово — переспрос слота",
      react.reply("shop_size", "sorry, whatever") is None)
check("у слота свой переспрос",
      react.unknown("shop_size")
      == "Sorry, what size do you wear? Small, medium or large?",
      react.unknown("shop_size"))
check("«просто смотрю» — свой ответ слота",
      react.reply("shop_help", "i'm just looking")
      == "No problem. Take your time.")
check("карта: «вот, пожалуйста» — не переспрос",
      react.reply("shop_card", "here you are")
      == "Thank you. Please enter your PIN.")

print("4) сессия проходит вторую сцену целиком")
session = lesson.LessonSession(LESSON, lesson_type=lesson.SCENE)
check("сцена стартует", session.start_scene(SHOP, scenes.counts(SHOP)) is True)
for step in range(1, 7):
    for index in range(scenes.counts(SHOP)[step - 1]):
        session.scene_check(SAMPLE[sum(scenes.counts(SHOP)[:step - 1])
                                    + index][1])
        moved = session.scene_advance()
        if moved.get("step_done"):
            session.scene_credit()
check("сцена пройдена", session.finished is True, session.finished)
check("6 шагов засчитаны", session.tasks_done == 6, session.tasks_done)
check("без оговорок", session.tasks_marked == 0, session.tasks_marked)
check("ответов 15", session.scene_answers == 15, session.scene_answers)

print("5) движок не правили под магазин")
src = io.open(os.path.join(ROOT, "scene_reactions.py"), encoding="utf-8").read()
check("в движке нет названий магазина",
      "shop_" not in src and "jacket" not in src, "shop_/jacket в коде")
check("все слоты магазина — только в данных",
      all(react.has_slot(name) for name in
          ["shop_help", "shop_item", "shop_size", "shop_colour", "shop_like",
           "shop_try", "shop_fit", "shop_bigger", "shop_price", "shop_take",
           "shop_pay", "shop_card", "shop_bag", "shop_receipt", "shop_bye"]))

print()
if FAILED:
    print("ПРОВАЛОВ: %d" % len(FAILED))
    for name in FAILED:
        print("   •", name)
    sys.exit(1)
print("ВСЁ ПРОШЛО: магазин работает на том же движке")
