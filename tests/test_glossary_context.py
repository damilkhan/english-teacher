# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GLOSSARY_CONTEXT.PY — контекст решает перевод фразы
# =========================================================
#   python tests\test_glossary_context.py
#
# ЗАЧЕМ. Жалоба ученика 25.10.2026: в реплике «It's great to see you
# today!» наведение на «see you» давало «Увидимся» (прощание), хотя здесь
# это «видеть тебя». Контекст решает, поэтому решает не модель, а простая
# таблица правил PHRASE_OVERRIDES: фраза + слово-переключатель рядом.
#
# Проверяем:
#   1) формула исключения: «to see you» → «видеть тебя»;
#   2) без переключателя («See you later!») смысл прежний — «Увидимся»;
#   3) другие переключатели (great / nice / glad / happy / want);
#   4) таблица работает и когда курсор на ВТОРОМ слове фразы;
#   5) обычные выражения не задеты (look forward to, nice to meet you);
#   6) правило с "ru": None велит переводить слово по слову;
#   7) фильтр склеек: «you tell», «you learn» в словарь НЕ попадают,
#      а настоящие обороты («I mean», «you know») — попадают;
#   8) правило есть в промпте модели (3c), счётчик overrides растёт.
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

import glossary   # noqa: E402

FAILED = []
TMP = os.path.join(ROOT, "logs", "_ctx_test.json")


