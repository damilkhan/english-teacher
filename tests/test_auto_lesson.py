# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_AUTO_LESSON.PY — Джейн сама начинает урок (этап B+)
# =========================================================
#   python tests\test_auto_lesson.py   (без окна, без модели, без сети)
#
# Проверяем две вещи:
#   1) progress_map.next_lesson() — какой урок следующий по плану
#      (первый непройденный, порядок линейный, по полю number);
#   2) chat_controller.begin_lesson(student_text=…) — реплика ученика
#      попадает в затравку урока, а без неё текст остаётся прежним.
# =========================================================

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                                                    # noqa: E402
from controllers.chat_controller import ChatController           # noqa: E402
from progress_map import ProgressMap                             # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def write_curriculum(folder, data):
    path = os.path.join(folder, "curriculum.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    return ProgressMap(base_path=folder)


def real_cases():
    """Настоящий учебный план: 468 уроков, строгий линейный порядок."""
    print("\n[1] next_lesson на реальном curriculum.json")
    pm = ProgressMap()
    # 13 локаций × 9 блоков × 4 урока (три урока + проверка)
    check("уроков в плане — 468", len(pm._lesson_order) == 468, len(pm._lesson_order))
    check("первый урок — 1.1", pm.next_lesson({}) == "1.1", pm.next_lesson({}))
    check("1.1 пройден → 1.2",
          pm.next_lesson({"completed_lessons": ["1.1"]}) == "1.2")
    check("1.1+1.2 → 1.3",
          pm.next_lesson({"completed_lessons": ["1.1", "1.2"]}) == "1.3")
    check("перескок вперёд не считается: 1.2 пройден → 1.1",
          pm.next_lesson({"completed_lessons": ["1.2"]}) == "1.1",
          pm.next_lesson({"completed_lessons": ["1.2"]}))
    check("после трёх уроков блока — его ПРОВЕРКА (1.3 → 1.4)",
          pm.next_lesson({"completed_lessons": ["1.1", "1.2", "1.3"]}) == "1.4",
          pm.next_lesson({"completed_lessons": ["1.1", "1.2", "1.3"]}))
    check("после проверки — первый урок следующего блока (1.4 → 2.1)",
          pm.next_lesson({"completed_lessons": ["1.1", "1.2", "1.3", "1.4"]}) == "2.1",
          pm.next_lesson({"completed_lessons": ["1.1", "1.2", "1.3", "1.4"]}))
    check("вся карта пройдена → None",
          pm.next_lesson({"completed_lessons": list(pm._lesson_order)}) is None)
    check("пустой профиль (None) → 1.1", pm.next_lesson(None) == "1.1")
    check("битые данные профиля не ломают выбор",
          pm.next_lesson({"completed_lessons": "1.1"}) == "1.1")
    check("неизвестные id в профиле игнорируются",
          pm.next_lesson({"completed_lessons": ["9.9", "нет такого"]}) == "1.1")


def order_cases():
    """Порядок берётся по полю number, а не по порядку строк в файле."""
    print("\n[2] порядок уроков: по number, с вложенными sublessons")
    plan = {
        "locations": [{
            "id": "test",
            "points": [
                {"id": "p2", "number": 2, "lessons": [{"id": "2.1"}]},
                {"id": "p1", "number": 1, "lessons": [
                    {"id": "1.1", "sublessons": [{"id": "1.1a"}, {"id": "1.1b"}]},
                    {"id": "1.2"},
                ]},
            ],
        }],
    }
    folder = tempfile.mkdtemp(prefix="lesson_auto_")
    try:
        pm = write_curriculum(folder, plan)
        check("порядок: 1.1 → 1.1a", pm.next_lesson({}) == "1.1", pm._lesson_order)
        check("порядок: 1.1a → 1.1b",
              pm.next_lesson({"completed_lessons": ["1.1"]}) == "1.1a",
              pm._lesson_order)
        check("порядок: 1.1b → 1.2",
              pm.next_lesson({"completed_lessons": ["1.1", "1.1a"]}) == "1.1b")
        check("блок 1 кончился → блок 2",
              pm.next_lesson({"completed_lessons": ["1.1", "1.1a", "1.1b", "1.2"]}) == "2.1")
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def broken_cases():
    """Сломанная карта: урок не выбирается, но и исключений нет."""
    print("\n[3] сломанная карта работает без исключений")
    folder = tempfile.mkdtemp(prefix="lesson_auto_")
    try:
        pm = ProgressMap(base_path=folder)                 # файла нет
        check("нет файла → None", pm.next_lesson({}) is None)
        with open(os.path.join(folder, "curriculum.json"), "w", encoding="utf-8") as fh:
            fh.write("{ битый json")
        pm = ProgressMap(base_path=folder)
        check("битый JSON → None", pm.next_lesson({}) is None)
        pm = write_curriculum(folder, {"locations": []})
        check("пустой план → None", pm.next_lesson({}) is None)
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def begin_lesson_cases():
    """Затравка урока: с репликой ученика и без неё."""
    print("\n[4] begin_lesson: реплика ученика в затравке урока")
    check("в config есть выключатель LESSON_AUTO_START",
          hasattr(config, "LESSON_AUTO_START"), "нет LESSON_AUTO_START")

    real_rag = config.RAG_ENABLED
    config.RAG_ENABLED = False          # тесту не нужны методические заметки
    try:
        ctrl = ChatController(llm=object(), dispatch=lambda fn: fn())
    finally:
        config.RAG_ENABLED = real_rag

    sent = []
    ctrl.send = lambda text: (sent.append(text), True)[1]

    lesson = {"title": "Hello / Hi", "type": "speaking", "topic": "Greetings"}
    check("без реплики ученика затравка прежняя",
          ctrl.begin_lesson(lesson) and sent[-1] ==
          "[START OF LESSON] Topic: Hello / Hi. Greet the student warmly in English "
          "and give the FIRST small task of this lesson (one thing at a time).",
          sent[-1])

    ctrl._opening = False
    check("с репликой ученика затравка её содержит",
          ctrl.begin_lesson(lesson, student_text="Hello, Jane!") and
          "Hello, Jane!" in sent[-1] and sent[-1].startswith("[START OF LESSON]"),
          sent[-1])
    check("затравка просит ответить и перейти к уроку",
          "answer that briefly" in sent[-1], sent[-1])

    ctrl._opening = False
    ctrl.begin_lesson(lesson, student_text='He said "hi"')
    check("кавычки в реплике не ломают затравку",
          'He said \'hi\'' in sent[-1], sent[-1])

    ctrl._opening = False
    ctrl.begin_lesson(lesson, student_text="x" * 400)
    check("слишком длинная реплика обрезается до 200 символов",
          sent[-1].count("x") == 200, sent[-1].count("x"))

    ctrl._opening = False
    check("пробельная реплика = обычная затравка",
          ctrl.begin_lesson(lesson, student_text="   ") and
          sent[-1] == ("[START OF LESSON] Topic: Hello / Hi. Greet the student "
                       "warmly in English and give the FIRST small task of this "
                       "lesson (one thing at a time)."),
          sent[-1])


def main():
    print("=" * 60)
    print("ТЕСТ: автозапуск урока (Джейн начинает сама)")
    print("=" * 60)
    real_cases()
    order_cases()
    broken_cases()
    begin_lesson_cases()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
