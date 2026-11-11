# -*- coding: utf-8 -*-
"""Тест §76: фраза вместо слова и зачёт только за ответ по заданию.

Живой урок city/3.3 (11.11.2026): Аналитик вернул правку одним словом
(sell, buy, bought), код просил повторять слово, STT слышал «cell/seal/till»,
а задание при этом засчитывалось за «bye» и «bolger».

Запуск: python tests/test_lesson_phrase.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import lesson as L

FAILS = []


def check(title, ok, detail=""):
    if ok:
        print("  ok   %s" % title)
    else:
        print("  ❌   %s  %s" % (title, detail))
        FAILS.append(title)


print("[1] fix_sentence: правка-слово превращается во ФРАЗУ")
got = L.fix_sentence("i don't sell anything", ["sell"], ["buy"])
check("слово заменено в своей фразе",
      got.lower() == "i don't buy anything", repr(got))
# реальный случай из лога: «usually i pay a card» -> «i pay with the card»
got2 = L.fix_sentence("usually i pay a card", ["pay a card"],
                      ["pay with a card"])
check("меняется кусок из трёх слов",
      got2.lower() == "usually i pay with a card", repr(got2))
check("регистр не важен",
      L.fix_sentence("I usually Pay a card", ["pay"], ["pay with"]) != "")
check("нет пары — фраза остаётся прежней",
      L.fix_sentence("i want a jacket", [], ["buy"]).lower()
      == "i want a jacket")
check("одно слово фразой не считается", L.fix_sentence("sell", ["sell"], ["buy"]) == "")
check("пустая реплика -> пусто", L.fix_sentence("", ["sell"], ["buy"]) == "")


print("[2] looks_like_answer: мусор задание не сдаёт")
for bad in ("bye", "bolger", "buy", "cell", "ok", "no, thanks", "yes"):
    check("«%s» — не ответ" % bad, L.looks_like_answer(bad) is False)
for good in ("i want to pay with a card", "i bought a hat at the store",
             "i was relaxing", "i don't buy anything", "we are two"):
    check("«%s» — ответ" % good, L.looks_like_answer(good) is True)


print("[3] expect_repeat: просим повторить ФРАЗУ, а не слово")
s = L.LessonSession("city/3.3", lesson_type="speaking")
s.expect_repeat(["buy"], wrongs=["sell"], said="i don't sell anything")
check("фраза в repeat_expected",
      list(s.repeat_expected) == ["i don't buy anything"],
      s.repeat_expected)
check("фаза «ждём повтор»", s.task_phase == L.TASK_FIX, s.task_phase)
check("ученик повторил фразу -> зачёт", s.says_fix("I don't buy anything") is True)
check("ученик сказал только слово -> НЕ зачёт", s.says_fix("buy") is False)


print("[4] фразу собрать не удалось — слово не подставляем")
s2 = L.LessonSession("city/3.3", lesson_type="speaking")
words = s2.expect_repeat(["buy"], wrongs=["sell"], said="sell")
check("одно слово не стало фразой", L._words_count(words[0]) < L.MIN_PHRASE_WORDS,
      words)


print("[5] зачёт по смыслу по-прежнему работает")
s3 = L.LessonSession("city/3.3", lesson_type="speaking")
s3.expect_repeat(["i would like to see"], wrongs=["i want to see"],
                 said="i want to see")
check("повтор с «would like» засчитан",
      s3.says_fix("i would like to see") is True)


print("[6] приложение и контроллер используют новые правила")
src_app = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
check("app передаёт реплику в expect_repeat", "said=text" in src_app)
check("зашитого «Almost!» больше нет", "Almost! Now say it once more" not in src_app)
check("гейт «не ответ» на месте", "looks_like_answer(text)" in src_app)
check("подсказки распознаванию для урока есть",
      "_lesson_stt_words" in src_app and
      "parts.extend(self._lesson_stt_words())" in src_app)
check("одно слово повторять не просим",
      "MIN_PHRASE_WORDS" in src_app)

print()
if FAILS:
    print("ПРОВАЛОВ: %d -> %s" % (len(FAILS), "; ".join(FAILS)))
    sys.exit(1)
print("ВСЁ ХОРОШО")
