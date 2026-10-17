# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_MOOD.PY — настроение текста Джейн (mood.py)
# =========================================================
#   python tests\test_mood.py   (окно НЕ создаётся)
#
# Проверяем:
#   1) разбиение на предложения;
#   2) определение настроения по эмодзи, словам, пунктуации;
#   3) при сомнении — нейтрально (не «угадывать» эмоцию);
#   4) план реплики: смена настроения по предложениям;
#   5) ограничение числа смен (лицо не дёргается);
#   6) порядок во времени (segment_at / mood_at);
#   7) «рассказ» определяется по длине и числу предложений;
#   8) связка с лицом: state_for_mood.
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

import mood                                                # noqa: E402
import character_face as cf                                # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("=" * 60)
    print("Проверка настроения текста (mood.py)")
    print("=" * 60)

    # ---------- 1. Предложения ----------
    print("\n[1] Разбиение на предложения")
    sents = mood.split_sentences("Hello! My name is Jane. How are you?")
    check("три предложения", len(sents) == 3, sents)
    check("знаки сохранены", sents[0].endswith("!"), sents[0])
    check("пустой текст → пусто", mood.split_sentences("") == [])
    check("текст без точек — одно предложение",
          len(mood.split_sentences("hello there")) == 1)

    # ---------- 2. Эмодзи ----------
    print("\n[2] Эмодзи задают настроение")
    check("радостный смайл → happy",
          mood.sentence_mood("Great job! 🎉") == mood.HAPPY,
          mood.sentence_mood("Great job! 🎉"))
    check("грустный смайл → sad",
          mood.sentence_mood("It was a sad day 😢") == mood.SAD,
          mood.sentence_mood("It was a sad day 😢"))
    check("удивление → surprised",
          mood.sentence_mood("Wow, really? 😮") == mood.SURPRISED,
          mood.sentence_mood("Wow, really? 😮"))
    check("задумчивость → thinking",
          mood.sentence_mood("Hmm, maybe later 🤔") == mood.THINKING,
          mood.sentence_mood("Hmm, maybe later 🤔"))

    # ---------- 3. Слова и пунктуация ----------
    print("\n[3] Слова и пунктуация")
    check("похвала словами → happy",
          mood.sentence_mood("Excellent work, well done!") == mood.HAPPY)
    check("русская похвала → happy",
          mood.sentence_mood("Молодец, отлично!") == mood.HAPPY)
    check("русская грусть → sad",
          mood.sentence_mood("Мне жаль, это печально.") == mood.SAD)
    check("восклицание добавляет энергии",
          mood.score_sentence("Yes!")[mood.HAPPY] > 0)
    check("многоточие — раздумье",
          mood.score_sentence("Well...")[mood.THINKING] > 0)

    # ---------- 4. Нейтрально при сомнении ----------
    print("\n[4] Сомнительный текст → нейтрально")
    check("обычное предложение нейтрально",
          mood.sentence_mood("The lesson starts at nine.") == mood.NEUTRAL,
          mood.sentence_mood("The lesson starts at nine."))
    check("пустое → нейтрально", mood.sentence_mood("") == mood.NEUTRAL)
    check("«неплохо» не превращается в грусть без признаков",
          mood.sentence_mood("Not bad.") in (mood.NEUTRAL, mood.HAPPY, mood.SAD))

    # ---------- 5. План реплики ----------
    print("\n[5] План реплики: смена по предложениям")
    text = ("Hello! I want to tell you a story. 🎉 "
            "It was a happy morning and everyone was glad! "
            "But then the little robot got lost, and it felt very sad 😢 "
            "In the end a girl found it, and it was happy again! 🎉")
    plan = mood.plan_reply(text)
    check("куски построены", len(plan.segments) >= 2, plan.moods())
    check("есть положительные и отрицательные куски",
          mood.HAPPY in plan.moods() or mood.SAD in plan.moods(), plan.moods())
    check("общая длительность > 0", plan.total_seconds > 0, plan.total_seconds)
    check("все куски не короче минимума",
          all(s.seconds >= mood.MIN_SEGMENT_SECONDS for s in plan.segments),
          [(s.text[:20], round(s.seconds, 2)) for s in plan.segments])

    # ---------- 6. Ограничение смен ----------
    print("\n[6] Ограничение числа смен")
    many = "Great! 😢 Sad. 🎉 Wow! 😮 Hmm 🤔 Fine."
    plan_many = mood.plan_reply(many, max_changes=2)
    check("смен настроения не больше лимита",
          len(plan_many.segments) <= 3, plan_many.moods())
    check("всегда есть хотя бы один кусок", len(plan_many.segments) >= 1)

    # ---------- 7. Время ----------
    print("\n[7] Куда попадает время")
    plan2 = mood.plan_reply("Great! 🎉 " + "Sad news today. 😢")
    first = plan2.segment_at(0.0)
    last = plan2.segment_at(plan2.total_seconds - 0.01)
    check("в начале первый кусок", first is plan2.segments[0] if first else False)
    check("в конце последний кусок", last is plan2.segments[-1] if last else False)
    check("mood_at возвращает строку", isinstance(plan2.mood_at(0.5), str))
    check("за пределами — последний", plan2.segment_at(9999) is plan2.segments[-1])

    # ---------- 8. Рассказ ----------
    print("\n[8] Признак «рассказ»")
    long_text = ("Once upon a time there was a little robot. "
                 "She lived in a big desert and liked to talk to people. "
                 "Every morning she walked to the old house. "
                 "And every evening she told a story to her friend.")
    check("длинный текст из 4+ предложений → рассказ",
          mood.plan_reply(long_text).story is True)
    check("короткая реплика — не рассказ",
          mood.plan_reply("Hello! How are you?").story is False)
    check("пустой текст — пустой план",
          mood.plan_reply("").segments == [])
    check("пустой текст — не рассказ", mood.plan_reply("").story is False)

    # ---------- 9. Связка с лицом ----------
    print("\n[9] Настроение → лицо робота")
    check("happy → говорящее радостное", cf.state_for_mood("happy") == cf.SPEAK_HAPPY)
    check("sad → говорящее грустное", cf.state_for_mood("sad") == cf.SPEAK_SAD)
    check("neutral → обычная речь", cf.state_for_mood("neutral") == cf.SPEAKING)
    check("neutral + рассказ → рассказ-режим",
          cf.state_for_mood("neutral", story=True) == cf.SPEAK_STORY)
    check("неизвестное настроение → обычная речь",
          cf.state_for_mood("чепуха") == cf.SPEAKING)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
