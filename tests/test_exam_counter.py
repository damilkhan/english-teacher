# =========================================================
# TESTS/TEST_EXAM_COUNTER.PY — «какой вопрос по счёту» в промпте экзамена
# =========================================================
#   python tests\test_exam_counter.py
#
# ЗАЧЕМ. Живой прогон экзамена (25.10.2026, logs/exam_live_run.txt) показал:
# правило «ровно 10 вопросов» модель НЕ СЧИТАЕТ — на 8-м ответе она сама
# объявила итог («We have covered a lot today…»), а после 9-го спросила снова.
# Лечим не словами, а числом: на каждый ход в промпт уходит
# «ученик ответил N из 10, спрашивай вопрос N+1».
#
# Проверяем:
#   1) без числа блок ПРЕЖНИЙ (старые проверки и smoke_test);
#   2) число подставляется верно: 0 → вопрос 1, 4 → вопрос 5;
#   3) когда все вопросы заданы — «ничего больше не спрашивай» и НЕТ «вопрос 11»;
#   4) мусор/отрицательное не ломают блок;
#   5) обычный (не экзаменационный) промпт счётчика не получает;
#   6) ChatController.set_exam_asked приводит значение к числу;
#   7) ui/app.py действительно обновляет счёт (иначе счётчик — мёртвый код).
# Модель, окно и сеть не нужны.
# =========================================================

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

import prompt_builder as pb                                     # noqa: E402
from controllers.chat_controller import ChatController           # noqa: E402

FAILED = []

PROFILE = {
    "mistakes": {"grammar": [], "vocabulary": []},
    "strengths": [],
    "topics_passed": [],
    "total_lessons": 0,
}


def check(name, ok, detail=""):
    print(("  OK  " if ok else "  ПРОВАЛ ") + name + ("" if ok else "  << " + str(detail)))
    if not ok:
        FAILED.append(name)


def read(*parts):
    with open(os.path.join(ROOT, *parts), "r", encoding="utf-8") as fh:
        return fh.read()


def main():
    plain = pb._exam_block(True, 10)

    print("[1] без числа блок прежний")
    check("нет счётчика", "PROGRESS:" not in plain and "Ask question" not in plain,
          plain[-120:])
    check("ровно 10 вопросов на месте", "Ask EXACTLY 10 questions" in plain)
    check("asked=None = без счётчика", pb._exam_block(True, 10, None) == plain)

    print("[2] число подставляется")
    first = pb._exam_block(True, 10, 0)
    check("0 ответов → спроси ВОПРОС 1",
          "answered 0 of 10 questions" in first
          and "Ask question 1 of 10 now" in first, first[-200:])
    fifth = pb._exam_block(True, 10, 4)
    check("4 ответа → спроси ВОПРОС 5",
          "answered 4 of 10 questions" in fifth
          and "Ask question 5 of 10 now" in fifth, fifth[-200:])
    check("запрет закрывать экзамен раньше 10-го",
          "do not end the exam before question 10" in fifth)
    check("просьба не подводить итог",
          "Do not" in fifth and "summarise" in fifth)
    check("счётчик стоит ПОСЛЕ правил экзамена",
          fifth.startswith(plain), fifth[:80])

    print("[3] вопросы кончились")
    last = pb._exam_block(True, 10, 10)
    check("10 ответов → экзамен закончен", "answered all 10 questions" in last)
    check("спрашивать больше НЕЛЬЗЯ", "ask NOTHING more" in last, last[-200:])
    check("вопроса 11 нет", "Ask question 11" not in last)
    check("и «Ask question» вообще нет", "Ask question" not in last)
    check("перебор (15) — тот же текст", pb._exam_block(True, 10, 15) == last)

    print("[4] мусор не ломает блок")
    check("строка-мусор → блок без счётчика",
          pb._exam_block(True, 10, "много") == plain)
    check("None → блок без счётчика", pb._exam_block(True, 10, None) == plain)
    check("отрицательное → как 0",
          "Ask question 1 of 10 now" in pb._exam_block(True, 10, -3))
    check("число вопросов другое (5): 2 → вопрос 3",
          "Ask question 3 of 5 now" in pb._exam_block(True, 5, 2))

    print("[5] обычный промпт счётчика не получает")
    free = pb.build_system_prompt("free", PROFILE, "en", exam=False, exam_asked=4)
    check("свободный чат без PROGRESS", "PROGRESS:" not in free)
    lesson = pb.build_system_prompt("lesson", PROFILE, "en", level="A2",
                                   lesson={"title": "Hello", "type": "speaking"},
                                   exam=False, exam_asked=4)
    check("урок без экзамена — без счётчика", "PROGRESS:" not in lesson)

    print("[6] счётчик доходит до промпта")
    exam_prompt = pb.build_system_prompt(
        "lesson", PROFILE, "en", level="A2",
        lesson={"title": "Hello", "type": "check"}, exam=True,
        exam_questions=10, exam_asked=3)
    check("в промпте «вопрос 4 из 10»", "Ask question 4 of 10 now" in exam_prompt)
    check("блок экзамена в КОНЦЕ", exam_prompt.endswith(pb._exam_block(True, 10, 3)),
          exam_prompt[-80:])

    print("[7] контроллер и приложение связаны")
    ctrl = ChatController(llm=None)
    check("по умолчанию счётчика нет", ctrl._exam_asked is None)
    ctrl.set_exam_asked(3)
    check("число принято", ctrl._exam_asked == 3, ctrl._exam_asked)
    ctrl.set_exam_asked("7")
    check("строка приводится к числу", ctrl._exam_asked == 7, ctrl._exam_asked)
    ctrl.set_exam_asked(-5)
    check("отрицательное → 0", ctrl._exam_asked == 0, ctrl._exam_asked)
    ctrl.set_exam_asked("мусор")
    check("мусор → счётчика нет", ctrl._exam_asked is None, ctrl._exam_asked)
    ctrl.set_exam_asked(2)
    ctrl.clear_history()
    check("новая история — счёт сброшен", ctrl._exam_asked is None)

    app_src = read("ui", "app.py")
    ctrl_src = read("controllers", "chat_controller.py")
    check("app обновляет счёт после реплики ученика",
          "_sync_exam_asked()" in app_src, "нет вызова")
    check("app сбрасывает счёт при закрытии занятия",
          "self.chat.set_exam_asked(None)" in app_src)
    check("контроллер передаёт счёт в промпт",
          "exam_asked=(self._exam_asked if exam_mode else None)" in ctrl_src)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
