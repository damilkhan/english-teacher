# =========================================================
# TESTS/TEST_EXAM_SOFT_SCORE.PY — сбой разбора не даёт 2 балла
# =========================================================
#   python tests\test_exam_soft_score.py
#
# ЗАЧЕМ. В `_exam_score_answer` (ui/app.py) ошибки брались так:
#   errors = 0; if result and result.get("ok"): errors = len(errors)
# То есть при СБОЕ разбора Аналитика получалось «0 ошибок» → ответ 4+ слов
# получал 2 балла. Ошибка модели не редкая (1 реплика из 5 в замере §20),
# значит сбой разбора превращался в ПОДАРОК на экзамене. Решение ученика
# 25.10.2026: неизвестно — значит не больше 1 балла, и в итоге честно
# написано, сколько ответов осталось без разбора.
#
# Проверяем:
#   1) score_answer: errors=None → 1, errors=0 → 2 (старое поведение цело);
#   2) ExamSession: ответ без разбора = 1 балл, счётчик unverified растёт,
#      mistakes НЕ меняется (ошибок мы не знаем);
#   3) в итоге есть "unverified";
#   4) ui/app.py действительно передаёт None при сбое разбора;
#   5) итог в чате честно пишет про неразобранные ответы (и молчит, если их нет).
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

import exam                                                     # noqa: E402

FAILED = []
LONG = "I like it very much and I go there every day"


def check(name, ok, detail=""):
    print(("  OK  " if ok else "  ПРОВАЛ ") + name + ("" if ok else "  << " + str(detail)))
    if not ok:
        FAILED.append(name)


def read(*parts):
    with open(os.path.join(ROOT, *parts), "r", encoding="utf-8") as fh:
        return fh.read()


def main():
    print("[1] score_answer: неизвестные ошибки")
    check("errors=None → 1 балл", exam.score_answer(LONG, errors=None) == 1,
          exam.score_answer(LONG, errors=None))
    check("errors=0 → 2 балла (как было)",
          exam.score_answer(LONG, errors=0) == exam.MAX_PER_ANSWER)
    check("errors=1 → 2 балла (как было)",
          exam.score_answer(LONG, errors=1) == exam.MAX_PER_ANSWER)
    check("errors=2 → 1 балл (как было)", exam.score_answer(LONG, errors=2) == 1)
    check("errors=None, короткий ответ → 1",
          exam.score_answer("I like it", errors=None) == 1)
    check("errors=None, по-русски → 0",
          exam.score_answer("Мне очень нравится тут", errors=None) == 0)
    check("errors=None не ломает пустой ответ",
          exam.score_answer("", errors=None) == 0)

    print("[2] ExamSession: ответ без разбора")
    sess = exam.ExamSession("city/1.4")
    step = sess.answer(LONG, errors=None)
    check("балл за ответ = 1", step["score"] == 1, step)
    check("счётчик unverified = 1", sess.unverified == 1, sess.unverified)
    check("mistakes не выдумываем", sess.mistakes == 0, sess.mistakes)
    sess.answer(LONG, errors=1)
    check("нормальный разбор идёт как раньше (2 балла)", sess.scores[-1] == 2)
    check("unverified не растёт", sess.unverified == 1, sess.unverified)
    check("mistakes учёл 1 ошибку", sess.mistakes == 1, sess.mistakes)

    print("[3] итог знает про неразобранные ответы")
    res = sess.result()
    check("в итоге есть unverified", res.get("unverified") == 1, res.get("unverified"))
    check("балл считается по этим же ответам", res["total"] == 3, res["total"])

    print("[4] приложение передаёт None при сбое разбора")
    app_src = read("ui", "app.py")
    check("в _exam_score_answer ошибки начинаются с None",
          "errors = None" in app_src, "не найдено")
    check("и заполняются только при удачном разборе",
          'if result and result.get("ok"):' in app_src)
    check("нет старого «errors = 0» в этой функции",
          "        text = pending.pop(0)\r\n        errors = 0" not in app_src)

    print("[5] итог в чате честный")
    from ui.app import EnglishTeacherApp
    text = EnglishTeacherApp.exam_summary_text(
        {"score": 7.0, "answers": [1, 2, 1, 2, 2, 1, 2, 2, 1, 1], "passed": True,
         "correct_full": 5, "questions": 10, "mistakes": 3, "unverified": 2})
    check("строка про неразобранные есть", "Не разобрано ответов: 2" in text, text)
    check("и предупреждение про балл", "не выше 1 балла" in text, text)
    clean = EnglishTeacherApp.exam_summary_text(
        {"score": 8.0, "answers": [2] * 10, "passed": True,
         "correct_full": 10, "questions": 10, "mistakes": 0, "unverified": 0})
    check("если сбоев нет — строки нет", "Не разобрано" not in clean, clean)
    check("и остальное на месте", "ЭКЗАМЕН" in clean and "Сдал" in clean, clean)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
