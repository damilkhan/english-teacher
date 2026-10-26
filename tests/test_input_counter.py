# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_INPUT_COUNTER.PY — счётчик «0 из N» внутри поля ввода
# =========================================================
#   python tests\test_input_counter.py
#
# Живой (скрытый) виджет InputBar:
#   1) пока задания нет, счётчика не видно;
#   2) set_counter(N) показывает «0 of N» серым;
#   3) буквы считаются по тексту поля и обновляются при вводе;
#   4) достигнут порог — цвет зелёный (palette["ok"]);
#   5) clear_counter убирает счётчик;
#   6) мусор вместо числа не ломает поле.
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

import customtkinter as ctk                        # noqa: E402
import theme                                       # noqa: E402
from ui.widgets.input_bar import InputBar          # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("=" * 60)
    print("СЧЁТЧИК БУКВ В ПОЛЕ ВВОДА")
    print("=" * 60)

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("700x200")
    root.withdraw()
    bar = InputBar(root, theme.DARK, on_send=lambda: None)
    bar.pack(fill="x")
    root.update()

    print("\n[1] Пока задания нет")
    check("счётчик пуст", bar.counter_text() == "", bar.counter_text())
    check("счётчик не размещён", not bar.counter_lbl.place_info())

    print("\n[2] Порог включён")
    bar.set_counter(105)
    root.update()
    check("текст «0 of 105»", bar.counter_text() == "0 of 105", bar.counter_text())
    check("счётчик виден", bool(bar.counter_lbl.place_info()))
    check("цвет серый", str(bar.counter_lbl.cget("fg")) == theme.DARK["muted"],
          bar.counter_lbl.cget("fg"))

    print("\n[3] Буквы считаются по тексту")
    bar.set_text("A street with people.")
    bar.set_counter(105)
    root.update()
    check("«17 of 105»", bar.counter_text() == "17 of 105", bar.counter_text())
    check("цвет всё ещё серый",
          str(bar.counter_lbl.cget("fg")) == theme.DARK["muted"],
          bar.counter_lbl.cget("fg"))

    print("\n[4] Порог набран")
    bar.set_text("There are many shops on the street and people are walking there.")
    bar.set_counter(40)
    root.update()
    check("текст обновился", bar.counter_text().endswith("of 40"), bar.counter_text())
    check("цвет зелёный", str(bar.counter_lbl.cget("fg")) == theme.DARK["ok"],
          bar.counter_lbl.cget("fg"))
    count = int(bar.counter_text().split()[0])
    check("счётчик ≥ порога", count >= 40, count)

    print("\n[5] Выключение")
    bar.clear_counter()
    root.update()
    check("текст пуст", bar.counter_text() == "", bar.counter_text())
    check("счётчик скрыт", not bar.counter_lbl.place_info())

    print("\n[6] Мусор вместо числа")
    bar.set_counter("abc")
    root.update()
    check("мусор → счётчик выключен", bar.counter_text() == "", bar.counter_text())
    bar.set_counter(-5)
    root.update()
    check("минус → счётчик выключен", bar.counter_text() == "", bar.counter_text())
    bar.set_counter(None)
    root.update()
    check("None → счётчик выключен", bar.counter_text() == "", bar.counter_text())

    try:
        root.destroy()
    except Exception:
        pass

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
