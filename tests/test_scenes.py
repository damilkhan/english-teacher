# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_SCENES.PY — сцена-пилот «ресторан» (шаг 3, 02.11.2026)
# =========================================================
#   python tests\test_scenes.py
#
# Что проверяем:
#   1) данные: 6 шагов, 15 готовых вопросов, подсказки, карточка роли;
#   2) чтение библиотеки: counts / question / for_lesson / total_questions;
#   3) сессия: сцена = 6 заданий, фаза «scene», подпись «Шаг 1/6»;
#   4) разбор ответа: ok (английский), retry (русский/пусто), skip, off_topic;
#   5) шаг засчитывается на ПОСЛЕДНЕМ вопросе шага, после 15 ответов — конец;
#   6) окно: методы сцены есть, ответ перехватывается ДО модели, фото нет;
#   7) флаг config.LESSON_SCENE выключает сцену (урок обычный).
# Модель и окно Tk не нужны.
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
import scenes                     # noqa: E402

FAILED = []

SCENE_ID = "a2.restaurant"
LESSON_ID = "city/2.1"
ANSWERS = ["two", "yes please", "water please", "yes", "yes please",
           "soup", "chicken", "salad", "thank you", "yes it is good",
           "no thanks", "no thanks", "the bill please", "card", "goodbye"]


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def new_scene_session():
    session = lesson.LessonSession(LESSON_ID, point_id="city/point_2",
                                   lesson_type=lesson.SCENE,
                                   title="Can I have the menu?")
    started = session.start_scene(SCENE_ID, scenes.counts(SCENE_ID))
    return session, started


def answer(session, text):
    """Один ход, как в окне: на «retry» вопрос повторяют, позиция не движется."""
    res = session.scene_check(text)
    if res.get("result") == "retry":
        return res, {"step_done": False, "retry": True}
    moved = session.scene_advance()
    if moved.get("step_done"):
        session.scene_credit()      # оговорку решает сама сессия
    return res, moved


print("1) данные сцены")
raw = json.load(open(scenes.path("A2"), encoding="utf-8"))
row = raw["scenes"][0]
check("сцена одна и id a2.restaurant", row.get("id") == SCENE_ID, row.get("id"))
check("привязана к уроку city/2.1", row.get("lesson") == LESSON_ID, row.get("lesson"))
check("шагов ровно 6", len(row["steps"]) == 6, len(row["steps"]))
questions = [q for step in row["steps"] for q in step["questions"]]
check("вопросов ровно 15", len(questions) == 15, len(questions))
check("у каждого вопроса есть подсказка по-русски",
      all(str(q.get("hint") or "").strip() for q in questions))
check("вопросы короткие (до 65 знаков)",
      all(len(q["en"]) <= 65 for q in questions),   # 61 — вопрос про меню (§57)
      max(len(q["en"]) for q in questions))
check("вопросы по-английски (латиница + знаки)",
      all(all("a" <= ch.lower() <= "z" or ch in " ?!.,'-" for ch in q["en"])
          for q in questions))
check("каждый вопрос кончается знаком",
      all(q["en"].strip()[-1] in ".!?" for q in questions),
      [q["en"] for q in questions if q["en"].strip()[-1] not in ".!?"])
card = row.get("card") or {}
check("карточка роли есть (ru и en)",
      card.get("ru") and card.get("en"), list(card))
check("в карточке сказано, что он НЕ друг",
      "НЕ друг" in card.get("ru", "") and "NOT a friend" in card.get("en", ""))

print("2) чтение библиотеки")
check("counts = [3,2,3,3,1,3]", scenes.counts(SCENE_ID) == [3, 2, 3, 3, 1, 3],
      scenes.counts(SCENE_ID))
check("всего вопросов 15", scenes.total_questions(SCENE_ID) == 15)
check("for_lesson находит сцену", scenes.for_lesson(LESSON_ID) == SCENE_ID)
check("обычный урок сцены не получает", scenes.for_lesson("city/1.1") == "")
check("чужой урок/пусто — пусто", scenes.for_lesson("") == "")
first = scenes.question(SCENE_ID, 1, 0)
check("первый вопрос — №1", first.get("number") == 1, first)
check("номер последнего вопроса — 15",
      scenes.question(SCENE_ID, 6, 2).get("number") == 15,
      scenes.question(SCENE_ID, 6, 2))
check("вопрос №11 — третий в шаге 4",
      scenes.question(SCENE_ID, 4, 2).get("number") == 11,
      scenes.question(SCENE_ID, 4, 2))
check("чего нет — пусто",
      scenes.question(SCENE_ID, 7, 0) == {}
      and scenes.question(SCENE_ID, 1, 5) == {}
      and scenes.question("a2.nope", 1, 0) == {})
check("describe собирается", "шагов 6" in scenes.describe(SCENE_ID))

print("3) сессия: сцена = задания урока")
session, started = new_scene_session()
check("сцена стартовала", started is True)
check("is_scene", session.is_scene is True)
check("заданий 6 (по шагам)", session.tasks_total == 6, session.tasks_total)
check("фаза scene", session.task_phase == lesson.TASK_SCENE, session.task_phase)
check("подпись «Шаг 1/6»", session.progress_text() == "Шаг 1/6",
      session.progress_text())
check("ввод: голос и текст", sorted(session.allowed_inputs()) == ["text", "voice"],
      sorted(session.allowed_inputs()))
check("тип подписан как «сцена»",
      lesson.type_label(lesson.SCENE) == "сцена", lesson.type_label(lesson.SCENE))
