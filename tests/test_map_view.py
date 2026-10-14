# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_MAP_VIEW.PY — логика карты без живого Tk
# =========================================================
#   python tests\test_map_view.py   (окно НЕ создаётся)
#
# Проверяем «чистую» часть ui/widgets/map_view.py:
#   1) масштабирование картинки (display_size / fit_scale);
#   2) перевод координат точки (scale_point / scaled_radius);
#   3) попадание курсора по жетону (hit_test);
#   4) тексты подсказки и русское склонение;
#   5) цвета состояния (state_colors) — берутся из палитры темы;
#   6) зажим подсказки внутри области (clamp_box);
#   7) отрисовка жетона Pillow-ом (render_token) — без Tk.
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

import theme                                                    # noqa: E402
import ui.widgets.map_view as mv                                # noqa: E402
from progress_map import UNLOCKED, LOCKED, COMPLETED            # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def rgb(img, x, y):
    return img.convert("RGB").getpixel((int(x), int(y)))


def dist(a, b):
    return sum((int(p) - int(q)) ** 2 for p, q in zip(a, b)) ** 0.5


def main():
    print("=" * 60)
    print("Проверка карты прогресса (чистая логика MapView)")
    print("=" * 60)

    # ---------- 1. Масштаб ----------
    print("\n[1] Вписывание картинки в рамку")
    check("широкая рамка: пропорции сохранены",
          mv.display_size((1248, 832), (1248, 400)) == (600, 400),
          mv.display_size((1248, 832), (1248, 400)))
    check("квадратная рамка: вписывается по ширине",
          mv.display_size((1248, 832), (700, 700)) == (700, 467),
          mv.display_size((1248, 832), (700, 700)))
    check("масштаб = 0.5 при половине ширины",
          abs(mv.fit_scale((1000, 500), (500, 500)) - 0.5) < 1e-9,
          mv.fit_scale((1000, 500), (500, 500)))
    check("нулевой размер рамки не роняет", mv.display_size((1248, 832), (0, 0))[0] >= 1)

    # ---------- 2. Координаты ----------
    print("\n[2] Перевод координат точки")
    check("без отступа", mv.scale_point((311, 159), 0.5) == (156, 80),
          mv.scale_point((311, 159), 0.5))
    check("с отступом", mv.scale_point((100, 100), 1.0, (20, 30)) == (120, 130),
          mv.scale_point((100, 100), 1.0, (20, 30)))
    check("радиус: масштаб умножается",
          mv.scaled_radius(26, 0.5) == 13, mv.scaled_radius(26, 0.5))
    check("радиус не меньше минимума",
          mv.scaled_radius(26, 0.05) == mv.TOKEN_MIN_RADIUS,
          mv.scaled_radius(26, 0.05))

    # ---------- 3. Попадание ----------
    print("\n[3] Попадание курсора по жетону")
    tokens = [{"id": "p1", "x": 100, "y": 100}, {"id": "p2", "x": 200, "y": 100}]
    check("в центр жетона", mv.hit_test(102, 98, tokens, 14) == "p1")
    check("по второму жетону", mv.hit_test(205, 100, tokens, 14) == "p2")
    check("мимо жетонов → None", mv.hit_test(150, 300, tokens, 14) is None)
    check("на границе радиуса — попадание",
          mv.hit_test(100 + 14, 100, tokens, 14) == "p1")
    check("чуть за радиусом — мимо",
          mv.hit_test(100 + 20, 100, tokens, 14) is None)
    check("пустой список → None", mv.hit_test(0, 0, [], 14) is None)

    # ---------- 4. Тексты ----------
    print("\n[4] Подсказка и склонение")
    check("склонение 1/2/5", (mv.plural_ru(1), mv.plural_ru(2), mv.plural_ru(5))
          == ("урок", "урока", "уроков"))
    check("склонение 11/21", (mv.plural_ru(11), mv.plural_ru(21)) == ("уроков", "урок"),
          (mv.plural_ru(11), mv.plural_ru(21)))
    check("склонение 13/14", (mv.plural_ru(13), mv.plural_ru(14)) == ("уроков", "уроков"))
    check("текст подсказки",
          mv.tooltip_text(1, "Greetings", 3) == "Блок 1: Greetings — 3 урока",
          mv.tooltip_text(1, "Greetings", 3))
    check("заголовок без названия",
          mv.tooltip_text(5, "", 3) == "Блок 5 — 3 урока", mv.tooltip_text(5, "", 3))
    check("склонение в подсказке для 1 урока",
          mv.tooltip_text(3, "Colors", 1) == "Блок 3: Colors — 1 урок",
          mv.tooltip_text(3, "Colors", 1))

    # ---------- 5. Цвета состояния ----------
    print("\n[5] Цвета состояния из палитры темы")
    for name, palette in (("DARK", theme.DARK), ("LIGHT", theme.LIGHT)):
        done_fill, done_out = mv.state_colors(COMPLETED, palette)
        act_fill, act_out = mv.state_colors(UNLOCKED, palette)
        lock_fill, lock_out = mv.state_colors(LOCKED, palette)
        check("%s: пройдено = map_done" % name, done_fill == palette["map_done"], done_fill)
        check("%s: активный = map_unlocked" % name, act_fill == palette["map_unlocked"], act_fill)
        check("%s: закрыто = map_locked" % name, lock_fill == palette["map_locked"], lock_fill)
        check("%s: три состояния разного цвета" % name,
              len({done_fill, act_fill, lock_fill}) == 3)
        check("%s: контуры заданы" % name, bool(done_out) and bool(act_out) and bool(lock_out))
    check("неизвестное состояние → закрыто",
          mv.state_colors("чушь", theme.DARK)[0] == theme.DARK["map_locked"])

    # ---------- 6. Зажим подсказки ----------
    print("\n[6] Зажим подсказки внутри области")
    check("внутри — без изменений", mv.clamp_box(100, 100, 80, 30, 500, 400) == (100, 100))
    check("за правым краем — прижата", mv.clamp_box(480, 100, 80, 30, 500, 400)[0] == 414,
          mv.clamp_box(480, 100, 80, 30, 500, 400))
    check("сверху — прижата к отступу", mv.clamp_box(-50, -50, 80, 30, 500, 400)[1] == 6,
          mv.clamp_box(-50, -50, 80, 30, 500, 400))

    # ---------- 7. Жетон (Pillow, без Tk) ----------
    print("\n[7] Отрисовка жетона (Pillow)")
    r = 20
    img_done = mv.render_token(1, COMPLETED, r, theme.DARK)
    img_act = mv.render_token(2, UNLOCKED, r, theme.DARK)
    img_lock = mv.render_token(3, LOCKED, r, theme.DARK)
    check("размер картинки согласован",
          img_done.width == img_done.height and abs(img_done.width - (r + (int(r * 0.55) + 6)) * 2) <= 2,
          (img_done.width, img_done.height))
    cx = img_lock.width // 2
    cy = img_lock.height // 2
    # берём пиксель ниже центра (там заливка, а не блик)
    y_low = int(cy + r * 0.6)
    d_done = rgb(img_done, cx, y_low)
    d_act = rgb(img_act, cx, y_low)
    d_lock = rgb(img_lock, cx, y_low)
    want_done = mv._hex_rgb(theme.DARK["map_done"])
    want_act = mv._hex_rgb(theme.DARK["map_unlocked"])
    want_lock = mv._hex_rgb(theme.DARK["map_locked"])
    check("пройдено — заливка map_done", dist(d_done, want_done) < 60,
          "%s vs %s" % (d_done, want_done))
    check("активный — заливка map_unlocked", dist(d_act, want_act) < 60,
          "%s vs %s" % (d_act, want_act))
    check("закрыто — заливка map_locked", dist(d_lock, want_lock) < 60,
          "%s vs %s" % (d_lock, want_lock))
    check("три состояния визуально различны",
          dist(d_done, want_act) > 60 and dist(d_lock, want_act) > 60)
    # цифра: где-то в жетоне должны быть белые пиксели
    whites = sum(1 for x in range(img_lock.width) for y in range(img_lock.height)
                 if rgb(img_lock, x, y) == (255, 255, 255))
    check("цифра/ободок дают белые пиксели", whites > 50, whites)
    check("жетон без номера рисуется", mv.render_token(None, LOCKED, 12, theme.DARK).width > 0)
    check("свечение активного не ломает отрисовку",
          mv.render_token(2, UNLOCKED, 18, theme.DARK, glow=True).width > 0)

    # ---------- 8. Интеграция с ProgressMap ----------
    print("\n[8] Состояние точки из профиля (ProgressMap)")
    from progress_map import ProgressMap
    pm = ProgressMap(os.path.join(ROOT, "knowledge_base"))
    pts = pm.points_of("desert")
    first = str(pts[0].get("id"))
    check("без профиля первая точка активна",
          mv.point_state_from(None, pm, first) == UNLOCKED)
    check("без профиля вторая точка закрыта",
          mv.point_state_from(None, pm, str(pts[1].get("id"))) == LOCKED)
    lessons = [l["id"] for l in pm.lessons_of(first)]
    check("после прохождения блока он completed",
          mv.point_state_from({"completed_lessons": lessons}, pm, first) == COMPLETED)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
