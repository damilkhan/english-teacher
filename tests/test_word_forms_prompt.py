# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_WORD_FORMS_PROMPT.PY — значения и формы слов в промпте
# =========================================================
#   python tests\test_word_forms_prompt.py   (окно НЕ создаётся)
#
# Живой случай 26.10.2026: ученик сказал «I go to lie down» (лечь), а память
# подсказала ему «lie — лгать». Ответ был верным, но объяснения не было —
# ученик решил, что Вербот исправил его неверно. Решение ученика: правило
# ОБЩЕЕ для всех слов с двумя значениями, а не только про lie.
#
# Проверяем:
#   1) без флага промпт ПРЕЖНИЙ байт-в-байт (smoke_test не падает);
#   2) с флагом блока ровно один, и он про значения/формы слов;
#   3) правило общее: в блоке есть примеры разных слов, не только lie;
#   4) блок стоит ДО блока слов ученика (порядок промпта);
#   5) приложение реально включает флаг (оба вызова в chat_controller).
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
    print("Проверка блока «значения и формы слов» в промпте")
    print("=" * 64)

    # ---------- 1. Без флага промпт прежний ----------
    print("\n[1] Без флага промпт НЕ меняется (smoke_test)")
    plain = pb.build_system_prompt("lesson", PROFILE, "en")
    explicit = pb.build_system_prompt("lesson", PROFILE, "en", word_forms=False)
    check("умолчание = явный False", plain == explicit)
    check("в блоке нет блока про значения", pb.WORD_FORMS_BLOCK not in plain)
    check("_word_forms_block(False) — пустая строка",
          pb._word_forms_block(False) == "", repr(pb._word_forms_block(False)))
    check("_word_forms_block(None) — тоже пусто", pb._word_forms_block(None) == "")

    # ---------- 2. С флагом блок есть ----------
    print("\n[2] С флагом блок добавляется ровно один раз")
    on = pb.build_system_prompt("lesson", PROFILE, "en", word_forms=True)
    check("блок присутствует", pb.WORD_FORMS_BLOCK in on)
    check("ровно один раз", on.count(pb.WORD_FORMS_BLOCK) == 1,
          on.count(pb.WORD_FORMS_BLOCK))
    check("промпт стал длиннее ровно на блок",
          len(on) - len(plain) == len(pb.WORD_FORMS_BLOCK),
          (len(on), len(plain), len(pb.WORD_FORMS_BLOCK)))
    check("работает и в свободном общении",
          pb.WORD_FORMS_BLOCK in pb.build_system_prompt("free", PROFILE, "en",
                                                       word_forms=True))

    # ---------- 3. Правило общее, а не про lie ----------
    print("\n[3] Правило общее для ВСЕХ слов")
    block = pb.WORD_FORMS_BLOCK
    for word in ("lie", "lay", "left", "bank", "watch"):
        check("в примерах есть «%s»" % word, word in block)
    check("сказано «несколько значений»", "several meanings" in block)
    check("запрет подменять слово другим значением",
          "Never replace" in block)
    check("нужны три формы глагола", "lie - lay - lain" in block)
    check("про разницу литературного и разговорного варианта",
          "colloquial" in block)
    check("требование коротко: одна фраза", "one short sentence" in block.lower()
          or "ONE short line" in block)

    # ---------- 4. Порядок блоков ----------
    print("\n[4] Блок стоит до блока слов ученика")
    words = pb.build_system_prompt("lesson", PROFILE, "en", word_forms=True,
                                   words=["flatbread", "rest"])
    i_forms = words.find("WORD MEANINGS AND WORD FORMS")
    i_words = words.find("WORDS FROM THE STUDENT")
    check("оба блока на месте", i_forms > 0 and i_words > 0, (i_forms, i_words))
    check("значения слов идут ПЕРЕД словами ученика", 0 < i_forms < i_words,
          (i_forms, i_words))

    # ---------- 5. Приложение включает флаг ----------
    print("\n[5] chat_controller включает флаг (оба вызова)")
    src = open(os.path.join(ROOT, "controllers", "chat_controller.py"),
               encoding="utf-8").read()
    check("word_forms=True встречается дважды", src.count("word_forms=True") == 2,
          src.count("word_forms=True"))
    check("флаг в сигнатуре build_system_prompt",
          "word_forms=False" in pb.build_system_prompt.__code__.co_varnames
          or "word_forms" in pb.build_system_prompt.__code__.co_varnames,
          pb.build_system_prompt.__code__.co_varnames[-6:])

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