other = lesson.LessonSession("city/1.1", lesson_type="speaking")
check("обычный урок сценой не стал", other.is_scene is False)
check("чужая сцена не стартует",
      other.start_scene("", [3]) is False and other.start_scene(SCENE_ID, []) is False)

print("4) разбор ответа")
probe, _ = new_scene_session()
check("английский ответ принят", probe.scene_check("two").get("result") == "ok")
probe, _ = new_scene_session()
check("русский ответ — повтор",
      probe.scene_check("привет, двое").get("result") == "retry")
check("вторая осечка — пропуск вопроса",
      probe.scene_check("двое").get("result") == "skip")
probe, _ = new_scene_session()
check("молчание — повтор", probe.scene_check("").get("result") == "retry")
probe, _ = new_scene_session()
check("«yes» — это ответ", probe.scene_check("yes").get("result") == "ok")
probe, _ = new_scene_session()
check("вопрос в ответе — ОБЫЧНЫЙ ответ, не «ушли в сторону»",
      probe.scene_check("can I have some water?").get("result") == "ok")
probe, _ = new_scene_session()
check("«are we two persons?» — ответ (ошибку ловит разбор в конце)",
      probe.scene_check("are we two persons?").get("result") == "ok")
probe, _ = new_scene_session()
check("ответ из русских букв и цифр — не зачёт",
      probe.scene_check("2 человека").get("result") == "retry")

print("5) шаги засчитываются на последнем вопросе")
session, _ = new_scene_session()
steps_done = []
for number, text in enumerate(ANSWERS, 1):
    _, moved = answer(session, text)
    if moved.get("step_done"):
        steps_done.append(number)
check("шаги закрылись на 3, 5, 8, 11, 12, 15",
      steps_done == [3, 5, 8, 11, 12, 15], steps_done)
check("после 15 ответов сцена пройдена", session.finished is True)
check("все 6 шагов засчитаны", session.tasks_done == 6, session.tasks_done)
check("без оговорок", session.tasks_marked == 0, session.tasks_marked)
check("ответов насчитано 15", session.scene_answers == 15, session.scene_answers)
check("фаза done", session.task_phase == lesson.TASK_DONE, session.task_phase)
probe, _ = new_scene_session()
for text in ["yes"] * 2:
    answer(probe, text)          # 1-й шаг: 3 вопроса, закроется на третьем
answer(probe, "yes")
check("шаг закрыт без оговорки", probe.tasks_marked == 0, probe.tasks_marked)
probe, _ = new_scene_session()
for text in ["", "", "yes", "yes"]:
    answer(probe, text)          # 1-й вопрос: молчание дважды → пропуск
check("брошенный вопрос — шаг с оговоркой",
      probe.tasks_marked == 1, probe.tasks_marked)
check("счётчик брошенных", probe.scene_skipped == 1, probe.scene_skipped)
check("шаг всё равно засчитан", probe.tasks_done == 1, probe.tasks_done)

print("6) окно: сцену ведёт приложение")
src = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
check("метод _scene_ask есть", "def _scene_ask" in src)
check("метод _scene_reply есть", "def _scene_reply" in src)
check("метод _scene_credit есть", "def _scene_credit" in src)
check("метод _scene_finish есть", "def _scene_finish" in src)
check("урок становится сценой", "lesson_mod.SCENE if scene_id" in src)
check("сцена стартует на карте", "session.start_scene(scene_id, scene_counts)" in src)
check("ответ перехватывается ДО дрилла",
      src.find("if self._scene_reply(text):") < src.find("if self._drill_reply(text):")
      and src.find("if self._scene_reply(text):") > 0)
_pos = src.find("if self._scene_reply(text):")
_after = src.find("if self.server_ready:", _pos) if _pos > 0 else -1
check("перехват стоит ДО требования сервера",
      0 < _pos and 0 < _after and (_after - _pos) < 2000,
      (_pos, _after))
check("лог шага и номера вопроса",
      "🎬 Сцена: шаг %d/%d, вопрос №%d" in src)
check("жёлтой подсказки в чате НЕТ (убрана 03.11.2026)",
      '"«" + hint' not in src and "hint + \"»\"" not in src)
check("вопрос сцены показывается только по-английски",
      'add_message(self.teacher_name, english)' in src)
check("формулировки подсказок в библиотеке ОСТАЛИСЬ (решение 84)",
      '"hint"' in open(os.path.join(ROOT, "data", "scenes_a2.json"),
                       encoding="utf-8").read())
check("фото после сцены не дают",
      'if getattr(session, "is_scene", False):' in src)
check("дрилл на сцене не запускается",
      "if scene_id and session.start_scene(scene_id, scene_counts):" in src)

print("7) флаг выключает сцену")
check("флаг есть в config", getattr(config, "LESSON_SCENE", None) is True,
      getattr(config, "LESSON_SCENE", None))
check("окно проверяет флаг перед сценой",
      'if not getattr(config, "LESSON_SCENE", True):' in src)
saved = getattr(config, "LESSON_SCENE", True)
try:
    config.LESSON_SCENE = False
    # тот же выбор, что делает окно: флаг выключен → урок обычный
    chosen = (scenes.for_lesson(LESSON_ID)
              if getattr(config, "LESSON_SCENE", True) else "")
    check("выключено — сцены нет", chosen == "", chosen)
    config.LESSON_SCENE = True
    check("включено — сцена есть", scenes.for_lesson(LESSON_ID) == SCENE_ID)
finally:
    config.LESSON_SCENE = saved

print()
if FAILED:
    print("❌ ПРОВАЛОВ: %d" % len(FAILED))
    for name in FAILED:
        print("   •", name)
    sys.exit(1)
print("🎉 ВСЕ ПРОВЕРКИ СЦЕНЫ ПРОШЛИ")
