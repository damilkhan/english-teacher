# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_INFO_BAR.PY — тонкая строка «учительского» вида
# =========================================================
#   python tests\test_info_bar.py   (нужен экран: создаётся Tk-окно)
#
# Проверяем виджет InfoBar (ui/widgets/info_bar.py):
#   1) пока данных нет — полоса СКРЫТА (в раскладке ничего не занимает);
#   2) разбор Аналитика показывает полосу и текст с иконкой;
#   3) план добавляется к разбору в одной строке;
#   4) clear() прячет полосу и очищает текст;
#   5) apply_theme меняет цвета и не падает.
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

import customtkinter as ctk          # noqa: E402
import theme                         # noqa: E402
from ui.widgets.info_bar import InfoBar  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def visible(widget):
    """Полоса реально упакована в раскладку (pack), а не спрятана."""
    return widget.winfo_manager() == "pack"


def main():
    print("=" * 60)
    print("Проверка строки «учительского» вида (InfoBar)")
    print("=" * 60)

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("820x340")
    bar = InfoBar(root, theme.DARK)
    root.update()

    print("\n[1] Старт: пустая полоса скрыта")
    check("полоса НЕ упакована", not visible(bar), bar.winfo_manager())
    check("текст пуст", bar.text == "", repr(bar.text))

    print("\n[2] Разбор Аналитика")
    bar.set_analysis("ответ · ⚠ доработать · ошибок 1 · travel")
    root.update()
    check("полоса показана", visible(bar), bar.winfo_manager())
    check("текст разбора на месте", "доработать" in bar.text, bar.text)
    check("иконка разбора есть (🔎)", "🔎" in bar.text, bar.text)

    print("\n[3] План в той же строке")
    bar.set_plan("Present Perfect")
    root.update()
    check("и разбор, и план в одной строке",
          "🔎" in bar.text and "📋" in bar.text and "Present Perfect" in bar.text,
          bar.text)

    print("\n[4] clear() прячет полосу")
    bar.clear()
    root.update()
    check("после clear полоса спрятана", not visible(bar), bar.winfo_manager())
    check("текст пуст", bar.text == "", repr(bar.text))

    print("\n[5] Тема")
    bar.set_plan("Travel")
    root.update()
    bar.apply_theme(theme.LIGHT)
    root.update()
    check("apply_theme меняет цвет текста",
          bar.label.cget("text_color") == theme.LIGHT["muted"],
          bar.label.cget("text_color"))
    check("после смены темы полоса всё ещё видна", visible(bar))

    root.destroy()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()