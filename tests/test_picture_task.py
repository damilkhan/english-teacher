# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PICTURE_TASK.PY — логика задания «опиши фото»
# =========================================================
#   python tests\test_picture_task.py
#
# Без окна и без сети: каталог, выбор фото, порог букв, защита от накрутки.
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

import config                              # noqa: E402
import picture_task as pt                  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def test_levels():
    print("\n[1] Уровни и порог букв")
    check("'a2' → 'A2'", pt.normalize_level("a2") == "A2")
    check("' B1 ' → 'B1'", pt.normalize_level(" B1 ") == "B1")
    check("мусор → ''", pt.normalize_level("XX") == "", pt.normalize_level("XX"))
    check("пусто → ''", pt.normalize_level(None) == "")
    check("порог A2 = 105", pt.threshold_for("A2") == 105, pt.threshold_for("A2"))
    check("порог B1 = 135", pt.threshold_for("B1") == 135, pt.threshold_for("B1"))
    check("порог A0 = 40", pt.threshold_for("A0") == 40)
    check("неизвестный уровень → как A2", pt.threshold_for("") == 105)
    check("уровень для порога у пустого — A2", pt.level_for_threshold("") == "A2")
    check("порог = число", isinstance(pt.threshold_for("A2"), int))


def test_letters():
    print("\n[2] Буквы и слова")
    check("'It is a cat.' = 8 букв", pt.letters("It is a cat.") == 8,
          pt.letters("It is a cat."))
    check("цифры и знаки не считаются", pt.letters("123 !? ,") == 0)
    check("кириллица считается буквой", pt.letters("да") == 2)
    check("пусто = 0", pt.letters("") == 0 and pt.letters(None) == 0)
    check("слова: только латиница", pt.words("A cat, a Dog!") == ["a", "cat", "a", "dog"],
          pt.words("A cat, a Dog!"))
    total, unique, share = pt.word_stats("cat cat cat dog")
    check("слов 4", total == 4, total)
    check("разных 2", unique == 2, unique)
    check("доля частого 0.75", abs(share - 0.75) < 1e-9, share)
    check("пустой текст: 0, 0, 0.0", pt.word_stats("") == (0, 0, 0.0))


def test_check():
    print("\n[3] Проверка описания (A2, порог 105)")
    good = ("There are many shops on the street. People are walking in the wet "
            "street. The sky is grey and the weather is cloudy. I can see a bus "
            "and two red cars near the old building.")
    res = pt.check_description(good, "A2")
    check("нормальное описание принято", res["ok"], res)
    check("букв столько же, сколько посчитали",
          res["letters"] == pt.letters(good), res["letters"])
    check("порог в ответе", res["threshold"] == 105)
    check("причина отказа пуста", res["reason"] is None)

    short = pt.check_description("A street with people.", "A2")
    check("короткий ответ отклонён", not short["ok"])
    check("причина too_short", short["reason"] == "too_short", short["reason"])

    repeated = pt.check_description("cat " * 60, "A2")
    check("повтор одного слова отклонён", not repeated["ok"])
    check("причина repeated", repeated["reason"] == "repeated", repeated["reason"])

    few = pt.check_description("one two three one two three " * 10, "A2")
    check("мало разных слов — отклонён", not few["ok"], few)
    check("причина few_words", few["reason"] == "few_words", few["reason"])

    exact = "a" * 105
    check("ровно порог — уже не short",
          pt.check_description(exact, "A2")["reason"] != "too_short")
    check("ниже порога на 1 — short", pt.check_description("a" * 104, "A2")["reason"]
          == "too_short")
    a2_text = ("shops people street weather cloudy walking buildings windows "
               "trees cars buses cafe table chairs coffee bread water morning "
               "evening station train ticket")
    a2_text = " ".join(a2_text.split())
    check("текст для B1 — 105..134 букв", 105 <= pt.letters(a2_text) < 135,
          pt.letters(a2_text))
    check("уровень B1 строже: 105+ букв всё равно мало",
          pt.check_description(a2_text, "B1")["reason"] == "too_short")
    check("тот же текст для A2 — принят",
          pt.check_description(a2_text, "A2")["ok"],
          pt.check_description(a2_text, "A2"))
    check("порог в ответе — 135 для B1",
          pt.check_description(good, "B1")["threshold"] == 135)


def test_catalog():
    print("\n[4] Каталог фото")
    catalog = pt.load_catalog()
    check("20 фото в каталоге", len(catalog) == 20, len(catalog))
    check("у записи есть абсолютный путь",
          os.path.isabs(catalog["a2/city-street"]["path"]), catalog.get("a2/city-street"))
    check("файл на месте", os.path.exists(catalog["a2/city-street"]["path"]))
    check("A0 — 5 фото", len(pt.pictures_for_level("A0")) == 5,
          len(pt.pictures_for_level("A0")))
    check("A1 — 6 фото", len(pt.pictures_for_level("A1")) == 6)
    check("A2 — 9 фото", len(pt.pictures_for_level("A2")) == 9)
    check("B1 — своих нет, берём A2", len(pt.pictures_for_level("B1")) == 9,
          len(pt.pictures_for_level("B1")))
    check("без уровня — A0", len(pt.pictures_for_level("")) == 5)
    check("все ключи A2 на месте",
          all(k.startswith("a2/") for k in pt.pictures_for_level("A2")))
    picked = pt.pick_picture("A2")
    check("выбор не пустой", picked and picked.startswith("a2/"), picked)
    check("уже показанное не повторяем",
          pt.pick_picture("A2", used=[picked]) != picked)
    check("все показаны — берём из списка снова",
          pt.pick_picture("A2", used=pt.pictures_for_level("A2")) in
          pt.pictures_for_level("A2"))


def test_describe_task():
    print("\n[5] Данные задания")
    task = pt.describe_task("A2")
    check("задание собралось", task is not None)
    check("порог 105", task["threshold"] == 105, task["threshold"])
    check("уровень A2", task["level"] == "A2")
    check("есть тема", bool(task.get("topic")), task.get("topic"))
    check("есть пункты", isinstance(task.get("points"), list) and task["points"])
    check("картинка существует", os.path.exists(task["path"]), task["path"])
    check("пороги в config на все уровни",
          set(config.PICTURE_LETTER_THRESHOLDS) == {"A0", "A1", "A2", "B1", "B2", "C1"},
          sorted(config.PICTURE_LETTER_THRESHOLDS))
    check("отправлять не меньше 768 px",
          config.PICTURE_MIN_SEND_SIDE >= 768, config.PICTURE_MIN_SEND_SIDE)


def main():
    print("=" * 60)
    print("ЗАДАНИЕ С КАРТИНКОЙ: логика")
    print("=" * 60)
    test_levels()
    test_letters()
    test_check()
    test_catalog()
    test_describe_task()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛОВ: %d" % len(FAILED))
        for name in FAILED:
            print("  - " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
