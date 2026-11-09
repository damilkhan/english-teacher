# -*- coding: utf-8 -*-
# =========================================================
# TEST_BLOCK_LOCATION.PY — локация берётся по САМОЙ точке
# =========================================================
# Живой баг 09.11.2026: на карте города («Городские улицы») окно блока
# подписывалось «Пустыня», а урок, начатый кнопкой «Провести урок», шёл без
# названия блока. Причина — жёсткое "desert" в ui/app.py.
#
# Что проверяем:
#   1) ProgressMap.location_of(точка) отдаёт настоящую локацию;
#   2) ProgressMap.point_of_lesson(урок) отдаёт блок по ВСЕЙ карте;
#   3) неизвестные id → пустая строка (не падаем);
#   4) profile_summary подписывает карту переданной локацией, а не «Пустыней».
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from progress_map import ProgressMap          # noqa: E402

FAILED = []


def check(name, ok, extra=None):
    if ok:
        print("  ✅ %s" % name)
    else:
        FAILED.append(name)
        print("  ❌ %s  →  %r" % (name, extra))


def main():
    print("=" * 60)
    print("Локация точки и блок урока — по всей карте")
    print("=" * 60)
    pm = ProgressMap()

    print("\n[1] location_of: точка → её локация")
    check("city/point_2 — это city", pm.location_of("city/point_2") == "city",
          pm.location_of("city/point_2"))
    check("point_1 (первая локация) — это desert", pm.location_of("point_1") == "desert",
          pm.location_of("point_1"))
    city = pm.get_location("city")
    check("у города есть название", bool(city.get("title")), city.get("title"))
    check("название — не «Пустыня»", city.get("title") != "Пустыня", city.get("title"))

    print("\n[2] point_of_lesson: урок → его блок (любая локация)")
    check("city/2.3 → city/point_2", pm.point_of_lesson("city/2.3") == "city/point_2",
          pm.point_of_lesson("city/2.3"))
    check("2.1 (Пустыня) → point_2", pm.point_of_lesson("2.1") == "point_2",
          pm.point_of_lesson("2.1"))

    print("\n[3] Неизвестные id не роняют")
    check("неизвестная точка → ''", pm.location_of("nope/point_9") == "")
    check("неизвестный урок → ''", pm.point_of_lesson("99.9") == "")
    check("пустой id → ''", pm.location_of("") == "" and pm.point_of_lesson("") == "")

    print("\n[4] profile_summary подписывает настоящую локацию")
    from ui import app as app_mod
    rows = app_mod.profile_summary({"name": "Дамиль"}, {}, (3, 9), "Городские улицы")
    text = " | ".join("%s: %s" % (h, v) for h, v in rows)
    check("в профиле «Городские улицы»", "Карта «Городские улицы»" in text, text)
    check("в профиле нет «Пустыни»", "Пустыня" not in text, text)
    rows2 = app_mod.profile_summary({"name": "Дамиль"}, {}, (3, 9), "")
    text2 = " | ".join("%s: %s" % (h, v) for h, v in rows2)
    check("без названия — «Пустыня» (старое поведение)",
          "Карта «Пустыня»" in text2, text2)

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("  ❌ %s" % name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
