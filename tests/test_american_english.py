# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_AMERICAN_ENGLISH.PY — американский английский, живые слова
# =========================================================
#   python tests\test_american_english.py    (модель НЕ нужна)
#
# Зачем: ученик возмутился (20.10.2026) — Джейн «преподавала» книжные
# слова: greeting, salutation, «it is a warm greeting», а в плане стояли
# британские формы (Colours, favourite, Travelling, film, holiday).
# Причина: переводчик слова отдавал СИНОНИМЫ как «разные значения», все они
# становились карточками повторения, а в промпте не было ни слова про США.
#
# Проверяем:
#   1) выключатель AMERICAN_ENGLISH в config.py;
#   2) блок «USE AMERICAN ENGLISH» в промпте — и что БЕЗ него промпт прежний;
#   3) ChatController передаёт флаг при обоих запросах (в т.ч. при повторе);
#   4) Планировщик просит живые американские слова;
#   5) план уроков без британских написаний и книжных названий;
#   6) фильтр значений: британский синоним и повтор не попадают в карточки;
#   7) инструкция модели запрещает синонимы и книжные слова.
# =========================================================

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config            # noqa: E402
import prompt_builder    # noqa: E402
import translate         # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  \u2705 " if ok else "  \u274c ") + name + ("" if ok else "  \u2190 " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


FULL_PROFILE = {
    "mistakes": {"grammar": [], "vocabulary": []},
    "strengths": [],
    "topics_passed": ["Saying Hi"],
    "total_lessons": 3,
}


# =========================================================
# 1. Выключатель
# =========================================================
def test_config():
    print("\n[1] Выключатель в config.py")
    check("AMERICAN_ENGLISH есть и включён",
          bool(getattr(config, "AMERICAN_ENGLISH", False)),
          getattr(config, "AMERICAN_ENGLISH", "нет"))


# =========================================================
# 2. Блок в промпте
# =========================================================
def test_prompt_block():
    print("\n[2] Блок «USE AMERICAN ENGLISH» и прежний промпт без него")
    off = prompt_builder.build_system_prompt("lesson", FULL_PROFILE, "en")
    explicit_off = prompt_builder.build_system_prompt(
        "lesson", FULL_PROFILE, "en", american=False)
    on = prompt_builder.build_system_prompt(
        "lesson", FULL_PROFILE, "en", american=True)
    check("без флага промпт байт-в-байт прежний", off == explicit_off)
    check("без флага блока нет", "USE AMERICAN ENGLISH" not in off)
    check("с флагом блок есть", "USE AMERICAN ENGLISH" in on)
    check("блок просит американские слова",
          "movie" in on and "apartment" in on and "favorite" in on)
    check("блок запрещает книжные слова",
          "greeting" in on and "salutation" in on)
    check("флаг США, а не Британии",
          "\U0001F1FA\U0001F1F8" in on and "\U0001F1EC\U0001F1E7" not in on)
    check("режим free тоже получает блок",
          "USE AMERICAN ENGLISH"
          in prompt_builder.build_system_prompt("free", FULL_PROFILE, "en",
                                                american=True))

    # блок должен быть НЕОБЯЗАТЕЛЬНЫМ и стоять до плана/слов (§10)
    with_plan = prompt_builder.build_system_prompt(
        "lesson", FULL_PROFILE, "en", american=True,
        plan="1. Warm-up", words=["ключ — key"])
    check("блок стоит до плана и слов",
          with_plan.index("USE AMERICAN ENGLISH")
          < with_plan.index("TODAY'S LESSON PLAN")
          < with_plan.index("WORDS FROM THE STUDENT"))


# =========================================================
# 3. Контроллер передаёт флаг
# =========================================================
def test_chat_controller():
    print("\n[3] ChatController передаёт флаг в ОБА запроса")
    src = io.open(os.path.join(ROOT, "controllers", "chat_controller.py"),
                  encoding="utf-8").read()
    count = src.count("american=bool(getattr(config, \"AMERICAN_ENGLISH\"")
    check("флаг передан дважды (обычный запрос и повтор)", count == 2, count)


# =========================================================
# 4. Планировщик
# =========================================================
def test_planner():
    print("\n[4] Планировщик просит живые американские слова")
    src = io.open(os.path.join(ROOT, "roles", "planner.py"),
                  encoding="utf-8").read()
    check("просит AMERICAN English", "AMERICAN English only" in src)
    check("запрещает книжные слова", "salutation" in src)
    check("даёт пример живой лексики", '"how\'s it going"' in src)


