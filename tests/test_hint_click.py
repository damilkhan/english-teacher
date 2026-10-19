# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_HINT_CLICK.PY — озвучка по клику в подсказке перевода
# =========================================================
#   python tests\test_hint_click.py   (нужен экран: создаётся Tk-окно)
#
# Решение ученика: кнопки-динамика 🔊 в полосе перевода больше НЕТ — озвучка
# идёт КЛИКОМ по самому слову или по его примеру, а при наведении мыши слово
# подсвечивается (видно, что на него можно нажать).
#
# Проверяем:
#   1) кнопки 🔊 нет (и озвучить можно без неё);
#   2) клик по английскому слову читает СЛОВО, клик по примеру — ПРИМЕР
#      (раньше 🔊 читал только первое значение, остальные — никак);
#   3) наведение меняет фон/цвет и возвращает их обратно;
#   4) служебная строка («Перевожу…») НЕ нажимается;
#   5) клик по фразе и по эталону произношения озвучивает их;
#   6) высота полосы не выросла против прежней (78 px на три значения) —
#      иначе полоса съедала бы место у чата;
#   7) разбор строки «слово — пример» (split_meaning).
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

import customtkinter as ctk                       # noqa: E402
import theme                                      # noqa: E402
from ui.widgets.hint_bar import HintBar, split_meaning   # noqa: E402

FAILED = []
MEANINGS = ["key — Use the key to unlock the door.",
            "wrench — He fixed the car with a wrench.",
            "key — This is the key ingredient."]
OLD_HEIGHT = 78          # высота полосы с тремя значениями ДО переделки


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def visible(widget):
    return widget.winfo_manager() == "pack"


def pump(root, n=8):
    for _ in range(n):
        root.update()


def click(label):
    """Настоящий клик мышью приходит во ВНУТРЕННИЙ tk.Label — туда и шлём."""
    label._label.event_generate("<Button-1>")


def hover(label, enter=True):
    label._label.event_generate("<Enter>" if enter else "<Leave>")


def make(root, spoken, inserted=None):
    return HintBar(root, theme.DARK,
                   on_insert=(lambda t: inserted.append(t) or True)
                   if inserted is not None else None,
                   on_listen=spoken.append)


def items(bar):
    return [label for label, _key in bar._items]


