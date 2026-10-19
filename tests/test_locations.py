# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LOCATIONS.PY — локации программы и проверочные занятия
# =========================================================
#   python tests\test_locations.py   (окно и модель НЕ нужны)
#
# Решение ученика: уроков мало — нужны ПРОВЕРОЧНЫЕ занятия в каждом блоке,
# а программа должна идти от A0 до C1 по разным локациям.
#
# Проверяем:
#   1) план: 13 локаций (A0 → C1), у каждой 9 блоков;
#   2) в каждом блоке 3 урока + ПРОВЕРКА (тип "check"), всего 468 уроков;
#   3) id блоков и уроков УНИКАЛЬНЫ в плане (иначе повтор «1.1» съедался
#      как дубликат и карта читала только первую локацию);
#   4) «Пустыня» сохранила простые id (1.1, 1.2 …) — прогресс не теряется;
#   5) локации открываются по очереди: первая — всегда, следующая — когда
#      предыдущая пройдена целиком; закрытая локация закрывает свои блоки;
#   6) next_lesson идёт сквозь блоки и локации, включая проверки;
#   7) проверочное занятие: тип, подпись, лимит реплик, инструкция Джейн.
# =========================================================

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

import config                                              # noqa: E402
import lesson                                              # noqa: E402
import progress_map                                        # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


PM = progress_map.ProgressMap(os.path.join(ROOT, "knowledge_base"))


def all_lessons(loc_id):
    return [lid for p in PM.points_of(loc_id) for lid in PM._point_lessons[p["id"]]]


# =========================================================
# 1-3. План
# =========================================================
def test_plan():
    print("\n[1] Программа A0 → C1: 13 локаций")
    ids = PM.location_ids()
    check("13 локаций", len(ids) == 13, len(ids))
    levels = [PM.get_location(i).get("level") for i in ids]
    check("уровни идут A0 → C1 без пропусков",
          levels == ["A0", "A1", "A1", "A2", "A2", "B1", "B1", "B1",
                     "B2", "B2", "B2", "C1", "C1"], levels)
    check("у каждой локации 9 блоков",
          all(len(PM.points_of(i)) == 9 for i in ids),
          [(i, len(PM.points_of(i))) for i in ids])

    print("\n[2] В каждом блоке 3 урока + проверка")
    total = 0
    checks = 0
    problems = []
    for loc_id in ids:
        for point in PM.points_of(loc_id):
            lessons = PM.lessons_of(point["id"])
            types = [l.get("type") for l in lessons]
            total += len(lessons)
            if len(lessons) != 4 or types.count("check") != 1:
                problems.append((point["id"], types))
            checks += types.count("check")
    check("всего 468 уроков", total == 468, total)
    check("117 проверочных занятий (по одному на блок)", checks == 117, checks)
    check("в каждом блоке ровно 4 урока, один из них check",
          not problems, problems[:3])
    check("проверка — последний урок блока",
          all(PM.lessons_of(p["id"])[-1].get("type") == "check"
              for loc_id in ids for p in PM.points_of(loc_id)))

    print("\n[3] id уникальны во всём плане")
    point_ids = [p["id"] for loc_id in ids for p in PM.points_of(loc_id)]
    lesson_ids = [l["id"] for loc_id in ids for p in PM.points_of(loc_id)
                  for l in PM.lessons_of(p["id"])]
    check("117 разных блоков", len(set(point_ids)) == 117, len(set(point_ids)))
    check("468 разных уроков", len(set(lesson_ids)) == 468, len(set(lesson_ids)))
    check("карта видит ВСЕ уроки плана", len(PM._lesson_order) == 468,
          len(PM._lesson_order))

    print("\n[4] «Пустыня» сохранила старые id (прогресс не потерян)")
    desert = all_lessons("desert")
    check("уроки Пустыни — простые id (1.1, 1.4 …)",
          "1.1" in desert and "1.4" in desert and "9.4" in desert, desert[:4])
    check("у новой локации id с префиксом",
          "forest/1.1" in all_lessons("forest"), all_lessons("forest")[:3])
    check("у всех уроков есть короткий КОД для экрана",
          PM.get_lesson("forest/1.1").get("code") == "1.1",
          PM.get_lesson("forest/1.1"))