# =========================================================
# 5. План уроков
# =========================================================
def test_curriculum():
    print("\n[5] План уроков без британских и книжных названий")
    data = json.load(io.open(os.path.join(ROOT, "knowledge_base",
                                          "curriculum.json"), encoding="utf-8"))
    locations = data["locations"]
    lessons = sum(len(p["lessons"]) for loc in locations for p in loc["points"])
    check("13 локаций", len(locations) == 13, len(locations))
    check("468 уроков", lessons == 468, lessons)
    texts = []
    for loc in locations:
        for pt in loc["points"]:
            texts.append(pt["block_title"])
            texts.extend(ls["title"] for ls in pt["lessons"])
    joined = " | ".join(texts).lower()
    for bad in ("colour", "favourite", "travelling", "organised",
                "holiday", "film", "practise", "greeting", "salutation"):
        check("нет «%s»" % bad, bad not in joined)
    check("блок называется «Saying Hi»",
          "Saying Hi" in texts, [t for t in texts if "Hi" in t][:3])
    check("цвета по-американски",
          any(t == "Colors" for t in texts) and "Basic colors" in texts)
    # прогресс ученика не должен поехать: id «Пустыни» остались простыми
    desert = locations[0]
    check("id «Пустыни» простые (прогресс цел)",
          desert["points"][0]["lessons"][0]["id"] == "1.1",
          desert["points"][0]["lessons"][0]["id"])
    check("у «Лесной тропы» id с префиксом",
          locations[1]["points"][0]["lessons"][0]["id"] == "forest/1.1",
          locations[1]["points"][0]["lessons"][0]["id"])
    # координата снята с новой картинки «Пустыни» (белый кружок с цифрой 1);
    # раскладки всех локаций и попадание в кружки — tests/test_map_points.py
    check("координаты точек на месте (9 у «Пустыни»)",
          len(desert["points"]) == 9
          and desert["points"][0]["point"] == [231, 697],
          desert["points"][0]["point"])


# =========================================================
# 6. Фильтр значений переводчика
# =========================================================
def test_trim_meanings():
    print("\n[6] Фильтр: британский синоним и повтор не идут в карточки")
    got = translate._trim_meanings([
        "movie \u2014 We watched a great movie.",
        "film \u2014 That old film is good.",
        "movie \u2014 I saw it twice.",
    ])
    check("остался только movie", got == ["movie \u2014 We watched a great movie."], got)

    got = translate._trim_meanings([
        "apartment \u2014 A nice apartment.",
        "flat \u2014 My flat has a view.",
    ])
    check("flat отброшен", len(got) == 1 and got[0].startswith("apartment"), got)

    got = translate._trim_meanings([
        "hello \u2014 Hello, how are you?",
        "greeting \u2014 It is a warm greeting.",
        "salutation \u2014 A quick salutation.",
    ])
    check("greeting/salutation отброшены", got == ["hello \u2014 Hello, how are you?"], got)

    got = translate._trim_meanings([
        "pen \u2014 Grab a pen to sign this form.",
        "handle \u2014 Pull the handle on the door.",
    ])
    check("настоящее второе значение сохранено (pen/handle)", len(got) == 2, got)

    got = translate._trim_meanings([
        "key \u2014 Use your key to open the door.",
        "key \u2014 This is the key to the puzzle.",
    ])
    check("одно и то же слово дважды не дублируется", len(got) == 1, got)

    got = translate._trim_meanings(["shop \u2014 A small shop."], limit=3)
    check("первая строка не трогается никогда (даже британская)",
          got == ["shop \u2014 A small shop."], got)

    got = translate._trim_meanings(["a \u2014 1", "b \u2014 2", "c \u2014 3", "d \u2014 4"])
    check("не больше трёх значений", len(got) == 3, got)


# =========================================================
# 7. Инструкция модели-переводчику
# =========================================================
def test_word_prompt():
    print("\n[7] Инструкция переводчику: живые слова, без синонимов")
    prompt = translate.WORD_SYSTEM_PROMPT
    check("просит американский английский", "American English" in prompt)
    check("синонимы прямо запрещены", "SYNONYMS ARE NOT DIFFERENT MEANINGS" in prompt)
    check("книжные слова перечислены как запрещённые",
          "salutation" in prompt and "greeting" in prompt)
    check("есть примеры британских подмен",
          "not \u00abfilm\u00bb" in prompt and "not \u00abflat\u00bb" in prompt)


# =========================================================
# 8. Слово для карточки — без знаков
# =========================================================
def test_normalize_word():
    print("\n[8] Слово карточки без точек и кавычек")
    check("«привет.» → «привет»", translate.normalize_word("привет.") == "привет",
          translate.normalize_word("привет."))
    check("« Ключ! » → «ключ»", translate.normalize_word(" Ключ! ") == "ключ",
          translate.normalize_word(" Ключ! "))
    src = io.open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
    check("приложение сохраняет слово через normalize_word",
          "translate.normalize_word(source)" in src)


def main():
    print("=" * 60)
    print("Проверка американского английского и живых слов")
    print("=" * 60)
    test_config()
    test_prompt_block()
    test_chat_controller()
    test_planner()
    test_curriculum()
    test_trim_meanings()
    test_word_prompt()
    test_normalize_word()

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d \u2192 %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()