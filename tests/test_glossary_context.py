# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GLOSSARY_CONTEXT.PY — перевод зависит ОТ РЕПЛИКИ
# =========================================================
#   python tests\test_glossary_context.py
#
# ЗАЧЕМ. Было: таблица PHRASE_OVERRIDES «лечила» пословный перевод вручную
# («great to see you» — это не прощание). Стало (03.11.2026): переводим
# КУСКАМИ ПО СМЫСЛУ, и контекст решает САМА модель — а код хранит разбор
# ПРИВЯЗАННЫМ К РЕПЛИКЕ, чтобы «see you» в разных репликах не путались.
#
# Проверяем:
#   1) один и тот же кусок в разных репликах переводится по-разному;
#   2) разбор одной реплики не подсказывает в другой;
#   3) в промпте есть запрет перевода слово-в-слово (пункт 3, пункт 6);
#   4) старые ручные таблицы убраны из кода (их работу делает модель);
#   5) код по-прежнему проверяет покрытие: пропуск слова — брак.
# =========================================================

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import glossary                                                   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def fresh(chunks):
    g = glossary.Glossary(llm=None, path=os.path.join(tempfile.mkdtemp(),
                                                      "g.json"))
    return g, chunks


# ---------------------------------------------------------
print("[1] Один кусок — два разных смысла в двух репликах")

GREAT = "It's great to see you today!"
BYE = "See you later!"

g = glossary.Glossary(llm=None, path=os.path.join(tempfile.mkdtemp(), "g.json"))
g.add_chunks(GREAT, [["It's", "это"], ["great", "здорово"],
                     ["to see you", "видеть тебя"], ["today", "сегодня"]])
g.add_chunks(BYE, [["See you", "увидимся"], ["later", "позже"]])

hit1 = g.lookup(GREAT, GREAT.index("see"))
check("«great to see you» → видеть тебя", hit1 and hit1["ru"] == "видеть тебя", hit1)

hit2 = g.lookup(BYE, BYE.index("See"))
check("«See you later» → увидимся", hit2 and hit2["ru"] == "увидимся", hit2)
check("это ДВА разных разбора в кэше", len(g.chunks) == 2, list(g.chunks))

# ---------------------------------------------------------
print("\n[2] Разбор не перетекает из реплики в реплику")
OTHER = "You see the window there?"
check("реплика без разбора — подсказки нет", g.lookup(OTHER, 4) is None)
check("чужая реплика не «вылечилась» сама", not g.known(OTHER))

# ---------------------------------------------------------
print("\n[3] Промпт: запрет слово-в-слово")
system = glossary._SYSTEM
check("пункт 3 запрещает пословный перевод", "3." in system and "word-by-word" in system)
check("в примере — «Would you like» → хотели бы вы",
      "Would you like" in system and "хотели бы вы" in system)
check("пункт 4 снимает предел длины куска", "word count" in system)
check("пункт 6 не даёт оторвать артикль", "article or preposition" in system)

# ---------------------------------------------------------
print("\n[4] Ручные таблицы убраны: смысл решает модель")
source = open(os.path.join(ROOT, "glossary.py"), encoding="utf-8").read()
check("PHRASE_OVERRIDES больше нет", "PHRASE_OVERRIDES" not in source)
check("пословного «Include EVERY word» в промпте нет",
      "Include EVERY word" not in source)
check("предела MAX_PHRASE_WORDS нет", "MAX_PHRASE_WORDS" not in source)

# ---------------------------------------------------------
print("\n[5] Покрытие проверяет КОД (не модель)")
LONG = "I'd like to book a table for two."
check("разбор по кускам покрывает реплику",
      glossary.covers(LONG, [["I'd like", "я хотел бы"],
                             ["to book", "забронировать"],
                             ["a table", "столик"],
                             ["for two", "на двоих"]]))
check("пропуск слова — брак",
      not glossary.covers(LONG, [["I'd like", "я хотел бы"],
                                 ["to book", "забронировать"],
                                 ["a table", "столик"]]))
check("лишнее слово в разборе — брак",
      not glossary.covers(LONG, [["I'd like", "я хотел бы"],
                                 ["to book", "забронировать"],
                                 ["a table", "столик"],
                                 ["for two", "на двоих"],
                                 ["please", "пожалуйста"]]))
check("порядок нарушен — брак",
      not glossary.covers(LONG, [["a table", "столик"],
                                 ["I'd like", "я хотел бы"],
                                 ["to book", "забронировать"],
                                 ["for two", "на двоих"]]))

# ---------------------------------------------------------
print("\n" + ("ИТОГ: провалов %d" % len(FAILED) if FAILED
              else "ИТОГ: все проверки пройдены"))
if FAILED:
    print("  " + ", ".join(FAILED))
sys.exit(1 if FAILED else 0)
