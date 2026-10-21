# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PROGRESS_MAP.PY — логика карты прогресса
# =========================================================
#   python tests\test_progress_map.py   (без окна, без модели)
#
# Проверяем progress_map.ProgressMap:
#   1) загрузка РЕАЛЬНОГО curriculum.json (9 точек, порядок по number);
#   2) состояния точки: первая открыта, остальные закрыты;
#   3) после прохождения точки — она completed, следующая unlocked;
#   4) состояния урока: строгий порядок внутри точки;
#   5) прогресс точки и локации;
#   6) вложенные sublessons (рекурсивный обход);
#   7) безопасные дефолты: нет файла / битый JSON / старый формат «blocks».
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

from progress_map import ProgressMap, LOCKED, UNLOCKED, COMPLETED   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def write_curriculum(folder, data):
    path = os.path.join(folder, "curriculum.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return path


def sample():
    """Небольшая учебная программа: 3 точки по 2 урока."""
    return {
        "version": 1,
        "locations": [{
            "id": "desert", "title": "Пустыня", "level": "A0",
            "image": "assets/map/desert.png", "size": [1248, 832],
            "points": [
                {"id": "p1", "number": 1, "point": [10, 10], "block_title": "One",
                 "lessons": [{"id": "1.1", "title": "a", "type": "speaking"},
                             {"id": "1.2", "title": "b", "type": "speaking"}]},
                {"id": "p2", "number": 2, "point": [20, 20], "block_title": "Two",
                 "lessons": [{"id": "2.1", "title": "c", "type": "chat"},
                             {"id": "2.2", "title": "d", "type": "speaking"}]},
                {"id": "p3", "number": 3, "point": [30, 30], "block_title": "Three",
                 "lessons": [{"id": "3.1", "title": "e", "type": "speaking"}]},
            ],
        }],
    }


def main():
    print("=" * 60)
    print("Проверка логики карты прогресса (ProgressMap)")
    print("=" * 60)

    # ---------- 1. Реальный curriculum.json ----------
    print("\n[1] Реальный knowledge_base/curriculum.json")
    pm = ProgressMap(os.path.join(ROOT, "knowledge_base"))
    ids = pm.location_ids()
    check("первая локация — desert", bool(ids) and ids[0] == "desert", ids)
    # программа полная: A0 → C1 (13 локаций, см. tools/build_curriculum.py)
    check("13 локаций по программе", len(ids) == 13, ids)
    loc = pm.get_location("desert")
    check("у локации есть image и size",
          loc.get("image") == "assets/map/desert.png" and loc.get("size") == [1248, 832],
          (loc.get("image"), loc.get("size")))
    pts = pm.points_of("desert")
    check("9 точек", len(pts) == 9, len(pts))
    numbers = [p.get("number") for p in pts]
    check("точки идут по порядку number 1..9", numbers == list(range(1, 10)), numbers)
    check("у первой точки на карте номер 1", pts[0].get("number") == 1)

    # ---------- 2. Пустой профиль ----------
    print("\n[2] Пустой профиль: открыта только первая точка")
    empty = {"completed_lessons": []}
    check("точка 1 unlocked", pm.get_point_state("point_1", empty) == UNLOCKED,
          pm.get_point_state("point_1", empty))
    check("точка 2 locked", pm.get_point_state("point_2", empty) == LOCKED,
          pm.get_point_state("point_2", empty))
    check("точка 9 locked", pm.get_point_state("point_9", empty) == LOCKED,
          pm.get_point_state("point_9", empty))
    check("первый урок открыт", pm.get_lesson_state("1.1", empty) == UNLOCKED,
          pm.get_lesson_state("1.1", empty))
    check("второй урок закрыт", pm.get_lesson_state("1.2", empty) == LOCKED,
          pm.get_lesson_state("1.2", empty))
    check("прогресс локации 0/9", pm.get_location_progress("desert", empty) == (0, 9),
          pm.get_location_progress("desert", empty))
    check("вторая локация закрыта",
          pm.get_location_state(ids[1], empty) == LOCKED,
          pm.get_location_state(ids[1], empty))
    check("её первая точка тоже закрыта",
          pm.get_point_state(pm.points_of(ids[1])[0]["id"], empty) == LOCKED)

    # ---------- 3. Линейное продвижение ----------
    print("\n[3] Частичное прохождение")
    profile = {"completed_lessons": ["1.1"]}
    check("урок 1.1 completed", pm.get_lesson_state("1.1", profile) == COMPLETED)
    check("урок 1.2 unlocked после 1.1", pm.get_lesson_state("1.2", profile) == UNLOCKED)
    check("урок 2.1 всё ещё locked", pm.get_lesson_state("2.1", profile) == LOCKED)
    check("точка 1 ещё не completed (1 из 4 уроков)",
          pm.get_point_state("point_1", profile) == UNLOCKED)
    check("прогресс точки 1 — (1, 4)",
          pm.get_point_progress("point_1", profile) == (1, 4),
          pm.get_point_progress("point_1", profile))
    check("в блоке есть проверочное занятие",
          any(l.get("type") == "check"
              for l in pm.lessons_of("point_1")),
          [l.get("type") for l in pm.lessons_of("point_1")])

    profile = {"completed_lessons": ["1.1", "1.2", "1.3", "1.4"]}
    check("точка 1 completed (3 урока + проверка)",
          pm.get_point_state("point_1", profile) == COMPLETED,
          pm.get_point_state("point_1", profile))
    check("точка 2 unlocked", pm.get_point_state("point_2", profile) == UNLOCKED,
          pm.get_point_state("point_2", profile))
    check("точка 3 locked (2 не пройдена)", pm.get_point_state("point_3", profile) == LOCKED)
    check("прогресс локации 1/9", pm.get_location_progress("desert", profile) == (1, 9),
          pm.get_location_progress("desert", profile))

    # ---------- 4. Всё пройдено ----------
    print("\n[4] Полное прохождение")
    all_lessons = [l["id"] for p in pts for l in pm.lessons_of(p["id"])]
    check("всего 36 уроков в локации (9 блоков × 4)",
          len(all_lessons) == 36, len(all_lessons))
    done = {"completed_lessons": all_lessons}
    check("все точки completed",
          all(pm.get_point_state(p["id"], done) == COMPLETED for p in pts))
    check("прогресс локации 9/9", pm.get_location_progress("desert", done) == (9, 9))

    # ---------- 5. Прогресс точки ----------
    print("\n[5] Прогресс точки")
    check("точка без уроков → (0, 0)", pm.get_point_progress("нет-такой", done) == (0, 0))
    check("неизвестная точка → locked", pm.get_point_state("нет-такой", done) == LOCKED)
    check("неизвестный урок → locked", pm.get_lesson_state("99.9", done) == LOCKED)
    check("неизвестная локация → (0, 0)",
          pm.get_location_progress("нет-такой", done) == (0, 0))
    check("get_location(неизвестный) → {}", pm.get_location("нет-такой") == {})

    # ---------- 6. Синтетика: sublessons и порядок ----------
    print("\n[6] sublessons и сортировка по number")
    tmp = tempfile.mkdtemp(prefix="et_map_")
    data = sample()
    # точки в файле идут В ПЕРЕМЕШКУ — порядок обязан восстановиться по number
    data["locations"][0]["points"] = [
        {"id": "p2", "number": 2, "block_title": "Two", "lessons": [
            {"id": "2.1", "title": "c", "type": "chat"}]},
        {"id": "p1", "number": 1, "block_title": "One", "lessons": [
            {"id": "1.1", "title": "a", "type": "speaking", "sublessons": [
                {"id": "1.1.1", "title": "a-formal", "type": "speaking"},
                {"id": "1.1.2", "title": "a-informal", "type": "speaking"}]},
            {"id": "1.2", "title": "b", "type": "speaking"}]},
        {"id": "p3", "number": 3, "block_title": "Three", "lessons": [
            {"id": "3.1", "title": "e", "type": "speaking"}]},
    ]
    write_curriculum(tmp, data)
    pm2 = ProgressMap(tmp)
    order = [p["id"] for p in pm2.points_of("desert")]
    check("точки отсортированы по number (p1, p2, p3)", order == ["p1", "p2", "p3"], order)
    lessons = [l["id"] for l in pm2.lessons_of("p1")]
    check("sublessons развёрнуты по порядку", lessons == ["1.1", "1.1.1", "1.1.2", "1.2"], lessons)
    e = {"completed_lessons": []}
    check("с подуроками: 1.1 открыт, 1.1.1 закрыт",
          pm2.get_lesson_state("1.1", e) == UNLOCKED
          and pm2.get_lesson_state("1.1.1", e) == LOCKED)
    p = {"completed_lessons": ["1.1"]}
    check("после 1.1 открывается его подурок 1.1.1",
          pm2.get_lesson_state("1.1.1", p) == UNLOCKED, pm2.get_lesson_state("1.1.1", p))
    check("прогресс точки p1 — (1, 4)",
          pm2.get_point_progress("p1", p) == (1, 4), pm2.get_point_progress("p1", p))

    # ---------- 7. Безопасные дефолты ----------
    print("\n[7] Безопасные дефолты")
    broken = tempfile.mkdtemp(prefix="et_map_broken_")
    with open(os.path.join(broken, "curriculum.json"), "w", encoding="utf-8") as fh:
        fh.write("{ это не json")
    pm3 = ProgressMap(broken)
    check("битый JSON: локаций нет", pm3.location_ids() == [])
    check("битый JSON: локация → {}", pm3.get_location("desert") == {})
    check("битый JSON: точка → locked", pm3.get_point_state("point_1", {}) == LOCKED)
    check("битый JSON: прогресс → (0, 0)", pm3.get_location_progress("desert", {}) == (0, 0))

    missing = tempfile.mkdtemp(prefix="et_map_missing_")
    pm4 = ProgressMap(missing)
    check("нет файла: локаций нет", pm4.location_ids() == [])
    check("нет файла: урок → locked", pm4.get_lesson_state("1.1", {}) == LOCKED)

    old = tempfile.mkdtemp(prefix="et_map_old_")
    write_curriculum(old, {"version": 1, "locations": [
        {"id": "desert", "title": "Пустыня", "level": "A0",
         "blocks": [{"id": "a0_greetings", "title": "Greetings", "lessons": []}]}]})
    pm5 = ProgressMap(old)
    check("старый формат 'blocks' не роняет", pm5.points_of("desert") == [])
    check("старый формат: локация всё равно находится",
          pm5.get_location("desert").get("title") == "Пустыня")

    # профиль не той формы — тоже безопасно
    check("profile=None → первая точка открыта, вторая закрыта",
          pm.get_point_state("point_1", None) == UNLOCKED
          and pm.get_point_state("point_2", None) == LOCKED)
    check("profile без completed_lessons → первая точка открыта",
          pm.get_point_state("point_1", {"mistakes": {}}) == UNLOCKED)
    check("completed_lessons не список → пусто",
          pm.completed_lessons({"completed_lessons": "1.1"}) == set())

    # ---------- 8. Запись прогресса (profile_store) ----------
    print("\n[8] profile_store: отметка урока не считает «занятие»")
    import profile_store
    real_path = profile_store.PROFILE_PATH
    tmp_prof = tempfile.mkdtemp(prefix="et_map_prof_")
    try:
        profile_store.PROFILE_PATH = os.path.join(tmp_prof, "student_profile.json")
        profile_store.set_active_user(None)
        prof, _created = profile_store.ensure_profile()
        check("новый профиль содержит completed_lessons",
              prof.get("completed_lessons") == [], prof.get("completed_lessons"))
        base_lessons = prof.get("total_lessons", 0)
        check("первая запись урока → True",
              profile_store.record_lesson_completed("1.1") is True)
        check("повторная запись → False",
              profile_store.record_lesson_completed("1.1") is False)
        saved = profile_store.load()
        check("урок сохранён", saved.get("completed_lessons") == ["1.1"],
              saved.get("completed_lessons"))
        check("total_lessons не изменился (урок ≠ занятие)",
              saved.get("total_lessons", 0) == base_lessons, saved.get("total_lessons"))
        check("карта видит пройденный урок",
              pm.get_lesson_state("1.1", saved) == COMPLETED)
        # старый профиль без ключа — мягкая миграция
        with open(profile_store.PROFILE_PATH, "w", encoding="utf-8") as fh:
            json.dump({"total_lessons": 3, "mistakes": {}}, fh)
        check("старый профиль: ключ добавляется сам",
              profile_store.load().get("completed_lessons") == [])
    finally:
        profile_store.PROFILE_PATH = real_path
        profile_store.set_active_user(None)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
