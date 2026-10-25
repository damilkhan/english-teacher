# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_REGREET.PY — не здороваться дважды (без экрана)
# =========================================================
#   python tests\test_lesson_regreet.py
#
# ЗАЧЕМ. Жалоба ученика 25.10.2026: он написал «hello», а преподаватель
# попросил его поздороваться ещё раз («can you try saying "Hi" back to me?»).
# Причина: первое задание урока 1.1 «Hello / Hi» и есть приветствие, а
# затравка просила лишь «ответь коротко и переходи к уроку».
#
# Теперь приветствие ученика считается СДЕЛАННЫМ: в затравке прямо запрещено
# просить поздороваться снова и повторять слово-приветствие.
#
# Проверяем:
#   1) без реплики ученика затравка прежняя БАЙТ-В-БАЙТ (ничего не сломано);
#   2) с репликой — есть запрет повторного приветствия и просьба ответить;
#   3) реплика ученика попадает в затравку, кавычки не ломают;
#   4) обрезка длинной реплики — 200 символов (как было);
#   5) затравка без кириллицы (модель не сбивается на русский).
# Модель, микрофон и Tk не нужны.
# =========================================================

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                                                    # noqa: E402
from controllers.chat_controller import ChatController             # noqa: E402

FAILED = []
OLD_OPENING = ("[START OF LESSON] Topic: Hello / Hi. Greet the student warmly "
               "in English and give the FIRST small task of this lesson "
               "(one thing at a time).")


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    real_rag = config.RAG_ENABLED
    config.RAG_ENABLED = False          # методические заметки тут не нужны
    try:
        ctrl = ChatController(llm=object(), dispatch=lambda fn: fn())
    finally:
        config.RAG_ENABLED = real_rag

    sent = []
    ctrl.send = lambda text: (sent.append(text), True)[1]
    lesson = {"title": "Hello / Hi", "type": "speaking", "topic": "Greetings"}

    # ---------- 1. прежнее поведение ----------
    print("[1] Без реплики ученика — затравка прежняя")
    ctrl.begin_lesson(lesson)
    check("строка байт-в-байт", sent[-1] == OLD_OPENING, sent[-1])
    check("запрета про приветствие нет (ученик ещё молчит)",
          "do NOT ask the student to greet" not in sent[-1], sent[-1])

    # ---------- 2. реплика ученика уже была ----------
    print("\n[2] Ученик сказал «hello» — просить снова нельзя")
    ctrl._opening = False
    ctrl.begin_lesson(lesson, student_text="hello")
    text = sent[-1]
    check("реплика ученика в затравке", '"hello"' in text, text)
    check("просьба ответить сохранена", "answer that briefly" in text, text)
    check("прямой запрет просить поздороваться снова",
          "do NOT ask the student to greet you again" in text, text)
    check("прямой запрет просить повторить слово-приветствие",
          "repeat a greeting word" in text, text)
    check("сказано, что приветствие уже сделано",
          "greeting is already" in text, text)
    check("затравка по-прежнему начинается со служебной метки",
          text.startswith("[START OF LESSON]"), text[:40])

    # ---------- 3. кавычки в реплике ----------
    print("\n[3] Кавычки в реплике")
    ctrl._opening = False
    ctrl.begin_lesson(lesson, student_text='He said "hi"')
    check("двойные кавычки стали одинарными",
          "He said 'hi'" in sent[-1] and '"hi"' not in sent[-1], sent[-1])

    # ---------- 4. длинная реплика ----------
    print("\n[4] Слишком длинная реплика")
    ctrl._opening = False
    ctrl.begin_lesson(lesson, student_text="x" * 400)
    check("обрезана до 200 символов", sent[-1].count("x") == 200,
          sent[-1].count("x"))

    # ---------- 5. язык затравки ----------
    print("\n[5] Язык затравки")
    ctrl._opening = False
    ctrl.begin_lesson(lesson, student_text="hello")
    check("в затравке нет кириллицы",
          re.search(r"[А-Яа-яЁё]", sent[-1]) is None,
          re.findall(r"[А-Яа-яЁё]+", sent[-1])[:5])

    # ---------- 6. пробельная реплика ----------
    print("\n[6] Пустая реплика = обычная затравка")
    ctrl._opening = False
    ctrl.begin_lesson(lesson, student_text="   ")
    check("пробелы не считаются приветствием", sent[-1] == OLD_OPENING, sent[-1])

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
