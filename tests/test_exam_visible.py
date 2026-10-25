# =========================================================
# TESTS/TEST_EXAM_VISIBLE.PY — балл экзамена ВИДЕН (карта и окно блока)
# =========================================================
#   python tests\test_exam_visible.py
#
# ЗАЧЕМ. record_exam писал балл в профиль, но увидеть его было негде:
# exam_result() никто не вызывал. Теперь балл показывается плашкой
# («8/10 ✓») в подсказке жетона карты и в окне блока. Проверяем ЧИСТЫЕ
# функции без Tk: профиль → плашка → текст подсказки.
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

import profile_store                                              # noqa: E402
from ui.widgets.map_view import tooltip_text, point_exam_badge     # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


# =========================================================
# 1. Балл → текст
# =========================================================
def test_score_text():
    print("\n[1] exam_score_text: «8/10», дробный, мусор")
    check("8 → «8/10»", profile_store.exam_score_text(8) == "8/10",
          profile_store.exam_score_text(8))
    check("8.0 → «8/10» (без хвоста .0)",
          profile_store.exam_score_text(8.0) == "8/10",
          profile_store.exam_score_text(8.0))
    check("8.5 → «8.5/10»", profile_store.exam_score_text(8.5) == "8.5/10",
          profile_store.exam_score_text(8.5))
    check("0 → «0/10» (ноль показываем честно)",
          profile_store.exam_score_text(0) == "0/10",
          profile_store.exam_score_text(0))
    check("12 → «10/10» (выше максимума не рисуем)",
          profile_store.exam_score_text(12) == "10/10",
          profile_store.exam_score_text(12))
    check("«не число» → пусто", profile_store.exam_score_text("не число") == "",
          profile_store.exam_score_text("не число"))
    check("None → пусто", profile_store.exam_score_text(None) == "",
          profile_store.exam_score_text(None))
    check("минус → пусто", profile_store.exam_score_text(-3) == "",
          profile_store.exam_score_text(-3))


# =========================================================
# 2. Запись профиля → плашка
# =========================================================
def test_badge():
    print("\n[2] exam_badge: галочка только за сданный")
    passed = profile_store.exam_badge({"score": 8, "passed": True})
    failed = profile_store.exam_badge({"score": 5, "passed": False})
    check("сдал → «8/10 ✓»", passed == "8/10 \u2713", repr(passed))
    check("не сдал → «5/10» без галочки", failed == "5/10", repr(failed))
    check("пустая запись → пусто", profile_store.exam_badge({}) == "",
          profile_store.exam_badge({}))
    check("не словарь → пусто", profile_store.exam_badge(None) == "",
          profile_store.exam_badge(None))
    check("битый балл → пусто",
          profile_store.exam_badge({"score": "ой", "passed": True}) == "",
          profile_store.exam_badge({"score": "ой", "passed": True}))


# =========================================================
# 3. Весь профиль → все плашки
# =========================================================
def test_badges():
    print("\n[3] exam_badges: {id урока: плашка}")
    profile = {"exams": {
        "desert/1.4": {"score": 9, "passed": True, "attempts": 2},
        "forest/1.4": {"score": 4, "passed": False, "attempts": 1},
        "city/1.4": {"score": "мусор"},
    }}
    badges = profile_store.exam_badges(profile)
    check("две годные записи", len(badges) == 2, badges)
    check("сданный — с галочкой", badges.get("desert/1.4") == "9/10 \u2713",
          badges.get("desert/1.4"))
    check("несданный — без галочки", badges.get("forest/1.4") == "4/10",
          badges.get("forest/1.4"))
    check("битая запись не попадает", "city/1.4" not in badges, badges)
    check("профиль без экзаменов → {}", profile_store.exam_badges({}) == {},
          profile_store.exam_badges({}))
    check("exams не словарь → {}", profile_store.exam_badges({"exams": []}) == {},
          profile_store.exam_badges({"exams": []}))


# =========================================================
# 4. Балл на жетоне: какой урок блока считать экзаменом
# =========================================================
def test_point_badge():
    print("\n[4] point_exam_badge: берём запись любого урока блока")
    badges = {"2.4": "7/10 \u2713"}
    check("запись у последнего урока блока",
          point_exam_badge(["2.1", "2.2", "2.3", "2.4"], badges) == "7/10 \u2713",
          point_exam_badge(["2.1", "2.2", "2.3", "2.4"], badges))
    check("записей нет → пусто", point_exam_badge(["2.1", "2.2"], {}) == "",
          point_exam_badge(["2.1", "2.2"], {}))
    check("пустой список уроков → пусто", point_exam_badge([], badges) == "",
          point_exam_badge([], badges))
    check("уроки не строки — не падаем", point_exam_badge([1, 2], {}) == "",
          point_exam_badge([1, 2], {}))


# =========================================================
# 5. Подсказка жетона: вторая строка
# =========================================================
def test_tooltip():
    print("\n[5] tooltip_text: балл — ВТОРОЙ строкой")
    plain = tooltip_text(1, "Greetings", 3)
    check("без балла — одна строка", "\n" not in plain, repr(plain))
    check("без балла — как раньше", plain == "Блок 1: Greetings — 3 урока",
          repr(plain))
    with_exam = tooltip_text(1, "Greetings", 3, "8/10 \u2713")
    lines = with_exam.split("\n")
    check("с баллом — две строки", len(lines) == 2, repr(with_exam))
    check("вторая строка про экзамен",
          lines[1] == "Экзамен: 8/10 \u2713", repr(lines[1]))
    check("первая строка не изменилась", lines[0] == plain, repr(lines[0]))
    check("пустой балл — без второй строки",
          "\n" not in tooltip_text(1, "", 2, ""),
          repr(tooltip_text(1, "", 2, "")))


def main():
    test_score_text()
    test_badge()
    test_badges()
    test_point_badge()
    test_tooltip()
    print("\n" + ("ИТОГ: все проверки пройдены" if not FAILED
                  else "ИТОГ: провалов %d — %s" % (len(FAILED), ", ".join(FAILED))))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
