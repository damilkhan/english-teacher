# =========================================================
# TESTS/TEST_PROMPT_EXAM.PY — блок промпта «идёт экзамен»
# =========================================================
#   python tests\test_prompt_exam.py
#
# ЗАЧЕМ. Экзамен должен спрашивать РОВНО 10 вопросов и НЕ подсказывать.
# Это говорим модели блоком промпта. Главная опасность — сломать обычный
# промпт: smoke_test сверяет базу с gui.py из коммита b62c09a БАЙТ-В-БАЙТ,
# поэтому блок обязан добавляться ТОЛЬКО при exam=True и стоять В КОНЦЕ.
#
# Проверяем:
#   1) без флага промпт не изменился ни на символ (в т.ч. по позиции);
#   2) с флагом блок есть, он в КОНЦЕ и число вопросов подставляется;
#   3) прежние аргументы работают по-старому (порядок и имена не сломаны).
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

FAILED = []

PROFILE = {
    "mistakes": {"grammar": [], "vocabulary": []},
    "strengths": [],
    "topics_passed": [],
    "total_lessons": 0,
}


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    # ---------- 1. Без флага промпт прежний ----------
    print("[1] Без экзамена промпт не меняется")
    plain_lesson = pb.build_system_prompt("lesson", PROFILE)
    plain_free = pb.build_system_prompt("free", PROFILE)
    check("exam=False даёт тот же текст",
          pb.build_system_prompt("lesson", PROFILE, exam=False) == plain_lesson)
    check("exam=None/0 (ложь) тоже ничего не добавляет",
          pb.build_system_prompt("lesson", PROFILE, exam=None) == plain_lesson
          and pb.build_system_prompt("lesson", PROFILE, exam=0) == plain_lesson)
    check("слова EXAM нет в обычном промпте",
          "EXAM" not in plain_lesson and "EXAM" not in plain_free,
          plain_lesson[-80:])
    check("блок без флага пустой", pb._exam_block() == "", repr(pb._exam_block()))

    # ---------- 2. С флагом: блок в конце, вопросов ровно ----------
    print("\n[2] Экзамен: блок в конце и нужное число вопросов")
    exam_lesson = pb.build_system_prompt("lesson", PROFILE, exam=True)
    check("блок добавлен", "EXAM MODE" in exam_lesson)
    check("ровно 10 вопросов по умолчанию", "EXACTLY 10 questions" in exam_lesson,
          [l for l in exam_lesson.splitlines() if "EXACTLY" in l])
    check("по одному вопросу за раз", "one short question at a time" in exam_lesson)
    check("подсказок нет", "do not give hints or translations" in exam_lesson)
    check("по-русски — дальше", "answers in Russian, move on" in exam_lesson)
    check("блок стоит В КОНЦЕ промпта",
          exam_lesson.endswith(pb._exam_block(True, 10)), exam_lesson[-60:])
    check("текст БЕЗ блока сохранён целиком",
          exam_lesson.startswith(plain_lesson), "начало промпта поехало")
    check("добавка не пустая", len(exam_lesson) > len(plain_lesson),
          (len(plain_lesson), len(exam_lesson)))

    few = pb.build_system_prompt("lesson", PROFILE, exam=True, exam_questions=5)
    check("число вопросов подставляется (5)", "EXACTLY 5 questions" in few)
    check("и 10 при этом нет", "EXACTLY 10 questions" not in few)
    check("мусор в exam_questions → 10",
          "EXACTLY 10 questions" in pb._exam_block(True, "много"),
          pb._exam_block(True, "много")[-120:])

    # ---------- 3. Прежние аргументы не сломаны ----------
    print("\n[3] Старые вызовы работают по-старому")
    by_name = pb.build_system_prompt(mode="lesson", profile=PROFILE, lang="en",
                                     level="A2", variety=True,
                                     english_only=True, american=True)
    check("вызов по именам проходит", "AMERICAN ENGLISH" in by_name)
    check("и экзамена там нет", "EXAM MODE" not in by_name)
    by_pos = pb.build_system_prompt("lesson", PROFILE, "ru", "A1")
    check("вызов по позициям проходит", "STUDENT PROGRESS" in by_pos)
    check("аргументов в сигнатуре стало больше",
          "exam" in pb.build_system_prompt.__code__.co_varnames,
          pb.build_system_prompt.__code__.co_varnames[-4:])

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
