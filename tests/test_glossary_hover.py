# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GLOSSARY_HOVER.PY — подсказка по наведению (окно)
# =========================================================
#   python tests\test_glossary_hover.py
#
# ЗАЧЕМ. Решения ученика (25.10.2026):
#   * подсказка-перевод появляется ТОЛЬКО при наведении курсора;
#   * только в репликах Вербота (свои он говорил сам — их не переводим);
#   * разбор реплики моделью идёт В ПАУЗЕ, а не во время ответа/озвучки.
#
# Проверяем:
#   1) контроллер ждёт паузу: пока занято — модель не зовётся;
#   2) очередь не больше N: новая реплика вытесняет старую;
#   3) в облачке преподавателя наведение показывает перевод (окно есть);
#   4) в облачке ученика подсказки нет вообще;
#   5) уход курсора и прокрутка окно закрывают;
#   6) lookup не зовёт модель (счётчик запросов не растёт).
# =========================================================

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

import tkinter as tk                                            # noqa: E402
import customtkinter as ctk                                     # noqa: E402

import glossary                                                 # noqa: E402
import theme                                                    # noqa: E402
from controllers.glossary_controller import GlossaryController   # noqa: E402
from ui.widgets.chat_view import ChatView                        # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeGloss:
    """Словарь-пустышка: считает разборы, ничего не переводит."""

    def __init__(self, known=False):
        self.calls = []
        self._known = known

    def known(self, text):
        return self._known

    def prime(self, text, timeout=120):
        self.calls.append(text)
        return True, 1


class SimpleEvent:
    def __init__(self, x=0, y=0, x_root=0, y_root=0, widget=None):
        self.x, self.y = x, y
        self.x_root, self.y_root = x_root, y_root
        self.widget = widget


# ---------------------------------------------------------
print("[1] Контроллер: разбор только в паузе")
gloss1 = FakeGloss()
state = {"idle": False}
ctl = GlossaryController(gloss1, is_idle=lambda: state["idle"], poll=0.01)
ctl.request("Look forward to seeing you there")
time.sleep(0.25)
check("пока занято — модель не зовётся", gloss1.calls == [], gloss1.calls)
state["idle"] = True
for _ in range(60):
    if gloss1.calls:
        break
    time.sleep(0.02)
check("в паузе — разбор пошёл", gloss1.calls == ["Look forward to seeing you there"],
      gloss1.calls)
check("счётчик done", ctl.done == 1, ctl.done)
ctl.stop()

gloss_known = FakeGloss(known=True)
ctl2 = GlossaryController(gloss_known, is_idle=lambda: True, poll=0.01)
check("уже известная реплика не ставится в очередь",
      ctl2.request("Same words again") is False)
check("пустая реплика не ставится в очередь", ctl2.request("   ") is False)
ctl2.stop()

# ---------------------------------------------------------
print("\n[2] Очередь вытесняет старое (не копим работу)")
gloss3 = FakeGloss()
ctl3 = GlossaryController(gloss3, is_idle=lambda: False, max_pending=2, poll=0.01)
for text in ("first reply", "second reply", "third reply"):
    ctl3.request(text)
check("вытеснение посчитано", ctl3.skipped == 1, ctl3.skipped)
check("в очереди осталось 2", ctl3._queue.qsize() == 2, ctl3._queue.qsize())
ctl3.stop()

# ---------------------------------------------------------
print("\n[3] Окно: подсказка в облачке преподавателя")
root = ctk.CTk()
root.geometry("760x520+40+40")
root.withdraw()                     # окно не мешает, виджеты всё равно считаются
palette = theme.DARK

dict_gloss = glossary.Glossary(llm=None, path=os.path.join(ROOT, "logs", "_hover_tmp.json"))
dict_gloss.add(glossary.parse_items(
    '{"items":[{"en":"Look forward to","ru":"с нетерпением ждать","phrase":true},'
    '{"en":"there","ru":"там","phrase":false}]}'))
before = dict_gloss.stats["requests"]

chat = ChatView(root, palette,
                on_hover_word=lambda text, pos: dict_gloss.lookup(text, pos))
chat.pack(fill="both", expand=True)
root.update()

mark = chat.add_message("Jane", "Look forward to seeing you there!")
root.update()
msg = chat._messages[mark]
body = msg.body

box = body.bbox("1.2")
check("текст реплики на месте", box is not None, box)
event = SimpleEvent(x=box[0] + 3, y=box[1] + box[3] // 2,
                    x_root=100, y_root=100, widget=body)
chat._gloss_motion(body, event)
root.update()
check("окно-подсказка появилось", chat._gloss_tip is not None, chat._gloss_tip)

texts = []
tip = chat._gloss_tip
if tip is not None:
    for child in tip.winfo_children():
        for label in child.winfo_children():
            try:
                texts.append(label.cget("text"))
            except Exception:
                pass
check("в подсказке перевод фразы", "с нетерпением ждать" in texts, texts)
check("для фразы показан и английский", "Look forward to" in texts, texts)

chat._gloss_hide()
root.update()
check("уход курсора закрывает окно", chat._gloss_tip is None)

# ---------------------------------------------------------
print("\n[4] В облачке ученика подсказок нет")
chat.add_message("Вы", "Look forward to seeing you there!")
root.update()
user_msg = chat._messages["msg_2"]
check("это реплика ученика", user_msg.is_user is True)
check("окно не появилось", chat._gloss_tip is None)

teacher_bound = bool(chat._messages[mark].body.bind("<Motion>"))
user_bound = bool(user_msg.body.bind("<Motion>"))
check("у реплики Вербота наведение привязано", teacher_bound is True, teacher_bound)
check("у реплики ученика наведение НЕ привязано", user_bound is False, user_bound)
check("окно так и не появилось", chat._gloss_tip is None)

# ---------------------------------------------------------
print("\n[5] Прокрутка закрывает подсказку")
chat._gloss_show({"en": "there", "ru": "там", "phrase": False, "start": 0, "end": 5},
                 100, 100)
root.update()
check("окно открыто перед прокруткой", chat._gloss_tip is not None)
chat._on_wheel(None)
check("прокрутка окно закрыла", chat._gloss_tip is None)

# ---------------------------------------------------------
print("\n[6] Наведение не зовёт модель")
check("запросов к модели не прибавилось",
      dict_gloss.stats["requests"] == before, dict_gloss.stats)

chat.destroy()
root.destroy()
try:
    os.remove(os.path.join(ROOT, "logs", "_hover_tmp.json"))
except OSError:
    pass

# ---------------------------------------------------------
print("\n" + ("ИТОГ: провалов %d" % len(FAILED) if FAILED
              else "ИТОГ: все проверки пройдены"))
if FAILED:
    print("  " + ", ".join(FAILED))
sys.exit(1 if FAILED else 0)
