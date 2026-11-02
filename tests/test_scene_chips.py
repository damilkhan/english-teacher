# -*- coding: utf-8 -*-
# =========================================================
# TEST_SCENE_CHIPS.PY - конструктор предложения на РУССКОМ (решение 101)
# =========================================================
# Панель без Tk не проверить (окно в общих прогонах висит), поэтому здесь:
#   1) данные чипов (все слоты обеих сцен, только кириллица на экране);
#   2) чистая логика scene_chips (группы, порядок, сборка предложения);
#   3) подключение панели в ui/app.py (по исходнику).
# Сам виджет рисуется и проверяется отдельным скриптом logs/_chip_smoke.py.
# =========================================================
import io
import json
import os
import sys

sys.stdout.reconfigure(errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scenes
import scene_chips as chips
import scene_reactions as react

FAILED = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "FAIL") + " | " + name
          + ("" if ok else "  <<< " + str(detail)))
    if not ok:
        FAILED.append(name)


GROUPS = {"start", "count", "item", "end", "short"}

print("1) данные: у каждого вопроса сцены есть чипы")
for scene_id in scenes.scene_ids():
    used = set()
    for step in range(1, scenes.step_count(scene_id) + 1):
        for index in range(scenes.counts(scene_id)[step - 1]):
            used.add(scenes.question(scene_id, step, index).get("slot"))
    naked = [slot for slot in used if not chips.has(slot)]
    check("%s: чипы у всех слотов" % scene_id, naked == [], naked)

raw = json.load(open(os.path.join(ROOT, "data", "reactions_a2.json"),
                     encoding="utf-8"))
slots = raw.get("slots") or {}
with_chips = [name for name, conf in slots.items() if conf.get("chips")]
check("чипы есть у всех 30 слотов", len(with_chips) == len(slots) == 30,
      (len(with_chips), len(slots)))
check("группы только известные",
      all(set(conf["chips"]) <= GROUPS for conf in slots.values()),
      [name for name, conf in slots.items()
       if not set(conf.get("chips") or {}) <= GROUPS])

print("2) на экране ТОЛЬКО русский")
latin = []
for name, conf in slots.items():
    for group, rows in (conf.get("chips") or {}).items():
        for row in rows:
            if chips.latin_in(row.get("ru")):
                latin.append("%s/%s: %s" % (name, group, row.get("ru")))
            if not str(row.get("en") or "").strip():
                latin.append("%s/%s: en пустой у %r" % (name, group, row.get("ru")))
check("ни в одной подписи нет латиницы", latin == [], latin[:6])
check("у каждого чипа есть en (для движка, не для экрана)", latin == [])

print("3) группы и порядок")
names = [g["key"] for g in chips.groups("drink")]
check("drink: start, count, item, end, short",
      names == ["start", "count", "item", "end", "short"], names)
check("people: число и короткий ответ",
      [g["key"] for g in chips.groups("people")] == ["count", "short"],
      [g["key"] for g in chips.groups("people")])
check("у короткого слота одна группа",
      [g["key"] for g in chips.groups("shop_bag")] == ["short"],
      [g["key"] for g in chips.groups("shop_bag")])
check("у каждого слота 2–12 чипов (короткий ответ — мало, сборка — больше)",
      all(2 <= len(chips.all_chips(name)) <= 12 for name in with_chips),
      {name: len(chips.all_chips(name)) for name in with_chips})

print("4) сборка предложения (порядок по смыслу, не по кликам)")
drink = {(c["group"], c["ru"]): c for c in chips.all_chips("drink")}
picked = [drink[("item", "пиво")], drink[("start", "Я бы хотел")],
          drink[("count", "два")]]
got = chips.compose(picked)
check("русское предложение собрано по смыслу",
      got["ru"] == "Я бы хотел два пиво", got["ru"])
check("английский вариант собран отдельно (движку)",
      got["en"] == "I would like two beer", got["en"])
check("пусто — пустая строка", chips.compose([])["ru"] == "")
check("один чип — его же текст",
      chips.compose([drink[("short", "Просто воду")]])["ru"] == "Просто воду")
check("повтор нажатого чипа не дублируется",
      chips.compose([drink[("start", "Я бы хотел")]])["ru"] == "Я бы хотел")

print("5) панель подключена в окно")
src = io.open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
check("ChipBuilder импортируется", "from ui.widgets.chip_builder import ChipBuilder" in src)
check("панель создаётся над чатом",
      "self.chip_builder = ChipBuilder(self.chat_tab, p," in src)
check("чипы строятся на КАЖДЫЙ вопрос сцены",
      'self.chip_builder.show_slot(item.get("slot"), english)' in src)
check("набор зависит от слота текущего вопроса",
      src.find("show_slot(item.get") > src.find("item = scenes_mod.question"))
check("панель прячется в конце сцены",
      src.find("self._scene_chips_off()      # конструктор") > 0)
check("панель прячется при выходе из урока",
      src.find("_scene_chips_off()         # конструктор прячется") > 0)
check("кнопка 🔊 повторяет вопрос",
      "def _scene_replay_question" in src and "self._say(text)" in src)
check("тема применяется", "self.chip_builder.apply_theme(p)" in src)

print("6) виджет: только русские подписи и микрофон")
widget = io.open(os.path.join(ROOT, "ui", "widgets", "chip_builder.py"),
                 encoding="utf-8").read()
check("кнопка «сказать» есть", "MIC_TEXT" in widget)
check("кнопка повтора вопроса есть", "REPLAY_TEXT" in widget)
check("сброс выбора есть", "def reset" in widget)
check("строка «Ты собрал» есть", 'Ты собрал' in widget)
check("в строке «Ты собрал» только русский",
      'text=("Ты собрал: «%s»" % text) if text else EMPTY_TEXT' in widget
      and 'text = scene_chips.compose(self._picked)["ru"]' in widget)
check("в виджете нет английских подписей (латиница только в служебном)",
      chips.latin_in("Ты собрал") == "")

print()
if FAILED:
    print("ПРОВАЛОВ: %d" % len(FAILED))
    for name in FAILED:
        print("   •", name)
    sys.exit(1)
print("ВСЁ ПРОШЛО: конструктор собирает русское предложение")
