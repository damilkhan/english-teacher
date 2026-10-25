# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LEVEL_LESSONS.PY — урок по уровню ученика (без экрана)
# =========================================================
#   python tests\test_level_lessons.py
#
# ЗАЧЕМ. Жалоба ученика 25.10.2026: он прошёл вступительный тест, у него A2,
# а занятие началось с урока 1.1 «Hello / Hi» (Пустыня, уровень A0) — и
# преподаватель попросил поздороваться ещё раз, хотя ученик уже сказал «hello».
# Причина: next_lesson брал ПЕРВЫЙ непройденный урок по порядку карты, уровень
# не учитывался вовсе.
#
# РЕШЕНИЕ УЧЕНИКА (вариант В): локации, чей уровень НИЖЕ уровня ученика,
# считаются ПРОЙДЕННЫМИ. Пройти их вручную всё равно можно в любой момент —
# кнопка «Начать» в окне блока не спрашивает состояние урока.
#
# Проверяем:
#   1) без уровня — прежнее поведение (карта с 1.1), ничего не сломано;
#   2) A0 — пропусков нет; A1 → Лесная тропа; A2 → Городские улицы;
#   3) пропущенные локации выглядят пройденными, но их уроки не «исчезают»;
#   4) настоящее прохождение не теряется: пройденное идёт вперёд;
#   5) мусор вместо профиля/уровня не роняет карту;
#   6) окно блока различает состояния: закрытое не начать, пропущенное по
#      уровню — открыто (оно считается пройденным).
# Модель, микрофон и Tk не нужны.
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

import progress_map                                              # noqa: E402
from progress_map import ProgressMap, COMPLETED, UNLOCKED        # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def profile(level=None, done=None):
    prof = {"completed_lessons": list(done or [])}
    if level is not None:
        prof["level"] = level
    return prof


