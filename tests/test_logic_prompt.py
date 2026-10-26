# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LOGIC_PROMPT.PY — «вопрос должен иметь смысл»
# =========================================================
#   python tests\test_logic_prompt.py   (окно НЕ создаётся)
#
# Живой случай 26.10.2026: Вербот в уроке про dentist спросил «Do you watch a
# movie?» — в кабинете стоматолога кино не смотрят. Ученик поправил: «your
# question isn't correct, when you go to the dentist you don't have time to
# watch a movie». Ответ был: два извинения и новая выдумка «*before* / *after*
# the dentist», плюс звёздочки прямо в чате.
#
# Проверяем:
#   1) без флага промпт ПРЕЖНИЙ байт-в-байт (smoke_test не падает);
#   2) с флагом блок ровно один и он про смысл вопросов;
#   3) правило «не выдумывать факты о ситуации» в блоке есть;
#   4) реакция на поправку: одно извинение, без защиты вопроса;
#   5) блок стоит ДО блока слов ученика (порядок промпта);
#   6) приложение включает флаг в ОБОИХ вызовах chat_controller;
#   7) clean_response снимает курсив одной звёздочкой (звёздочки из скриншота).
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

import prompt_builder as pb                                    # noqa: E402

FAILED = []

PROFILE = {"name": "Дамиль", "level": "A2", "gender": "м",
           "completed_lessons": 12, "weak_topics": ["Past Simple"]}


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("=" * 64)
    print("Проверка блока «вопрос должен иметь смысл»")
    print("=" * 64)

    # ---------- 1. Без флага промпт прежний ----------
    print("\n[1] Без флага промпт НЕ меняется (smoke_test)")
    plain = pb.build_system_prompt("lesson", PROFILE, "en")
    explicit = pb.build_system_prompt("lesson", PROFILE, "en", logic=False)
    check("умолчание = явный False", plain == explicit)
    check("блока в промпте нет", pb.LOGIC_BLOCK not in plain)
    check("_logic_block(False) — пустая строка",
          pb._logic_block(False) == "", repr(pb._logic_block(False)))
    check("_logic_block(None) — тоже пусто", pb._logic_block(None) == "")

    # ---------- 2. С флагом блок есть, ровно один ----------
    print("\n[2] С флагом блок добавляется ровно один раз")
    on = pb.build_system_prompt("lesson", PROFILE, "en", logic=True)
    check("блок присутствует", pb.LOGIC_BLOCK in on)
    check("ровно один раз", on.count(pb.LOGIC_BLOCK) == 1,
          on.count(pb.LOGIC_BLOCK))
    check("промпт вырос ровно на блок",
          len(on) - len(plain) == len(pb.LOGIC_BLOCK),
          (len(on), len(plain), len(pb.LOGIC_BLOCK)))
    check("работает и в свободном общении",
          pb.LOGIC_BLOCK in pb.build_system_prompt("free", PROFILE, "en",
                                                   logic=True))

    # ---------- 3. Содержание правила ----------
    print("\n[3] Блок про смысл вопроса, а не про что попало")
    block = pb.LOGIC_BLOCK
    check("заголовок про проверку вопроса", "THINK BEFORE YOU ASK" in block)
    check("запрет выдумывать факты о месте",
          "Never invent facts about a place" in block)
    check("живой пример со стоматологом", "dentist" in block.lower())
    check("пример про кино в кабинете", "cinema" in block.lower())
    check("опираться на слова ученика", "their own words" in block)
    check("запрет приносить новую вещь/место/хобби",
          "Never bring a new thing" in block)
    check("запасной ход, когда спросить нечего", "Tell me more" in block)
    check("ровно ОДИН вопрос в конце", "ONE question per reply" in block)
    check("про поправку ученика", "student says your question is silly" in block)
    check("одно короткое согласие, без двух извинений",
          "Do not apologize twice" in block)
    check("не защищать вопрос", "defend the question" in block)
    check("не объяснять, зачем спросил",
          "explain why you asked it" in block)

    # ---------- 4. Порядок блоков ----------
    print("\n[4] Блок стоит до блока слов ученика")
    full = pb.build_system_prompt("lesson", PROFILE, "en", word_forms=True,
                                  logic=True, words=["flatbread", "rest"])
    i_forms = full.find("WORD MEANINGS AND WORD FORMS")
    i_logic = full.find("THINK BEFORE YOU ASK")
    i_words = full.find("WORDS FROM THE STUDENT")
    check("все три блока на месте", min(i_forms, i_logic, i_words) > 0,
          (i_forms, i_logic, i_words))
    check("значения слов → смысл вопроса → слова ученика",
          i_forms < i_logic < i_words, (i_forms, i_logic, i_words))

    # ---------- 5. Приложение включает флаг ----------
    print("\n[5] chat_controller включает флаг (оба вызова)")
    src = open(os.path.join(ROOT, "controllers", "chat_controller.py"),
               encoding="utf-8").read()
    check("logic=True встречается дважды", src.count("logic=True") == 2,
          src.count("logic=True"))
    check("флаг есть в сигнатуре build_system_prompt",
          "logic" in pb.build_system_prompt.__code__.co_varnames,
          pb.build_system_prompt.__code__.co_varnames[-5:])

    # ---------- 6. Звёздочки из скриншота ----------
    print("\n[6] clean_response: курсив одной звёздочкой снят")
    raw = ("Oh, you are right! Maybe you watch a movie *before* you go to the "
           "dentist, or *after*? What kind of movie do you like?")
    got = pb.clean_response(raw)
    check("звёздочек в чате нет", "*" not in got, repr(got))
    check("слова целы", "before" in got and "after" in got, repr(got))
    check("жирный текст по-прежнему чистится",
          pb.clean_response("Ответ **жирный** тут") == "Ответ жирный тут",
          repr(pb.clean_response("Ответ **жирный** тут")))
    check("числа с умножением не портятся",
          pb.clean_response("2*3*4") == "2*3*4",
          repr(pb.clean_response("2*3*4")))
    check("теги Gemma по-прежнему вырезаются",
          pb.clean_response("Готово <end_turn>") == "Готово",
          repr(pb.clean_response("Готово <end_turn>")))

    print()
    if FAILED:
        print("❌ ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("   - " + name)
        return 1
    print("✅ Все проверки пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
