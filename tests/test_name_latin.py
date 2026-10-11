# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_NAME_LATIN.PY — имя ученика латиницей
# =========================================================
#   python tests\test_name_latin.py
#
# Имя храним ЛАТИНИЦЕЙ (Damil, а не Дамиль): так оно единообразно выглядит и
# озвучивается. Проверяем транслитерацию и живое преобразование в форме.
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

import user_manager          # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def test_to_latin():
    print("\n[1] user_manager.to_latin")
    check("Дамиль → Damil", user_manager.to_latin("Дамиль") == "Damil",
          user_manager.to_latin("Дамиль"))
    check("Аня → Anya", user_manager.to_latin("Аня") == "Anya", user_manager.to_latin("Аня"))
    check("латиница не меняется", user_manager.to_latin("Damil") == "Damil")
    check("цифры и пробелы не трогаются", user_manager.to_latin("Damil 42") == "Damil 42")
    check("регистр сохраняется", user_manager.to_latin("АБВ") == "ABV",
          user_manager.to_latin("АБВ"))
    check("пусто → пусто", user_manager.to_latin("") == "" and user_manager.to_latin(None) == "")
    check("ё/ж/щ/ю/я", user_manager.to_latin("ёж щюя") == "ezh shchyuya",
          user_manager.to_latin("ёж щюя"))


def test_form():
    print("\n[2] Форма профиля: живая транслитерация имени")
    import customtkinter as ctk
    import theme
    from ui.first_run import FirstRunForm

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("300x200")
    root.withdraw()
    form = None
    try:
        form = FirstRunForm(root, theme.DARK)
        form.name_var.set("Дамиль")
        check("кириллица сохранена в имени", form.name_var.get() == "Дамиль",
              form.name_var.get())
        check("латиница заполнилась автоматически",
              form.name_latin_var.get() == "Damil", form.name_latin_var.get())
        form.name_latin_var.set("Damil777")
        form.name_var.set("Дамиль Второй")
        check("правленую латиницу не перезаписываем",
              form.name_latin_var.get() == "Damil777", form.name_latin_var.get())
    finally:
        if form is not None:
            try:
                form.destroy()
            except Exception:
                pass
        root.destroy()


def main():
    print("=" * 60)
    print("Проверка: имя ученика латиницей")
    print("=" * 60)
    test_to_latin()
    test_form()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
