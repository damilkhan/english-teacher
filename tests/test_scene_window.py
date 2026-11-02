# -*- coding: utf-8 -*-
# =========================================================
# TEST_SCENE_WINDOW.PY - реакции в окне: сцена ОТВЕЧАЕТ, а не читает скрипт
# =========================================================
# Проверяем поведение _scene_reply БЕЗ Tk: методы окна берём у класса
# EnglishTeacherApp, а «окно» подменяем маленькой заглушкой (как FakeApp в
# test_lesson_drill). Ни модели, ни сервера, ни звука.
# =========================================================
import io
import os
import sys

sys.stdout.reconfigure(errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import lesson
import scenes
import scene_reactions as react
from ui.app import EnglishTeacherApp

FAILED = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "FAIL") + " | " + name
          + ("" if ok else "  <<< " + str(detail)))
    if not ok:
        FAILED.append(name)


class FakeLesson:
    def __init__(self, session):
        self.s = session

    def current(self):
        return self.s


class Fake:
    """Заглушка окна: пишет, что было сказано, и в каком порядке."""

    def __init__(self, session):
        self.lesson = FakeLesson(session)
        self.teacher_name = "Verbot"
        self.lines = []      # реплики учителя в чате
        self.spoken = []     # всё, что озвучено
        self.asks = []       # заданные вопросы
        self.events = []     # ("speak", текст) / ("finish", "")
        self.finished = False

    def add_message(self, sender, text, **kw):
        self.lines.append(text)

    def _say(self, text, on_done=None, **kw):
        self.spoken.append(text)
        self.events.append(("speak", text))
        if on_done:
            on_done()        # звук «доиграл» сразу

    def _dispatch(self, fn):
        fn()

    def _scene_ask(self, session):
        item = scenes.question(session.scene_id, session.scene_step,
                               session.scene_q) or {}
        question = item.get("en", "")
        self.asks.append(question)
        self.spoken.append(question)
        return True

    def _scene_credit(self, session):
        return session.scene_credit()

    def _scene_finish(self, session):
        self.finished = True
        self.events.append(("finish", ""))

    def _register_lesson_reply(self, text):
        return None

    _scene_say = EnglishTeacherApp._scene_say
    _scene_reply = EnglishTeacherApp._scene_reply


def new_session():
    s = lesson.LessonSession("city/2.1", lesson_type=lesson.SCENE)
    s.start_scene("a2.restaurant", scenes.counts("a2.restaurant"))
    return s


print("1) вопросы отдают метку slot")
src_scenes = io.open(os.path.join(ROOT, "scenes.py"), encoding="utf-8").read()
check('scenes.question отдаёт "slot"',
      '"slot": str(item.get("slot") or "").strip()' in src_scenes)
all_q = [scenes.question("a2.restaurant", st, i)
         for st in range(1, 7)
         for i in range(scenes.counts("a2.restaurant")[st - 1])]
check("у всех 15 вопросов есть метка",
      all(q.get("slot") for q in all_q),
      [q.get("en") for q in all_q if not q.get("slot")])
check("метки — известные слоты движка",
      all(react.has_slot(q["slot"]) for q in all_q),
      [q["slot"] for q in all_q if not react.has_slot(q["slot"])])

print("2) предмет + число: реакция, и ТОЛЬКО ПОТОМ следующий вопрос")
s = new_session()
s.scene_step, s.scene_q = 1, 2          # «Can I get you something to drink?»
f = Fake(s)
f._scene_reply("i would like two beers")
check("реакция озвучена первой, вопрос — вторым",
      f.spoken[:2] == ["Two beers, coming up.",
                       "Here is the menu. Would you like a few minutes to look at it?"],
      f.spoken[:3])
check("реакция попала в чат", f.lines[:1] == ["Two beers, coming up."], f.lines[:2])
check("шаг идёт дальше", (s.scene_step, s.scene_q) == (2, 0),
      (s.scene_step, s.scene_q))

