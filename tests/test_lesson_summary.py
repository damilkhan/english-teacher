# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_SUMMARY.PY — итог ОБЫЧНОГО занятия (без экрана)
# =========================================================
#   python tests\test_lesson_summary.py
#
# ЗАЧЕМ. До 25.10.2026 итог был только у экзамена, а обычный урок кончался
# одной строкой «🎉 Урок пройден!». Счётчики hints/mistakes копились зря.
#
# Решения ученика (25.10.2026):
#   * показывать в конце: реплики, подсказки, ошибки + похвалу;
#   * НУЛИ показывать («Подсказок: 0», «Ошибок: 0»);
#   * подсказки НЕ наказывают (обычное занятие);
#   * голосом — короткая АНГЛИЙСКАЯ похвала, русский итог — текстом.
#
# Проверяем:
#   1) summary_text: заголовок, счётчики, нули, блок пройден целиком;
#   2) mistake_note: пороги 0 / 1–2 / 3+;
#   3) praise_text: склонение mistake/mistakes, ТОЛЬКО латиница (иначе
#      английский голос читает русский текст мусором);
#   4) мусор на входе (None, строки) не роняет.
# Модель, микрофон и сеть не нужны.
# =========================================================

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import lesson_summary                                            # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def session(replies=12, target=12, hints=3, mistakes=2,
            lesson_id="city/1.1"):
    """Как LessonSession, но без lesson.py (итогу нужны только счётчики)."""
    return types.SimpleNamespace(replies=replies, target=target,
                                reply_target=target, hints=hints,
                                mistakes=mistakes, lesson_id=lesson_id)


def has_cyrillic(text):
    for ch in text:
        if "\u0400" <= ch <= "\u04FF":
            return True
    return False


print("[1] Итог обычного занятия (русский текст)")

s = session()
text = lesson_summary.summary_text(s)

check("есть «Урок city/1.1 пройден»", "Урок city/1.1 пройден" in text, text)
check("реплики «12 из 12»", "🗣 Реплик: 12 из 12" in text, text)
check("подсказки посчитаны", "💡 Подсказок: 3" in text, text)
check("ошибки посчитаны", "📝 Ошибок: 2" in text, text)
check("похвала в конце", text.rstrip().endswith(
    lesson_summary.mistake_note(2)), text)
check("нет пустых строк", "\n\n" not in text, repr(text))
check("без блока нет слова «Блок»", "Блок" not in text, text)

with_block = lesson_summary.summary_text(s, block_title="В городе")
check("блок пройден целиком", "Блок «В городе» пройден целиком" in with_block,
      with_block)

print("[2] Нули показываем честно")

zero = lesson_summary.summary_text(session(hints=0, mistakes=0))
check("«Подсказок: 0» видно", "💡 Подсказок: 0" in zero, zero)
check("«Ошибок: 0» видно", "📝 Ошибок: 0" in zero, zero)
check("«Реплик: 12 из 12» на месте", "🗣 Реплик: 12 из 12" in zero, zero)

print("[3] Урок без id (крайний случай)")

no_id = lesson_summary.summary_text(session(lesson_id=""))
check("«🎉 Урок пройден!» без номера", no_id.startswith("🎉 Урок пройден!"),
      no_id)
check("нет двойного пробела", "  " not in no_id, repr(no_id))

print("[4] Пороги похвалы (решения ученика)")

check("0 ошибок → «чисто»", "чисто" in lesson_summary.mistake_note(0),
      lesson_summary.mistake_note(0))
check("1 ошибка → «пара ошибок»", "Пара ошибок" in lesson_summary.mistake_note(1),
      lesson_summary.mistake_note(1))
check("2 ошибки → «пара ошибок»", "Пара ошибок" in lesson_summary.mistake_note(2),
      lesson_summary.mistake_note(2))
check("3 ошибки → «есть что повторить»",
      "Есть что повторить" in lesson_summary.mistake_note(3),
      lesson_summary.mistake_note(3))
check("10 ошибок → «есть что повторить»",
      "Есть что повторить" in lesson_summary.mistake_note(10),
      lesson_summary.mistake_note(10))
check("мусор в ошибках не роняет", isinstance(lesson_summary.mistake_note("abc"),
                                              str),
      lesson_summary.mistake_note("abc"))

print("[5] Английская похвала для голоса")

clean = lesson_summary.praise_text(session(mistakes=0))
check("0 ошибок → no mistakes", "no mistakes" in clean and "Well done" in clean,
      clean)

one = lesson_summary.praise_text(session(mistakes=1))
check("1 ошибка → «1 mistake.» (не mistakes)",
      "only 1 mistake." in one, one)

two = lesson_summary.praise_text(session(mistakes=2))
check("2 ошибки → «2 mistakes»", "only 2 mistakes" in two, two)

many = lesson_summary.praise_text(session(mistakes=5))
check("5 ошибок → Nice try", many.startswith("Nice try!") and "5 mistakes" in many,
      many)

check("в похвале есть число реплик", "12 replies" in two, two)
check("похвала БЕЗ кириллицы (иначе английский голос сломается)",
      not has_cyrillic(two), two)
check("похвала БЕЗ кириллицы и при нуле ошибок", not has_cyrillic(clean), clean)
check("похвала не пустая при мусоре",
      lesson_summary.praise_text(None).strip() != "",
      lesson_summary.praise_text(None))

print("[6] Итог из state() словарём (как зовёт чат)")

state = {"lesson_id": "forest/1.2", "replies": 12, "target": 12,
         "hints": 0, "mistakes": 4}
dict_text = lesson_summary.summary_text(state)
check("словарь понят как сессия", "Урок forest/1.2 пройден" in dict_text,
      dict_text)
check("«Реплик: 12 из 12» из словаря", "12 из 12" in dict_text, dict_text)
check("ошибки из словаря", "📝 Ошибок: 4" in dict_text, dict_text)

print("[7] Два сообщения конца занятия")

pair = lesson_summary.finish_messages(s, block_title="В городе")
check("ровно два сообщения", isinstance(pair, tuple) and len(pair) == 2, pair)
check("первое — русский итог", "Урок city/1.1 пройден" in pair[0], pair[0])
check("второе — английское", not has_cyrillic(pair[1]), pair[1])

print("[8] Числительные не склеены с формой слова")

one_reply = lesson_summary.summary_text(session(replies=1))
check("«Реплик: 1 из 12» (нет «1 реплик»)",
      "Реплик: 1 из 12" in one_reply and "1 реплик" not in one_reply,
      one_reply)

print()
if FAILED:
    print("❌ ПРОВАЛОВ: %d" % len(FAILED))
    for name in FAILED:
        print("   • " + name)
    sys.exit(1)
print("✅ Все проверки итога занятия пройдены.")