# =========================================================
# 5. Порядок открытия локаций
# =========================================================
def test_unlock():
    print("\n[5] Локации открываются по очереди")
    ids = PM.location_ids()
    empty = {"completed_lessons": []}
    check("первая локация открыта",
          PM.get_location_state(ids[0], empty) == progress_map.UNLOCKED,
          PM.get_location_state(ids[0], empty))
    check("вторая закрыта",
          PM.get_location_state(ids[1], empty) == progress_map.LOCKED,
          PM.get_location_state(ids[1], empty))
    check("её первый блок закрыт",
          PM.get_point_state(PM.points_of(ids[1])[0]["id"], empty)
          == progress_map.LOCKED)
    check("её первый урок закрыт",
          PM.get_lesson_state(all_lessons(ids[1])[0], empty)
          == progress_map.LOCKED)
    check("карта показывает первую локацию",
          PM.first_open_location(empty) == ids[0], PM.first_open_location(empty))

    done_first = {"completed_lessons": all_lessons(ids[0])}
    check("первая локация пройдена",
          PM.get_location_state(ids[0], done_first) == progress_map.COMPLETED,
          PM.get_location_state(ids[0], done_first))
    check("вторая открылась",
          PM.get_location_state(ids[1], done_first) == progress_map.UNLOCKED,
          PM.get_location_state(ids[1], done_first))
    check("третья всё ещё закрыта",
          PM.get_location_state(ids[2], done_first) == progress_map.LOCKED)
    check("её первый урок открыт",
          PM.get_lesson_state(all_lessons(ids[1])[0], done_first)
          == progress_map.UNLOCKED)
    check("карта перешла на вторую локацию",
          PM.first_open_location(done_first) == ids[1],
          PM.first_open_location(done_first))

    partial = {"completed_lessons": all_lessons(ids[0])[:30]}
    check("недопройденная локация не открывает следующую",
          PM.get_location_state(ids[1], partial) == progress_map.LOCKED)


# =========================================================
# 6. next_lesson сквозь блоки и локации
# =========================================================
def test_next_lesson():
    print("\n[6] Следующий урок идёт сквозь блоки и локации")
    check("с нуля — первый урок плана",
          PM.next_lesson({}) == "1.1", PM.next_lesson({}))
    check("после 3 уроков — проверка блока (1.3 → 1.4)",
          PM.next_lesson({"completed_lessons": ["1.1", "1.2", "1.3"]}) == "1.4")
    check("после проверки — следующий блок (1.4 → 2.1)",
          PM.next_lesson({"completed_lessons": ["1.1", "1.2", "1.3", "1.4"]})
          == "2.1")
    ids = PM.location_ids()
    first_done = {"completed_lessons": all_lessons(ids[0])}
    check("конец локации → первая проверка новой локации",
          PM.next_lesson(first_done) == "forest/1.1",
          PM.next_lesson(first_done))
    everything = {"completed_lessons": PM._lesson_order}
    check("всё пройдено → None", PM.next_lesson(everything) is None)


# =========================================================
# 7. Проверочное занятие
# =========================================================
def test_check_lesson():
    print("\n[7] Проверочное занятие (тип check)")
    check("тип известен модулю уроков",
          lesson.normalize_type("check") == "check")
    check("подпись типа — «проверка»",
          lesson.type_label("check") == "проверка", lesson.type_label("check"))
    check("это голосовое занятие (цель — говорение)",
          lesson.allowed_inputs("check") == {"voice"},
          lesson.allowed_inputs("check"))
    check("микрофон нужен", lesson.needs_microphone("check") is True)
    check("текст запрещён", lesson.needs_text("check") is False)
    check("is_check_lesson", lesson.is_check_lesson("check") is True
          and lesson.is_check_lesson("speaking") is False)
    check("не путается с уроком-рассказом",
          lesson.is_story_lesson("check") is False)

    instruction = lesson.opening_task("check")
    check("Джейн не учит новому",
          "NOT teach" in instruction, instruction[:90])
    check("спрашивает по одному вопросу",
          "ONE question at a time" in instruction)

    target = int(getattr(config, "LESSON_CHECK_REPLY_TARGET", 16))
    session = lesson.LessonSession("forest/1.4", lesson_type="check",
                                   title="Проверка: Daily Routine", code="1.4")
    check("проверка длиннее обычного урока",
          session.reply_target == target
          and target > int(config.LESSON_REPLY_TARGET),
          (session.reply_target, config.LESSON_REPLY_TARGET))
    check("на экране короткий код, а не forest/1.4",
          session.label() == "Урок 1.4 · Проверка: Daily Routine",
          session.label())
    check("подсказка в поле ввода — про проверку",
          "Проверка" in lesson.locked_hint("check"), lesson.locked_hint("check"))

    plain = lesson.LessonSession("forest/1.1", lesson_type="speaking",
                                 title="My morning", code="1.1")
    check("обычный урок короче проверки",
          plain.reply_target == int(config.LESSON_REPLY_TARGET),
          plain.reply_target)


def main():
    print("=" * 60)
    print("Проверка локаций программы и проверочных занятий")
    print("=" * 60)
    test_plan()
    test_unlock()
    test_next_lesson()
    test_check_lesson()

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
