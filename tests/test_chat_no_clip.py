# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_CHAT_NO_CLIP.PY — текст реплики не обрезается снизу
# =========================================================
#   python tests\test_chat_no_clip.py   (нужен экран — создаётся Tk-окно)
#
# Баг ученика (23.10.2026, снимок): в приветствии вторая строка обрезана
# снизу. Причина: у строки с ЭМОДЗИ высота больше обычной (картинка-эмодзи
# поднимает строку: dlineinfo 21 px вместо 19), а `height` у tk.Text задаётся
# в СТРОКАХ и этого не учитывает. Замер до правки: тексту нужно 63 px,
# окно 61 px → нижние 2 px последней строки срезаны.
#
# Проверяем:
#   1) текст помещается в окно ЦЕЛИКОМ (count(ypixels) <= высота) — для
#      реплик с эмодзи в начале, в середине и в каждой строке;
#   2) приветствие из двух строк с эмодзи (случай со снимка) не обрезано;
#   3) то же при трёх ширинах чата (перекладка не возвращает обрезку);
#   4) после обновления текста (update_message) обрезки тоже нет;
#   5) длинная реплика на много строк помещается целиком.
# =========================================================

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                                                    # noqa: E402
import customtkinter as ctk                                      # noqa: E402
import theme                                                     # noqa: E402
from ui import fonts as ui_fonts                                 # noqa: E402
from ui.widgets.chat_view import ChatView                        # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def needed_px(body):
    """Сколько пикселей реально занимает текст в окне."""
    return body.count("1.0", "end", "ypixels")[0]


def worst_clip(view):
    """Худшая обрезка по всем репликам: (сколько не хватило, метка)."""
    worst, mark_worst = 0, None
    for mark in view._order:
        body = view._messages[mark].body
        if body is None:
            continue
        over = needed_px(body) - body.winfo_height()
        if over > worst:
            worst, mark_worst = over, mark
    return worst, mark_worst


def main():
    print("=" * 60)
    print("Проверка: текст реплики не обрезается снизу")
    print("=" * 60)

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("1000x600")
    # пиксельный шрифт чата — как в живом приложении (именно на нём баг виден)
    ui_fonts.register_font(getattr(config, "CHAT_FONT_FILE", ""))
    theme.resolve_fonts(root)
    print("шрифт чата: %s (пиксельный: %s)" % (theme.FONT_BODY, theme.CHAT_FONT_OK))

    view = ChatView(root, theme.DARK)
    view.pack(fill="both", expand=True)
    for _ in range(20):
        root.update()

    print("\n[1] Эмодзи в разных местах строк")
    cases = [
        ("эмодзи в начале строк", "😊 Первая строка\n🎯 Вторая строка\n👍 Третья"),
        ("эмодзи в середине", "Первая 😊 строка\nВторая 🎯 строка"),
        ("эмодзи на каждой строке", "😊😊 Первая 😊\n🎯🎯 Вторая 🎯\n👍👍 Третья 👍"),
        ("приветствие со снимка",
         "🦊 Привет, Дамиль! Я Verbot, твой преподаватель английского.\n"
         "🎯 Твой уровень: A2 — буду подбирать задания под него."),
        ("без эмодзи", "Первая строка\nВторая строка\nТретья строка"),
    ]
    marks = []
    for name, text in cases:
        marks.append((name, view.add_message("Verbot", text)))
    for _ in range(20):
        root.update()
        time.sleep(0.01)

    for name, mark in marks:
        body = view._messages[mark].body
        over = needed_px(body) - body.winfo_height()
        check("«%s» помещается целиком" % name, over <= 0,
              "нужно %d px, окно %d px (не хватает %d)"
              % (needed_px(body), body.winfo_height(), over))

    print("\n[2] Приветствие со снимка — отдельно и подробно")
    body = view._messages[marks[3][1]].body
    lines = int(body.index("end-1c").split(".")[0])
    print("     строк: %d, нужно %d px, окно %d px" % (
        lines, needed_px(body), body.winfo_height()))
    check("высота окна не меньше нужной", body.winfo_height() >= needed_px(body),
          (body.winfo_height(), needed_px(body)))
    last = body.bbox("%d.0 lineend" % lines)
    check("низ последней строки внутри окна",
          bool(last) and last[1] + last[3] <= body.winfo_height(),
          (last, body.winfo_height()))

    print("\n[3] Три ширины чата: перекладка не возвращает обрезку")
    for geo in ("1000x600", "820x600", "700x600"):
        root.geometry(geo)
        for _ in range(60):
            root.update()
            time.sleep(0.02)
        worst, mark = worst_clip(view)
        check("при окне %s обрезки нет" % geo, worst <= 0,
              "худшая обрезка %d px у %s" % (worst, mark))

    print("\n[4] После обновления текста обрезки нет")
    mark = marks[3][1]
    view.update_message(mark, "🦊 Привет!\n🎯 Уровень: B1 — идём дальше.\n"
                              "📚 Дальше больше практики.")
    for _ in range(20):
        root.update()
        time.sleep(0.01)
    body = view._messages[mark].body
    check("обновлённая реплика помещается целиком",
          needed_px(body) <= body.winfo_height(),
          (needed_px(body), body.winfo_height()))

    print("\n[5] Длинная реплика на много строк")
    long_text = "\n".join("Строка %d с эмодзи 😊 и текстом для проверки." % i
                          for i in range(1, 8))
    view.add_message("Вы", long_text)
    for _ in range(20):
        root.update()
        time.sleep(0.01)
    # у реплики ученика метки нет — берём последнюю по порядку
    body = view._messages[view._order[-1]].body
    lines = int(body.index("end-1c").split(".")[0])
    print("     строк: %d, нужно %d px, окно %d px" % (
        lines, needed_px(body), body.winfo_height()))
    check("длинная реплика помещается целиком",
          needed_px(body) <= body.winfo_height(),
          (needed_px(body), body.winfo_height()))
    worst, mark_worst = worst_clip(view)
    check("во всём чате нет ни одной обрезанной реплики", worst <= 0,
          "худшая %d px у %s" % (worst, mark_worst))

    root.destroy()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
