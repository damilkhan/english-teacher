# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_MAP_NUMBERS.PY — номера точек на карте
# =========================================================
#   python tests\test_map_numbers.py   (нужно окно Windows)
#
# Регрессия: картинка жетона кэшировалась по (состояние, радиус) БЕЗ номера
# точки, поэтому все жетоны одного состояния получали картинку ПЕРВОГО
# нарисованного — на карте все точки были под «2» (грабли №36).
#
# Проверяем:
#   1) в учебном плане номера точек — 1..9 без повторов;
#   2) render_token(1..9) даёт 9 РАЗНЫХ картинок;
#   3) на живой карте у каждой точки своя картинка и свой ключ кэша;
#   4) номер в подсказке жетона совпадает с номером точки.
# =========================================================

import hashlib
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import theme                                                  # noqa: E402
from progress_map import ProgressMap                          # noqa: E402
from ui.widgets.map_view import MapView, render_token, tooltip_text  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def test_plan():
    print("\n[1] Номера точек в учебном плане")
    pm = ProgressMap()
    points = pm.points_of("desert")
    numbers = [p.get("number") for p in points]
    check("точек 9", len(points) == 9, len(points))
    check("номера 1..9 по порядку", numbers == [1, 2, 3, 4, 5, 6, 7, 8, 9], numbers)
    check("id точек не совпадают с номерами",
          [p.get("id") for p in points] != numbers, [p.get("id") for p in points])


def test_render():
    print("\n[2] Картинки жетонов различаются по номеру")
    hashes = {}
    for n in range(1, 10):
        img = render_token(n, "locked", 26, theme.DARK)
        hashes[n] = hashlib.md5(img.tobytes()).hexdigest()
    check("9 разных картинок для номеров 1..9", len(set(hashes.values())) == 9,
          len(set(hashes.values())))
    same_state = render_token(2, "unlocked", 26, theme.DARK)
    other = render_token(7, "unlocked", 26, theme.DARK)
    check("и для активного состояния тоже разные",
          hashlib.md5(same_state.tobytes()).hexdigest()
          != hashlib.md5(other.tobytes()).hexdigest())


def test_live_map():
    print("\n[3] Живая карта: у каждой точки своя картинка")
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("900x640+40+40")
    theme.resolve_fonts(root)
    view = None
    try:
        for _ in range(20):
            root.update()
            time.sleep(0.02)
        view = MapView(root, theme.DARK, on_point_click=lambda pid: None)
        view.pack(fill="both", expand=True)
        view.set_active(True)
        for _ in range(60):
            root.update()
            time.sleep(0.02)

        check("жетонов столько же, сколько точек",
              len(view._tokens) == 9, len(view._tokens))
        photos = {}
        for token in view._tokens:
            photo = view._token_photos.get(token["id"])
            photos.setdefault(str(photo), []).append(token.get("number"))
        check("9 уникальных картинок на карте", len(photos) == 9,
              {k[-6:]: v for k, v in photos.items()})
        duplicates = [v for v in photos.values() if len(v) > 1]
        check("ни одна картинка не повторяется у разных точек", not duplicates,
              duplicates)
        check("в ключе кэша есть номер точки",
              all(len(key) == 3 for key in view._token_cache), list(view._token_cache)[:5])

        numbers = sorted(int(t.get("number")) for t in view._tokens)
        check("на карте все номера 1..9", numbers == list(range(1, 10)), numbers)

        print("\n[4] Подсказка жетона")
        first = view._tokens[0]
        text = tooltip_text(first.get("number"), first.get("title"), first.get("lessons"))
        check("номер точки в подсказке", "Блок 1" in text, text)
        last = view._tokens[-1]
        text2 = tooltip_text(last.get("number"), last.get("title"), last.get("lessons"))
        check("и у девятой точки свой номер", "Блок 9" in text2, text2)
    finally:
        try:
            if view is not None:
                view.destroy()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass


def main():
    print("=" * 60)
    print("Проверка номеров точек на карте")
    print("=" * 60)
    test_plan()
    test_render()
    test_live_map()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
