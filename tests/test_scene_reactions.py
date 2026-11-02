# -*- coding: utf-8 -*-
"""СЦЕНА: движок реакций (scene_reactions.py) - тесты без Tk и без сервера."""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import scene_reactions as R                                # noqa: E402

ok_n = 0
fail = []


def ok(name, cond):
    global ok_n
    if cond:
        ok_n += 1
    else:
        fail.append(name)


def eq(name, got, want):
    ok("%s: получено %r, ждали %r" % (name, got, want), got == want)


# ---------------------------------------------------------------
print("[1] данные читаются, метки слотов сцены известны движку")
lib = R.library()
ok("library вернул словарь", isinstance(lib, dict) and lib)
ok("есть universal", bool(lib.get("universal")))
ok("есть words", bool(lib.get("words")))
ok("есть numbers", bool(lib.get("numbers")))
ok("слотов >= 15", len(R.slot_names()) >= 15)

import json                                              # noqa: E402
scenes = json.load(open(os.path.join(ROOT, "data", "scenes_a2.json"), encoding="utf-8"))
missing = []
for sc in scenes["scenes"]:
    for st in sc["steps"]:
        for q in st["questions"]:
            slot = q.get("slot") or ""
            if not slot or not R.has_slot(slot):
                missing.append("%s -> %r" % (q["en"], slot))
eq("у всех вопросов сцены известная метка slot", missing, [])

# ---------------------------------------------------------------
print("[2] намерения: предмет, число, да/нет, благодарность")
eq("beer -> item", R.intent("drink", "a beer please").kind, R.ITEM)
eq("пиво названо по-разному", R.intent("drink", "i would like some beer").item, "beer")
eq("два пива = число 2", R.intent("drink", "two beers").count, 2)
eq("стейк -> item", R.intent("main", "i think i will take the steak").item, "steak")
eq("карта -> item", R.intent("payment", "i will pay by card").item, "by card")
eq("наличные -> item", R.intent("payment", "cash").item, "in cash")
eq("just me -> один человек", R.intent("people", "just me").count, 1)
eq("i am alone -> один", R.intent("people", "i am alone").count, 1)
eq("three of us -> три", R.intent("people", "three of us").count, 3)
eq("цифра 4 -> четыре", R.intent("people", "4").count, 4)
eq("me and my wife -> два", R.intent("people", "me and my wife").count, 2)
eq("пустая реплика -> empty", R.intent("drink", "   ").kind, R.EMPTY)
eq("yes", R.intent("menu", "yes please").kind, R.YES)
eq("no", R.intent("menu", "no").kind, R.NO)
eq("no thanks - это ОТКАЗ", R.intent("bread", "no, thank you").kind, R.NO)
eq("thanks", R.intent("thanks", "thank you very much").kind, R.THANKS)

# ---------------------------------------------------------------
print("[3] порядок правил (то, что прототип путал)")
# «just water thanks» = вода, а не благодарность
eq("just water thanks -> item", R.intent("drink", "just water thanks").kind, R.ITEM)
# жалоба раньше переспроса: «sorry, the food is cold»
eq("жалоба", R.intent("food_ok", "sorry, the food is cold").kind, R.COMPLAINT)
# «i will pay by card» = карта, а не счёт
eq("оплата картой", R.intent("payment", "i will pay by card").kind, R.ITEM)
# «no thanks, just the bill» = счёт
eq("bill раньше отказа", R.intent("dessert", "no thanks, just the bill").kind, R.BILL)
# «how much is coffee?» = цена, а не предмет
eq("вопрос о цене", R.intent("drink", "how much is coffee?").kind, R.PRICE)
# «i would like some beer. what do you have?» = пиво (жалоба ученика 03.11.2026)
it = R.intent("drink", "i would like some beer. what do you have?")
eq("пиво раньше «что у вас есть»", (it.kind, it.item), (R.ITEM, "beer"))
# «please» НЕ считается согласием
eq("please - не да", R.intent("drink", "latte please").kind, R.OTHER)

# ---------------------------------------------------------------
print("[4] переспрос и незнакомое слово")
eq("sorry? -> repeat", R.intent("drink", "sorry?").kind, R.REPEAT)
eq("could you say that again -> repeat", R.intent("drink", "sorry, could you say that again?").kind, R.REPEAT)
eq("на repeat ответ None (окно повторит)", R.reply("drink", "sorry?"), None)
eq("лапте не знаем -> other", R.intent("drink", "latte").kind, R.OTHER)
eq("«sorry, latte» - не переспрос", R.intent("drink", "sorry, latte").kind, R.OTHER)
ok("unknown даёт свой переспрос слота",
   R.unknown("drink").startswith("Sorry, what would you like to drink?"))
ok("unknown для слота без fallback содержит вопрос",
   R.unknown("bread") != "")

# ---------------------------------------------------------------
print("[5] ответы: шаблоны и заглавная буква")
eq("один предмет", R.reply("drink", "a beer please"), "One beer, coming up.")
eq("два предмета", R.reply("drink", "two beers"), "Two beers, coming up.")
eq("число людей", R.reply("people", "three of us"), "Three people? Right this way, please.")
eq("один человек", R.reply("people", "i am alone"), "Just one? Right this way, please.")
eq("предмет с заглавной", R.reply("starter", "soup please"), "Soup to start. Very good.")
eq("главное блюдо", R.reply("main", "for me chicken please"),
   "Chicken for the main course. Good choice.")
eq("оплата", R.reply("payment", "cash"), "In cash. Fine, thank you.")
eq("счёт", R.reply("dessert", "no thanks, just the bill"), "Here is your bill.")
eq("жалоба", R.reply("food_ok", "the food is cold"),
   "I'm sorry about that. I'll take it back to the kitchen.")
eq("рекомендация для напитков", R.reply("drink", "what can you recommend?"),
   "I recommend our lemonade. It's very good.")
eq("туалет", R.reply("main", "where is the toilet?"), "It's over there, on the right.")
eq("не знаю -> take your time", R.reply("menu", "i don't know"),
   "No problem. Take your time.")
eq("bye в goodbye", R.reply("goodbye", "bye"), "Have a nice evening!")
eq("пустой ответ -> None", R.reply("drink", ""), None)
ok("все ответы ресторана непустые и с заглавной",
   all((not t) or t[0].isupper() for t in [R.reply("drink", "beer"),
                                           R.reply("table", "by the window"),
                                           R.reply("dessert", "cake")]))

# ---------------------------------------------------------------
print("[6] метки слотов можно ставить в новой сцене без правки кода")
eq("незнакомый слот не падает (своих слов нет -> other)",
   R.intent("no_such_slot", "beer").kind, R.OTHER)
eq("незнакомый слот: ответ из общих слов", R.reply("no_such_slot", "no"), "No problem.")
ok("у незнакомого слота есть переспрос", bool(R.unknown("no_such_slot")))

# ---------------------------------------------------------------
print("")
print("=" * 60)
print("ИТОГ test_scene_reactions: зелёных %d, провалов %d" % (ok_n, len(fail)))
for line in fail:
    print("  ❌", line)
print("=" * 60)
sys.exit(1 if fail else 0)
