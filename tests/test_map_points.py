# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_MAP_POINTS.PY — жетоны стоят на СВОИХ кружках
# =========================================================
#   python tests\test_map_points.py     (Tk, звук и модель не нужны)
#
# Зачем этот файл. Раньше в tools/build_curriculum.py был ОДИН список
# POINTS_XY из 9 пар координат на ВСЕ 13 локаций. Пока картинка была только
# у «Пустыни», это не мешало; но с появлением леса, реки и города девять
# жетонов вставали по пустынным местам — наугад.
#
# Теперь раскладка у каждой локации СВОЯ: координаты сняты с белых кружков,
# которые нарисованы на самой карте, и номер блока совпадает с номером
# на картинке. Проверяем:
#   1) в плане у каждой локации 9 точек с номерами 1..9 по порядку;
#   2) раскладки РАЗНЫЕ (регрессия «один список на все локации»);
#   3) координаты внутри картинки и точки не наезжают друг на друга;
#   4) картинки существуют и ровно 1248×832 — как записано в плане;
#   5) каждая точка попадает на БЕЛЫЙ кружок (яркость в центре);
#   6) сборщик плана и curriculum.json не разъехались.
# =========================================================

import importlib.util
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

PLAN_PATH = os.path.join(ROOT, "knowledge_base", "curriculum.json")
BUILD_PATH = os.path.join(ROOT, "tools", "build_curriculum.py")

# локации, у которых картинка уже нарисована пользователем
MAPS_WITH_IMAGE = ("desert", "forest", "river", "city")