print("3) незнакомое слово: переспрос, шаг НЕ идёт")
s = new_session()
s.scene_step, s.scene_q = 1, 2
f = Fake(s)
f._scene_reply("sorry, latte")
check("переспрос словами слота",
      f.lines[:1] == ["Sorry, what would you like to drink?"], f.lines[:2])
check("тот же вопрос задан снова",
      f.asks == ["Here is your table. Can I get you something to drink?"], f.asks)
check("шаг не сдвинулся", (s.scene_step, s.scene_q) == (1, 2),
      (s.scene_step, s.scene_q))
f._scene_reply("sorry, latte")
check("второй раз не поняли — «OK.»", "OK." in f.lines, f.lines[-3:])
check("после второго раза шаг идёт", (s.scene_step, s.scene_q) == (2, 0),
      (s.scene_step, s.scene_q))

print("4) «повторите»: вопрос ещё раз, без реакции")
s = new_session()
s.scene_step, s.scene_q = 1, 2
f = Fake(s)
f._scene_reply("sorry, could you repeat that?")
check("лишней реплики нет", f.lines == [], f.lines)
check("вопрос задан снова", f.asks == ["Here is your table. "
                                       "Can I get you something to drink?"],
      f.asks)
check("шаг не сдвинулся", (s.scene_step, s.scene_q) == (1, 2),
      (s.scene_step, s.scene_q))

print("5) «да» на напиток — это ответ, а не молчание")
s = new_session()
s.scene_step, s.scene_q = 1, 2
f = Fake(s)
f._scene_reply("yes please")
check("движок ответил по слоту",
      f.lines[:1] == ["What would you like? We have beer, wine, "
                      "juice and coffee."], f.lines[:2])
check("шаг идёт дальше", (s.scene_step, s.scene_q) == (2, 0),
      (s.scene_step, s.scene_q))

print("6) вся сцена: 15 реакций, итог ПОСЛЕ последней реакции")
answers = {"people": "two", "table": "yes", "drink": "beer", "menu": "yes",
           "ready": "yes", "starter": "soup", "main": "steak", "side": "salad",
           "thanks": "thank you", "food_ok": "yes", "bread": "no",
           "dessert": "yes", "anything": "no", "payment": "card",
           "goodbye": "thank you"}
s = new_session()
f = Fake(s)
for step in range(1, 7):
    for index in range(scenes.counts("a2.restaurant")[step - 1]):
        f._scene_reply(answers[scenes.question("a2.restaurant", step,
                                               index)["slot"]])
reactions = [text for kind, text in f.events if kind == "speak"][:15]
check("первая реакция — про двоих",
      reactions[0] == "Two people? Right this way, please.", reactions[0])
check("реакция на пиво", reactions[2] == "One beer, coming up.", reactions[2])
check("последняя реакция — прощание",
      reactions[-1] == "Thank you. Have a nice evening!", reactions[-1])
check("итог идёт ПОСЛЕ последней реакции",
      f.events[-1][0] == "finish", f.events[-3:])
check("итог показан один раз",
      [kind for kind, _ in f.events].count("finish") == 1)
check("сцена пройдена: 6 шагов",
      s.finished is True and s.tasks_done == 6, (s.finished, s.tasks_done))

print("7) окно: движок подключён в _scene_reply")
src = io.open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
check("движок импортируется в окне", "import scene_reactions as react_mod" in src)
check("намерение берётся по метке вопроса",
      "sense = react_mod.intent(slot, text)" in src)
check("реакцию отдаёт движок",
      "reaction = react_mod.reply_to(slot, sense) or" in src)
check("реакция → следующий вопрос (один вход)",
      "self._scene_say(session, reaction, finish=done)" in src)
check("озвучка ждёт конца реакции",
      "_say(line, on_done=_after)" in src and "_next()" in src)
check("модель в сцене не зовётся",
      "_send_to_teacher" not in src[src.find("def _scene_reply"):
                                    src.find("def _scene_say")])

print()
if FAILED:
    print("ПРОВАЛОВ: %d" % len(FAILED))
    for name in FAILED:
        print("   •", name)
    sys.exit(1)
print("ВСЁ ПРОШЛО: реакции в окне работают")
