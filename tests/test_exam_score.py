# =========================================================
# TESTS/TEST_EXAM_SCORE.PY — балл экзамена (без окна и модели)
# =========================================================
#   python tests\test_exam_score.py
#
# ЗАЧЕМ. Экзамен = проверка блока: ровно 10 вопросов, за ответ 0/1/2,
# итог 0-20 -> /2 -> 0-10, проходной 6. Считаться всё должно КОДОМ,
# а не «на глаз», иначе «сдал/не сдал» зависит от настроения модели.
#
# Проверяем:
#   1) score_answer: пусто/по-русски = 0, короткий = 1, полный = 2,
#      2+ ошибки = 1, подсказка = 1;
#   2) ExamSession: 10 ответов, итог, граница проходного (11 -> 5.5,
#      12 -> 6.0), лишний ответ не принимается;
#   3) итог и снимок состояния: ключи, прерывание, лучший результат.
# Модель, микрофон и сеть не нужны.
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

import exam                                                      # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    # ---------- 1. Балл за один ответ ----------
    print("[1] score_answer: 0 / 1 / 2")
    check("пусто → 0", exam.score_answer("") == 0)
    check("пробелы → 0", exam.score_answer("   \n ") == 0)
    check("молчание (None) → 0", exam.score_answer(None) == 0)
    check("по-русски → 0", exam.score_answer("я думаю что это хорошо") == 0)
    check("кириллица вперемешку → 0",
          exam.score_answer("I think это good") == 0)
    check("только цифры → 0", exam.score_answer("123 456") == 0)

    check("3 слова → 1", exam.score_answer("I like it") == 1,
          exam.score_answer("I like it"))
    check("4 слова → 2", exam.score_answer("I like it very") == 2,
          exam.score_answer("I like it very"))
    check("знаки не мешают счёту слов",
          exam.score_answer("Yes, I like it!") == 2,
          exam.score_answer("Yes, I like it!"))

    check("1 ошибка → 2", exam.score_answer("I goes to school every day", 1) == 2)
    check("2 ошибки → 1", exam.score_answer("I goes to school every day", 2) == 1)
    check("5 ошибок → 1", exam.score_answer("I goes to school every day", 5) == 1)
    check("ошибки мусором не ломают счёт",
          exam.score_answer("I like it very", "много") == 2,
          exam.score_answer("I like it very", "много"))

    check("подсказка → 1", exam.score_answer("I like it very", 0, True) == 1)
    check("подсказка + короткий всё равно 1",
          exam.score_answer("I like", 0, True) == 1)

    # ---------- 2. Сессия: 10 вопросов и проходной ----------
    print("\n[2] ExamSession: 10 ответов и граница 6 из 10")
    s = exam.ExamSession("1.4")
    check("вопросов 10", s.questions == 10, s.questions)
    check("сдавать начали, ответов 0", s.answered == 0 and s.is_active)
    check("итог пока 0.0", s.score == 0.0, s.score)
    check("и не сдал", s.passed is False)

    for i in range(9):
        r = s.answer("I like it very much")
    check("после 9 ответов экзамен ещё идёт", s.is_active is True, s.state())
    check("последний ответ: индекс 9", r["index"] == 9, r)
    check("последний ответ: не финал", r["finished"] is False, r)

    r = s.answer("I like it very much")
    check("10-й ответ закрывает экзамен", r["finished"] is True, r)
    check("и экзамен больше не идёт", s.is_active is False)
    check("все ответы полные: 20 из 20", s.total == 20, s.total)
    check("итог 10.0", s.score == 10.0, s.score)
    check("сдал", s.passed is True)
    check("лишний 11-й ответ не принимается",
          s.answer("I like it very much")["accepted"] is False, s.state())
    check("и сумма не выросла", s.total == 20, s.total)

    # граница: 11 из 20 = 5.5 (не сдал) и 12 из 20 = 6.0 (сдал)
    low = exam.ExamSession("1.4")
    for pts in [2, 2, 2, 2, 2, 1, 0, 0, 0, 0]:          # 11 из 20
        low.answer("I like it very much" if pts == 2 else
                   ("I like it" if pts == 1 else ""))
    check("11 из 20 = 5.5", low.score == 5.5, low.score)
    check("5.5 — не сдал", low.passed is False, low.state())

    high = exam.ExamSession("1.4")
    for pts in [2, 2, 2, 2, 2, 2, 0, 0, 0, 0]:          # 12 из 20
        high.answer("I like it very much" if pts == 2 else "")
    check("12 из 20 = 6.0", high.score == 6.0, high.score)
    check("6.0 — сдал (порог ровно 6)", high.passed is True, high.state())

    # ---------- 3. Итог, снимок, прерывание, лучший ----------
    print("\n[3] Итог и снимок")
    res = high.result()
    for key in ("lesson_id", "questions", "answers", "total", "score",
                "passed", "mistakes", "hints", "finished"):
        check("итог содержит «%s»" % key, key in res, list(res))
    check("в итоге 10 оценок", len(res["answers"]) == 10, res["answers"])
    check("шесть полных ответов", res["correct_full"] == 6,
          res["correct_full"])
    check("порог в итоге 6", res["pass_score"] == 6, res["pass_score"])
    check("экзамен дочитан", res["finished"] is True, res["finished"])
    check("подсказок на экзамене 0", res["hints"] == 0, res["hints"])

    st = high.state()
    check("снимок: отвечено 10 из 10",
          st["answered"] == 10 and st["questions"] == 10, st)
    check("снимок: экзамен не идёт", st["active"] is False, st)

    stop = exam.ExamSession("1.5")
    stop.answer("I like it very much")
    stop.abort()
    check("прерванный не активен", stop.is_active is False, stop.state())
    check("прерванный не дочитан", stop.result()["finished"] is False)
    check("прерванный ответ не принимается",
          stop.answer("I like it very much")["accepted"] is False, stop.state())
    check("ответы прерванного сохранились", stop.answered == 1, stop.answered)

    check("ошибки копятся в итоге",
          exam.ExamSession("1.6").answer("I like it very", 2)["score"] == 1)

    check("лучший результат: 5.5 и 8.0 → 8.0",
          exam.best_of(5.5, 8.0) == 8.0, exam.best_of(5.5, 8.0))
    check("лучший: 9.0 и 6.0 → 9.0", exam.best_of(9.0, 6.0) == 9.0)
    check("лучший: пусто → 7.0", exam.best_of(None, 7.0) == 7.0)
    check("лучший: мусор не роняет", exam.best_of("?", 4.0) == 4.0,
          exam.best_of("?", 4.0))
    check("подпись итога «8.5 из 10»", exam.score_text(8.5) == "8.5 из 10",
          exam.score_text(8.5))
    check("подпись целого без .0", exam.score_text(8.0) == "8 из 10",
          exam.score_text(8.0))

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