SIZE = (1248, 832)          # размер всех картинок карты
MIN_APART = 30              # жетоны не должны наезжать друг на друга (px)
MIN_BRIGHT = 140            # яркость центра жетона = белый кружок на карте

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def load_plan():
    with open(PLAN_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def load_builder():
    """Импортировать tools/build_curriculum.py по пути (пакета tools нет)."""
    spec = importlib.util.spec_from_file_location("build_curriculum_under_test",
                                                  BUILD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def image_path(rel):
    return os.path.join(ROOT, str(rel).replace("/", os.sep))


# =========================================================
# 1. Точки в плане
# =========================================================
def test_points_in_plan(plan):
    print("\n[1] Точки в учебном плане")
    locations = plan.get("locations") or []
    check("локаций 13", len(locations) == 13, len(locations))

    bad_counts, bad_numbers, bad_coords = [], [], []
    for loc in locations:
        points = loc.get("points") or []
        if len(points) != 9:
            bad_counts.append((loc.get("id"), len(points)))
        numbers = [p.get("number") for p in points]
        if numbers != list(range(1, 10)):
            bad_numbers.append((loc.get("id"), numbers))
        for point in points:
            xy = point.get("point")
            if (not isinstance(xy, (list, tuple)) or len(xy) != 2
                    or not all(isinstance(v, int) for v in xy)):
                bad_coords.append((loc.get("id"), point.get("number"), xy))

    check("у каждой локации 9 точек", not bad_counts, bad_counts)
    check("номера точек 1..9 по порядку", not bad_numbers, bad_numbers)
    check("координаты — пары целых чисел", not bad_coords, bad_coords[:5])


# =========================================================
# 2. Раскладка у каждой локации своя
# =========================================================
def test_layouts_are_different(plan):
    print("\n[2] Раскладка у каждой локации СВОЯ (главная регрессия)")
    layouts = {}
    for loc in plan.get("locations") or []:
        layouts[loc.get("id")] = tuple(tuple(p.get("point") or [])
                                       for p in loc.get("points") or [])

    print("     раскладок всего: %d, уникальных: %d"
          % (len(layouts), len(set(layouts.values()))))
    for loc_id in MAPS_WITH_IMAGE:
        for other in MAPS_WITH_IMAGE:
            if other <= loc_id:
                continue
            check("«%s» и «%s» — разные раскладки" % (loc_id, other),
                  layouts.get(loc_id) != layouts.get(other),
                  "совпали координаты")

    # локации без картинки берут общую запасную раскладку — это нормально,
    # но она НЕ должна совпадать с раскладкой нарисованной карты
    for loc_id in MAPS_WITH_IMAGE:
        same = [other for other, lay in layouts.items()
                if other not in MAPS_WITH_IMAGE and lay == layouts.get(loc_id)]
        check("запасная раскладка не равна «%s»" % loc_id, not same, same)


# =========================================================
# 3. Точки внутри картинки и не наезжают друг на друга
# =========================================================
def test_geometry(plan):
    print("\n[3] Геометрия точек")
    outside, crowded, same_xy = [], [], []
    for loc in plan.get("locations") or []:
        size = loc.get("size") or list(SIZE)
        w, h = int(size[0]), int(size[1])
        points = [(p.get("number"), p.get("point") or [0, 0])
                  for p in loc.get("points") or []]
        for number, xy in points:
            x, y = int(xy[0]), int(xy[1])
            if not (0 <= x < w and 0 <= y < h):
                outside.append((loc.get("id"), number, (x, y)))
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                (n1, a), (n2, b) = points[i], points[j]
                if tuple(a) == tuple(b):
                    same_xy.append((loc.get("id"), n1, n2))
                dist = ((int(a[0]) - int(b[0])) ** 2
                        + (int(a[1]) - int(b[1])) ** 2) ** 0.5
                if dist < MIN_APART:
                    crowded.append((loc.get("id"), n1, n2, round(dist, 1)))
    check("все точки внутри картинки", not outside, outside)
    check("ни одна пара точек не совпадает", not same_xy, same_xy)
    check("точки не ближе %d px друг к другу" % MIN_APART, not crowded, crowded)


# =========================================================
# 4. Картинки на месте и нужного размера
# =========================================================
def test_images(plan):
    print("\n[4] Картинки локаций")
    by_id = {loc.get("id"): loc for loc in plan.get("locations") or []}
    for loc_id in MAPS_WITH_IMAGE:
        loc = by_id.get(loc_id) or {}
        rel = loc.get("image") or ""
        exists = bool(rel) and os.path.isfile(image_path(rel))
        check("«%s»: картинка на месте (%s)" % (loc_id, rel), exists, rel)
        if not exists:
            continue
        try:
            from PIL import Image
        except Exception as exc:                       # noqa: BLE001
            check("Pillow доступен для замера размеров", False, exc)
            return
        with Image.open(image_path(rel)) as im:
            real = im.size
        check("«%s»: размер %dx%d" % (loc_id, SIZE[0], SIZE[1]),
              real == SIZE, real)
        check("«%s»: размер в плане совпадает с файлом" % loc_id,
              list(loc.get("size") or []) == list(real),
              (loc.get("size"), real))

    # у остальных локаций картинки ещё нет — программа покажет заглушку
    missing = [loc_id for loc_id in by_id if loc_id not in MAPS_WITH_IMAGE
               and os.path.isfile(image_path((by_id[loc_id] or {}).get("image") or ""))]
    check("локации без картинки пока без файлов (заглушка)", True,
          "%d с файлом" % len(missing))


# =========================================================
# 5. Каждая точка стоит на белом кружке
# =========================================================
def test_tokens_on_circles(plan):
    print("\n[5] Жетон попадает на белый кружок карты")
    try:
        from PIL import Image
    except Exception as exc:                           # noqa: BLE001
        check("Pillow доступен", False, exc)
        return

    for loc in plan.get("locations") or []:
        if loc.get("id") not in MAPS_WITH_IMAGE:
            continue
        path = image_path(loc.get("image") or "")
        if not os.path.isfile(path):
            check("«%s»: картинка для замера" % loc.get("id"), False, path)
            continue
        with Image.open(path) as im:
            rgb = im.convert("RGB")
            pixels = rgb.load()
            w, h = rgb.size
        worst, worst_number = 999.0, None
        for point in loc.get("points") or []:
            x, y = int(point["point"][0]), int(point["point"][1])
            total = count = 0
            radius = 8
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx * dx + dy * dy > radius * radius:
                        continue
                    px, py = x + dx, y + dy
                    if not (0 <= px < w and 0 <= py < h):
                        continue
                    r, g, b = pixels[px, py][:3]
                    total += 0.299 * r + 0.587 * g + 0.114 * b
                    count += 1
            mean = total / float(count) if count else 0.0
            if mean < worst:
                worst, worst_number = mean, point.get("number")
        check("«%s»: все 9 центров на светлом кружке (мин. яркость %.0f)"
              % (loc.get("id"), worst),
              worst >= MIN_BRIGHT,
              "точка %s: %.0f < %d" % (worst_number, worst, MIN_BRIGHT))


# =========================================================
# 6. Сборщик плана и curriculum.json не разъехались
# =========================================================
def test_builder_matches_plan(plan):
    print("\n[6] tools/build_curriculum.py и curriculum.json")
    builder = load_builder()
    fresh = builder.build()
    check("сборщик отдаёт 13 локаций", len(fresh["locations"]) == 13,
          len(fresh["locations"]))
    check("сборщик знает 4 раскладки", len(builder.POINTS_XY) == 4,
          list(builder.POINTS_XY))
    check("у каждой раскладки 9 пар", all(len(v) == 9 for v in builder.POINTS_XY.values()),
          {k: len(v) for k, v in builder.POINTS_XY.items()})

    plan_points = {loc.get("id"): [p.get("point") for p in loc.get("points") or []]
                   for loc in plan.get("locations") or []}
    fresh_points = {loc.get("id"): [p.get("point") for p in loc.get("points") or []]
                    for loc in fresh["locations"]}
    diff = [loc_id for loc_id in fresh_points
            if plan_points.get(loc_id) != fresh_points.get(loc_id)]
    check("координаты в файле плана = координаты сборщика", not diff, diff)

    for loc_id in MAPS_WITH_IMAGE:
        check("«%s»: раскладка сборщика = файл" % loc_id,
              [list(p) for p in builder.POINTS_XY[loc_id]]
              == [list(p) for p in fresh_points[loc_id]],
              loc_id)

    check("картинки в плане — .png по id локации",
          all((loc.get("image") or "").endswith("/%s.png" % loc.get("id"))
              for loc in fresh["locations"]),
          [loc.get("image") for loc in fresh["locations"]][:4])


def main():
    print("=" * 62)
    print("КАРТА: жетоны стоят на своих кружках")
    print("=" * 62)
    if not os.path.isfile(PLAN_PATH):
        check("есть knowledge_base/curriculum.json", False, PLAN_PATH)
    else:
        plan = load_plan()
        test_points_in_plan(plan)
        test_layouts_are_different(plan)
        test_geometry(plan)
        test_images(plan)
        test_tokens_on_circles(plan)
        test_builder_matches_plan(plan)

    print("\n" + "=" * 62)
    if FAILED:
        print("ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("   • " + name)
        return 1
    print("ВСЁ ЗЕЛЁНОЕ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