def check(name, ok, detail=""):
    print(("  \u2705 " if ok else "  \u274c ") + name + ("" if ok else "  \u2190 " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def fresh(items_json):
    path = TMP
    if os.path.exists(path):
        os.remove(path)
    g = glossary.Glossary(path=path, autosave=False)
    g.add(glossary.parse_items(items_json))
    return g


BASE = ('{"items":['
        '{"en":"see you","ru":"\u0423\u0432\u0438\u0434\u0438\u043c\u0441\u044f","phrase":true},'
        '{"en":"see","ru":"\u0432\u0438\u0436\u0443","phrase":false},'
        '{"en":"you","ru":"\u0442\u0435\u0431\u044f","phrase":false},'
        '{"en":"Look forward to","ru":"\u0441 \u043d\u0435\u0442\u0435\u0440\u043f\u0435\u043d\u0438\u0435\u043c \u0436\u0434\u0430\u0442\u044c","phrase":true},'
        '{"en":"nice to meet you","ru":"\u041f\u0440\u0438\u044f\u0442\u043d\u043e \u043f\u043e\u0437\u043d\u0430\u043a\u043e\u043c\u0438\u0442\u044c\u0441\u044f","phrase":true}'
        ']}')


# ---------------------------------------------------------
print("[1] Формула исключения: «to see you» — не прощание")
g = fresh(BASE)
s = "It's great to see you today!"
hit = g.lookup(s, s.find("see"))
check("перевод стал «видеть тебя»", hit and hit["ru"] == "видеть тебя", hit)
check("фраза всё равно помечена как фраза", hit and hit["phrase"] is True, hit)
check("счётчик overrides вырос", g.stats["overrides"] == 1, g.stats)

print("\n[2] Без переключателя смысл прежний")
s2 = "See you later!"
hit2 = g.lookup(s2, 0)
check("«See you later» → «Увидимся»", hit2 and hit2["ru"] == "Увидимся", hit2)
s3 = "I will see you at six"
hit3 = g.lookup(s3, s3.find("see"))
check("«I will see you» → «Увидимся»", hit3 and hit3["ru"] == "Увидимся", hit3)

print("\n[3] Другие слова-переключатели")
pairs = [
    ("It's nice to see you again", "видеть тебя"),
    ("I am glad to see you", "видеть тебя"),
    ("She was happy to see you", "видеть тебя"),
    ("I want to see you happy", "видеть тебя"),
    ("Good to see you, friend", "видеть тебя"),
]
for sentence, expected in pairs:
    h = g.lookup(sentence, sentence.find("see"))
    check("«%s»" % sentence, h and h["ru"] == expected, h)

print("\n[4] Курсор на втором слове фразы")
s4 = "It's great to see you today!"
h4 = g.lookup(s4, s4.find("you"))
check("у «you» свой перевод — «тебя» (слово точнее фразы)",
      h4 and h4["ru"] == "тебя", h4)

print("\n[5] Обычные выражения не задеты")
s5 = "I look forward to it"
h5 = g.lookup(s5, s5.find("look"))
check("look forward to → «с нетерпением ждать»",
      h5 and h5["ru"] == "с нетерпением ждать", h5)
s6 = "Nice to meet you!"
h6 = g.lookup(s6, s6.find("meet"))
check("nice to meet you → «Приятно познакомиться»",
      h6 and h6["ru"] == "Приятно познакомиться", h6)

print("\n[6] Правило с ru=None велит переводить слово по слову")
glossary.PHRASE_OVERRIDES[("see", "you")].append(
    {"before": {"never"}, "ru": None})
try:
    s7 = "I never see you here"
    h7 = g.lookup(s7, s7.find("see"))
    check("фраза отброшена → слово «see» отдельно",
          h7 and h7["ru"] == "вижу" and h7["phrase"] is False, h7)
finally:
    glossary.PHRASE_OVERRIDES[("see", "you")].pop()

print("\n[7] Фильтр склеек «местоимение + глагол»")
glue = ('{"items":['
        '{"en":"you tell","ru":"\u0442\u044b \u0441\u043a\u0430\u0437\u0430\u0442\u044c","phrase":true},'
        '{"en":"you learn","ru":"\u0442\u0435\u0431\u0435 \u0443\u0447\u0438\u0442\u044c\u0441\u044f","phrase":true},'
        '{"en":"they were having","ru":"\u043e\u043d\u0438 \u0438\u043c\u0435\u043b\u0438","phrase":true},'
        '{"en":"I mean","ru":"\u044f \u0438\u043c\u0435\u044e \u0432 \u0432\u0438\u0434\u0443","phrase":true},'
        '{"en":"you know","ru":"\u0437\u043d\u0430\u0435\u0448\u044c","phrase":true},'
        '{"en":"take the bus","ru":"\u0435\u0445\u0430\u0442\u044c \u043d\u0430 \u0430\u0432\u0442\u043e\u0431\u0443\u0441\u0435","phrase":true}'
        ']}')
g2 = fresh(glue)
check("«you tell» не попала в словарь", ("you", "tell") not in g2.phrases, list(g2.phrases))
check("«you learn» не попала", ("you", "learn") not in g2.phrases, list(g2.phrases))
check("«they were having» не попала", ("they", "were", "having") not in g2.phrases)
check("«I mean» осталась", ("i", "mean") in g2.phrases, list(g2.phrases))
check("«you know» осталась", ("you", "know") in g2.phrases, list(g2.phrases))
check("«take the bus» осталась", ("take", "the", "bus") in g2.phrases, list(g2.phrases))
check("отказы посчитаны", g2.stats["rejected"] == 3, g2.stats)

print("\n[8] Правило есть в промпте модели")
check("в промпте пункт 3c", "3c." in glossary._SYSTEM, glossary._SYSTEM[-300:])
check("промпт запрещает склейку «you tell»", "you tell" in glossary._SYSTEM)
check("в промпте есть правило про контекст — нет, решает таблица",
      "PHRASE_OVERRIDES" in open(os.path.join(ROOT, "glossary.py"),
                                 encoding="utf-8").read())

if os.path.exists(TMP):
    os.remove(TMP)

print()
if FAILED:
    print("\u0418\u0422\u041e\u0413: \u043f\u0440\u043e\u0432\u0430\u043b\u043e\u0432: %d" % len(FAILED))
    for name in FAILED:
        print("  - " + name)
    sys.exit(1)
print("\u0418\u0422\u041e\u0413: \u0432\u0441\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u043f\u0440\u043e\u0439\u0434\u0435\u043d\u044b")