def main():
    print("=" * 60)
    print("Проверка подсказки перевода: озвучка по клику")
    print("=" * 60)

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("1160x560")
    spoken, inserted = [], []
    bar = make(root, spoken, inserted)
    pump(root)

    print("\n[1] Кнопки-динамика больше нет")
    check("атрибута listen_btn нет", not hasattr(bar, "listen_btn"))
    check("кнопок в полосе ровно две (↺ и ✕)",
          sum(1 for w in bar.winfo_children() if isinstance(w, ctk.CTkButton)) == 2,
          [type(w).__name__ for w in bar.winfo_children()])
    check("↺ на месте", bar.insert_btn.cget("text") == "↺")
    check("✕ на месте", bar.close_btn.cget("text") == "✕")

    print("\n[2] Слово с тремя значениями: клик читает именно это")
    bar.show_meanings(MEANINGS, "ключ")
    pump(root)
    labels = items(bar)
    check("полоса показана", visible(bar), bar.winfo_manager())
    check("заголовок не нажимается", labels[0].cget("cursor") == "arrow",
          labels[0].cget("cursor"))
    spoken.clear()
    click(labels[1])                       # «   • key»
    pump(root)
    check("клик по слову читает СЛОВО", spoken == ["key"], spoken)
    spoken.clear()
    click(labels[2])                       # «— Use the key to unlock the door.»
    pump(root)
    check("клик по примеру читает ПРИМЕР",
          spoken == ["Use the key to unlock the door."], spoken)
    spoken.clear()
    click(labels[3])                       # второе значение: слово wrench
    pump(root)
    check("второе значение тоже озвучивается (раньше 🔊 не мог)",
          spoken == ["wrench"], spoken)

    print("\n[3] Подсветка при наведении")
    example = labels[2]
    before_bg, before_fg = example.cget("fg_color"), example.cget("text_color")
    hover(example, True)
    pump(root, 4)
    hover_bg, hover_fg = example.cget("fg_color"), example.cget("text_color")
    check("под курсором фон меняется", hover_bg == theme.DARK["btn_hover"], hover_bg)
    check("под курсором текст ярче", hover_fg == theme.DARK["text_strong"], hover_fg)
    check("под курсором — «рука»", example.cget("cursor") == "hand2")
    hover(example, False)
    pump(root, 4)
    check("после ухода фон прежний", example.cget("fg_color") == before_bg,
          example.cget("fg_color"))
    check("после ухода цвет прежний", example.cget("text_color") == before_fg,
          example.cget("text_color"))

    print("\n[4] Служебная строка не нажимается")
    bar.show_status("💡 Перевожу…")
    pump(root)
    status = items(bar)[0]
    spoken.clear()
    click(status)
    pump(root)
    check("курсор обычный", status.cget("cursor") == "arrow",
          status.cget("cursor"))
    check("клик ничего не озвучивает", spoken == [], spoken)

    print("\n[5] Фраза и эталон произношения")
    bar.show_translation("I want to go home.", "я хочу пойти домой")
    pump(root)
    spoken.clear()
    click(items(bar)[0])
    pump(root)
    check("клик по фразе читает фразу", spoken == ["I want to go home."], spoken)
    check("исходный русский текст виден", "я хочу пойти домой" in bar.text, bar.text)
    bar.show_note("🟡 Почти\n   нажми на фразу, чтобы послушать",
                  "Open the door with this key.")
    pump(root)
    spoken.clear()
    click(items(bar)[0])
    pump(root)
    check("клик по вердикту читает эталон",
          spoken == ["Open the door with this key."], spoken)

    print("\n[6] Полоса не выросла (место у чата не отнимаем)")
    bar.show_meanings(MEANINGS, "ключ")
    pump(root)
    height = bar.winfo_height()
    check("три значения = прежние %d px (не больше)" % OLD_HEIGHT,
          height <= OLD_HEIGHT, height)
    check("текст не обрезан (строка не ниже нужного)",
          all(l._label.winfo_height() >= l._label.winfo_reqheight()
              for l in items(bar)))

    print("\n[7] split_meaning")
    check("длинное тире", split_meaning("key — Open the door.") ==
          ("key", "Open the door."), split_meaning("key — Open the door."))
    check("короткое тире", split_meaning("key - Open the door.") ==
          ("key", "Open the door."), split_meaning("key - Open the door."))
    check("без тире — вся строка", split_meaning("just text") == ("just text", ""),
          split_meaning("just text"))
    check("пустая строка", split_meaning("") == ("", ""), split_meaning(""))
    check("тире внутри примера не рвёт строку",
          split_meaning("key — A door — and a window.")[0] == "key",
          split_meaning("key — A door — and a window."))

    print("\n[8] Без обработчика озвучки клик безвреден")
    silent = make(root, spoken)
    silent._on_listen = None
    silent.show_meanings(MEANINGS, "ключ")
    pump(root)
    hover(items(silent)[1], True)
    pump(root, 4)
    check("без on_listen подсветки нет",
          items(silent)[1].cget("fg_color") == "transparent",
          items(silent)[1].cget("fg_color"))
    click(items(silent)[1])
    pump(root)
    check("клик не падает", True)

    print("\n[9] ↺ по-прежнему вставляет перевод")
    bar.show_meanings(MEANINGS, "ключ")
    pump(root)
    inserted.clear()
    bar._insert()
    pump(root)
    check("перевод ушёл в поле ввода", inserted == [MEANINGS[0]], inserted)
    check("подсказка закрылась после вставки", not visible(bar))

    root.destroy()

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
