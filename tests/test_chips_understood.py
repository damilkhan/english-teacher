# -*- coding: utf-8 -*-
# =========================================================
# TEST_CHIPS_UNDERSTOOD.PY - панель не предлагает фраз, которых нет в движке
# =========================================================
# Живой баг 03.11.2026: чип «Дайте пару минут» -> «A few minutes, please»,
# ученик сказал её дословно, а движок ответил переспросом. Проверка-замок:
# КАЖДЫЙ готовый ответ из панели (и КАЖДАЯ собранная из чипов фраза) должен
# пониматься движком реакций. Плюс проверка черновика: распознанное в сцене
# идёт В ПОЛЕ на проверку, а не в чат само.
# =========================================================
import io
import itertools
import os
import sys

sys.stdout.reconfigure(errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scene_chips as chips_mod
import scene_reactions as react
from ui.app import EnglishTeacherApp

FAILED = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "FAIL") + " | " + name
          + ("" if ok else "  <<< " + str(detail)))
    if not ok:
        FAILED.append(name)


# ---------------------------------------------------------
# 1. Готовые короткие ответы панели понимаются движком
# ---------------------------------------------------------
def test_short_chips():
    total, bad = 0, []
    for slot in react.slot_names():
        for row in chips_mod.chips(slot).get("short") or []:
            en = row.get("en") or ""
            if not en:
                check("short-чип слота %s без en: %r" % (slot, row.get("ru")), False)
                continue
            total += 1
            if react.reply(slot, en) is None:
                bad.append((slot, row["ru"], en))
    check("готовых ответов в панели: %d (не меньше 60)" % total, total >= 60, total)
    check("все готовые ответы панели понимаются (не понято: %d)" % len(bad),
          not bad, bad)


# ---------------------------------------------------------
# 2. Собранное из чипов предложение тоже понимается
# ---------------------------------------------------------
def _combo(tab, groups):
    picked = []
    for group in groups:
        rows = tab.get(group) or []
        for row in rows:
            picked.append({"group": group, "ru": row["ru"], "en": row["en"]})
    return picked


def test_composed():
    total, bad = 0, []
    for slot in react.slot_names():
        tab = {k: v for k, v in chips_mod.chips(slot).items() if v}
        plans = []
        if "start" in tab and "item" in tab:
            plans.append(["start", "item"])
        if "start" in tab and "count" in tab and "item" in tab:
            plans.append(["start", "count", "item"])
        if "item" in tab and "end" in tab:
            plans.append(["item", "end"])
        seen = set()
        for plan in plans:
            groups = [tab[g] for g in plan]
            names = list(plan)
            for combo in itertools.product(*groups):
                picked = [{"group": names[i], "ru": row["ru"],
                           "en": row["en"]} for i, row in enumerate(combo)]
                en = chips_mod.compose(picked)["en"]
                if not en or en in seen:
                    continue
                seen.add(en)
                total += 1
                if react.reply(slot, en) is None:
                    bad.append((slot, en))
    check("собранных фраз проверено: %d (не меньше 60)" % total, total >= 60, total)
    check("собранные фразы понимаются (не понято: %d)" % len(bad), not bad, bad)


# ---------------------------------------------------------
# 3. Живые фразы ученика (реальные из лога)
# ---------------------------------------------------------
def test_live_phrases():
    cases = [
        ("menu", "give me two minutes, please"),
        ("menu", "a few minutes, please"),
        ("menu", "we are ready"),
        ("ready", "one more minute"),
        ("side", "both, please"),
        ("food_ok", "it's delicious"),
        ("shop_item", "i'm just looking"),
        ("shop_colour", "any colour"),
        ("shop_like", "do you have another colour?"),
        ("shop_price", "it's too expensive"),
        ("shop_take", "i'll think about it"),
        ("shop_bye", "have a nice day"),
        ("goodbye", "have a nice evening"),
    ]
    for slot, text in cases:
        line = react.reply(slot, text)
        check("движок понимает %r (%s)" % (text, slot), bool(line),
              react.intent(slot, text))


# ---------------------------------------------------------
# 4. Черновик распознанного: в поле, а не в чат
# ---------------------------------------------------------
class FakeInput:
    def __init__(self):
        self.text = ""
        self.focused = False

    def set_text(self, text):
        self.text = str(text)

    def focus_input(self):
        self.focused = True


class FakeCtrl:
    def __init__(self, session):
        self.s = session

    def current(self):
        return self.s


class FakeSession:
    def __init__(self, active=True, scene=True):
        self.is_active = active
        self.is_scene = scene


class FakeWin:
    def __init__(self, session):
        self.lesson = FakeCtrl(session)
        self.input_bar = FakeInput()


def test_draft():
    method = getattr(EnglishTeacherApp, "_scene_draft", None)
    check("в окне есть _scene_draft", callable(method))
    if not callable(method):
        return

    win = FakeWin(FakeSession())
    got = method(win, "give me two minutes, please")
    check("в сцене распознанное уходит в поле", got is True, got)
    check("текст в поле совпадает",
          win.input_bar.text == "give me two minutes, please", win.input_bar.text)
    check("поле получило фокус (можно править)", win.input_bar.focused)

    win2 = FakeWin(FakeSession(active=False))
    check("вне занятия в поле НЕ кладём", method(win2, "hello") is False)

    win3 = FakeWin(FakeSession(scene=False))
    check("в обычном уроке НЕ кладём (там как было)", method(win3, "hello") is False)

    win4 = FakeWin(FakeSession())
    check("пустое распознавание игнорируем", method(win4, "   ") is False)
    check("поле осталось пустым", win4.input_bar.text == "")


def test_source_order():
    src = io.open(os.path.join(ROOT, "ui", "app.py"),
                  encoding="utf-8").read()
    body = src[src.find("def _on_recognized"):]
    body = body[:body.find("def _on_server_state")]
    pos_draft = body.find("self._scene_draft(text)")
    pos_msg = body.find('self.add_message("Вы (голос)", text)')
    check("_on_recognized зовёт _scene_draft", pos_draft >= 0)
    check("черновик раньше отправки в чат", 0 <= pos_draft < pos_msg,
          (pos_draft, pos_msg))


def main():
    test_short_chips()
    test_composed()
    test_live_phrases()
    test_draft()
    test_source_order()
    print("")
    if FAILED:
        print("ПРОВАЛОВ: %d" % len(FAILED))
        for name in FAILED:
            print("  - " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