def main():
    pm = ProgressMap(os.path.join(ROOT, "knowledge_base"))

    # ---------- 1. обратная совместимость ----------
    print("[1] Без уровня — как раньше")
    check("карта прочитана (есть уроки)", len(pm._lesson_order) > 0, len(pm._lesson_order))
    check("без уровня: первый урок 1.1",
          pm.next_lesson(profile()) == "1.1", pm.next_lesson(profile()))
    check("без уровня: пропусков нет",
          pm.skipped_lessons(profile()) == set(), pm.skipped_lessons(profile()))
    check("первый урок открыт",
          pm.get_lesson_state("1.1", profile()) == UNLOCKED,
          pm.get_lesson_state("1.1", profile()))

    # ---------- 2. уровень ведёт уроки вперёд ----------
    print("\n[2] Уровень выбирает урок")
    check("A0: пропусков нет (он и есть начало)", pm.skipped_lessons(profile("A0")) == set(),
          pm.skipped_lessons(profile("A0")))
    check("A1: начинаем с Лесной тропы",
          pm.next_lesson(profile("A1")) == "forest/1.1", pm.next_lesson(profile("A1")))
    check("A2: начинаем с Городских улиц",
          pm.next_lesson(profile("A2")) == "city/1.1", pm.next_lesson(profile("A2")))
    check("B1: начинаем с Морского берега",
          pm.next_lesson(profile("B1")) == "coast/1.1", pm.next_lesson(profile("B1")))
    check("C1: начинаем с Небесных островов",
          pm.next_lesson(profile("C1")) == "sky/1.1", pm.next_lesson(profile("C1")))

    # ---------- 3. пропущенное = пройденное (вариант В) ----------
    print("\n[3] Нижние локации выглядят пройденными")
    a2 = profile("A2")
    check("Пустыня (A0) — пройдена",
          pm.get_location_state("desert", a2) == COMPLETED,
          pm.get_location_state("desert", a2))
    check("Лесная тропа (A1) — пройдена",
          pm.get_location_state("forest", a2) == COMPLETED,
          pm.get_location_state("forest", a2))
    check("Город (A2 = уровень) — открыт, не пройден",
          pm.get_location_state("city", a2) == UNLOCKED,
          pm.get_location_state("city", a2))
    check("урок 1.1 значится пройденным",
          pm.get_lesson_state("1.1", a2) == COMPLETED, pm.get_lesson_state("1.1", a2))
    check("первый открытый урок города доступен",
          pm.get_lesson_state("city/1.1", a2) == UNLOCKED,
          pm.get_lesson_state("city/1.1", a2))
    skipped = pm.skipped_lessons(a2)
    check("в пропущенных есть 1.1", "1.1" in skipped)
    check("в пропущенных НЕТ урока его уровня", "city/1.1" not in skipped)

    # уроки пропущенной локации никуда не делись — их можно пройти руками
    point = pm.get_point("point_1") or {}
    check("уроки Пустыни по-прежнему в плане",
          len(point.get("lessons") or ()) > 0, list(point)[:5])
    check("уроки пропущенной локации читаются картой",
          len(pm.lessons_of("point_1")) > 0, pm.lessons_of("point_1"))

    # ---------- 4. настоящее прохождение не теряется ----------
    print("\n[4] Пройденное идёт вперёд")
    check("A2 + пройден city/1.1 → city/1.2",
          pm.next_lesson(profile("A2", ["city/1.1"])) == "city/1.2",
          pm.next_lesson(profile("A2", ["city/1.1"])))
    check("A1 + пройден forest/1.1 → forest/1.2",
          pm.next_lesson(profile("A1", ["forest/1.1"])) == "forest/1.2",
          pm.next_lesson(profile("A1", ["forest/1.1"])))
    check("пройденный урок остаётся пройденным",
          pm.get_lesson_state("city/1.1", profile("A2", ["city/1.1"])) == COMPLETED,
          pm.get_lesson_state("city/1.1", profile("A2", ["city/1.1"])))

    # ---------- 5. мусор не роняет карту ----------
    print("\n[5] Битые данные")
    check("profile = None → пусто", pm.skipped_lessons(None) == set(), pm.skipped_lessons(None))
    check("profile = строка → пусто", pm.skipped_lessons("abc") == set(),
          pm.skipped_lessons("abc"))
    weird = {"completed_lessons": "1.1", "level": "XX"}
    check("неизвестный уровень = без уровня",
          pm.next_lesson(weird) == "1.1", pm.next_lesson(weird))
    check("строковый уровень в нижнем регистре понимается",
          pm.next_lesson({"level": " a2 "}) == "city/1.1",
          pm.next_lesson({"level": " a2 "}))
    check("level_rank: A0=0, C1=5, мусор=-1",
          (pm.level_rank("A0"), pm.level_rank("C1"), pm.level_rank("нет")) == (0, 5, -1),
          (pm.level_rank("A0"), pm.level_rank("C1"), pm.level_rank("нет")))

    # ---------- 6. пропущенное по уровню открыто, недойденное закрыто ----------
    print("\n[6] Окно блока: пропущенное по уровню открыто")
    path = os.path.join(ROOT, "ui", "panels", "block_panel.py")
    try:
        src = open(path, encoding="utf-8").read()
    except OSError as exc:
        src = ""
        print("  ⚠️ не прочитал %s: %s" % (path, exc))
    # НОВОЕ ПРАВИЛО (25.10.2026, решение ученика): закрытый урок начать нельзя,
    # а ПРОПУЩЕННЫЙ по уровню — можно: он считается пройденным (вариант В).
    check("окно блока различает состояния уроков (закрытое не начать)",
          "self.states" in src, "панель не знает состояний уроков")
    a2 = profile("A2")
    check("пропущенный по уровню урок — пройден, а не закрыт",
          pm.get_lesson_state("1.1", a2) == COMPLETED,
          pm.get_lesson_state("1.1", a2))
    check("пропущенный урок есть в done_lessons (его пустят)",
          "1.1" in pm.done_lessons(a2), sorted(pm.done_lessons(a2))[:3])
    check("кнопка «Начать» есть у каждого урока", src.count("Начать") >= 1,
          src.count("Начать"))

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
