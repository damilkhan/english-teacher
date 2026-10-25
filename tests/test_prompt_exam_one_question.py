# =========================================================
# TESTS/TEST_PROMPT_EXAM_ONE_QUESTION.PY — «один вопрос на реплику»
# =========================================================
#   python tests\test_prompt_exam_one_question.py
#
# ЗАЧЕМ. Живой прогон экзамена (25.10.2026, logs/exam_live_run.txt) показал:
# ровно один «?» был только в 6 репликах из 10, в №5 и №9 модель задавала
# два вопроса подряд («Did you see a new movie? And what was the movie
# about?»). Ученик отвечает на оба и путается, а экзамен идёт по одному
# вопросу за раз. Поэтому в блок промпта добавлено правило про ОДИН «?».
#
# Проверяем:
#   1) новое правило есть в блоке и стоит ПОСЛЕ «one short question at a time»;
#   2) прежние фразы блока целы (их держат старые тесты и §20);
#   3) обычный промпт по-прежнему БЕЗ этого текста (не сломали базу);
#   4) блок остаётся В КОНЦЕ промпта и число вопросов подставляется.
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
    print(("  OK  " if ok else "  ПРОВАЛ ") + name + ("" if ok else "  << " + str(detail)))
    if not ok:
        FAILED.append(name)


def main():
    block = pb._exam_block(True, 10)

    print("[1] правило «один вопрос на реплику»")
    check("правило есть", "ONE QUESTION PER REPLY" in block, block[:80])
    check("ровно один «?» в реплике — сказано прямо",
          "exactly one question mark in each reply" in block)
    check("варианты — внутри одного вопроса",
          "keep them inside that single question" in block)
    check("пример альтернативного вопроса на месте",
          "on Saturday or on Sunday" in block)
    check("запрет двух вопросов подряд",
          "Never ask" in block and "two questions in one reply" in block)
    check("правило стоит ПОСЛЕ «one short question at a time»",
          0 < block.find("one short question at a time")
          < block.find("ONE QUESTION PER REPLY"), block)

    print("[2] прежние фразы блока целы")
    for phrase in ("EXAM MODE - CHECK OF THIS BLOCK",
                   "Ask EXACTLY 10 questions in total",
                   "one short question at a time",
                   "do not give hints or translations",
                   "answers in Russian, move on",
                   "Do not correct mistakes out loud"):
        check("на месте: %s" % phrase[:38], phrase in block)

    print("[3] обычный промпт не тронут")
    plain = pb.build_system_prompt("lesson", PROFILE, "en", level="A2",
                                   lesson={"title": "Hello", "type": "speaking"},
                                   exam=False)
    check("в обычном промпте нет нового правила",
          "ONE QUESTION PER REPLY" not in plain)
    check("и блока экзамена там нет", "EXAM MODE" not in plain)

    print("[4] блок в конце и число подставляется")
    exam_prompt = pb.build_system_prompt(
        "lesson", PROFILE, "en", level="A2",
        lesson={"title": "Hello", "type": "check"}, exam=True,
        exam_questions=10)
    check("блок стоит В КОНЦЕ промпта",
          exam_prompt.endswith(pb._exam_block(True, 10)), exam_prompt[-60:])
    check("новое правило дошло до промпта",
          "ONE QUESTION PER REPLY" in exam_prompt)
    few = pb._exam_block(True, 5)
    check("число вопросов подставляется (5)", "EXACTLY 5 questions" in few)
    check("и 10 при этом нет", "EXACTLY 10 questions" not in few)
    check("без флага блок пустой", pb._exam_block() == "")

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
