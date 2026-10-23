# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_CHAT_SCROLL.PY — прокрутка чата с облачками
# =========================================================
#   python tests\test_chat_scroll.py   (нужен экран — создаётся Tk-окно)
#
# ИСТОРИЯ. Баг ученика (23.10.2026): при прокрутке текст в чате «прыгал»,
# потому что правый отступ обтекания робота пересчитывался прямо во время
# прокрутки. Затем чат переписали на ОБЛАЧКА (список виджетов), и обтекание
# робота убрали совсем: робот стоит под чатом (см. tests\test_chat_layout.py).
#
# Проверяем то, что теперь важно:
#   1) полоса прокрутки достаточно широкая (>= 10 px) и не накрыта;
#   2) содержимое растягивается на всю ширину, прокрутка появляется;
#   3) во время прокрутки ширина облачков НЕ меняется (0 изменений на
#      20 шагов колеса) — тот же баг «текст прыгает», но для облачков;
#   4) колесо мыши прокручивает чат;
#   5) после новой реплики чат внизу;
#   6) облачко не шире предела и текст не обрезан (xview = 0..1);
#   7) при сужении окна реплики раскладываются заново и остаются в пределах;
#   8) короткое содержимое НЕ уезжает вниз: пустоты над первой репликой нет
#      (баг со снимка 23.10.2026: колесо вверх давало canvasy(0) = -652 px),
#      и первая реплика не липнет к самому верху чата.
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

import customtkinter as ctk          # noqa: E402
import theme                         # noqa: E402
from ui.widgets import chat_view as chat_mod  # noqa: E402
from ui.widgets.chat_view import ChatView      # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def make_view(width, height, messages=14):
    """Окно и чат с репликами (по умолчанию — много, чтобы было что крутить)."""
    root = ctk.CTk()
    root.geometry("%dx%d" % (width, height))
    frame = ctk.CTkFrame(root, fg_color=theme.DARK["surface"])
    frame.pack(fill="both", expand=True)
    view = ChatView(frame, theme.DARK)
    view.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 8))
    for i in range(messages):
        view.add_message(
            "Verbot",
            "Message %d: tell me about your day, what you did in the morning "
            "and what you plan to do in the evening." % i)
        view.add_message("Вы", "I woke up at seven, had breakfast, then I went to work.")
    root.update()
    return root, view


def widths(view):
    """Ширины всех облачков по порядку (то, что не должно «дёргаться»)."""
    return tuple(view._messages[mark].bubble.winfo_width()
                 for mark in view._order
                 if view._messages[mark].bubble is not None)


def main():
    print("=" * 60)
    print("Проверка прокрутки чата с облачками")
    print("=" * 60)

    ctk.set_appearance_mode("dark")

    print("\n[1] Полоса прокрутки")
    check("SCROLLBAR_WIDTH >= 10 px",
          chat_mod.SCROLLBAR_WIDTH >= 10, chat_mod.SCROLLBAR_WIDTH)

    root, view = make_view(1040, 620)   # минимальный размер окна
    try:
        check("полоса прокрутки видна (>= 10 px на экране)",
              view.scrollbar.winfo_width() >= 10, view.scrollbar.winfo_width())
        check("фон чата и фон списка совпадают",
              view.canvas.cget("bg") == view.list_frame.cget("fg_color"),
              (view.canvas.cget("bg"), view.list_frame.cget("fg_color")))

        print("\n[2] Содержимое и прокрутка")
        region = view.canvas.bbox("all")
        check("область прокрутки не пустая", bool(region) and region[3] > 0, region)
        first, last = view.canvas.yview()
        check("прокрутка есть (видно не всё)", last - first < 0.99, (first, last))
        width_item = view.canvas.itemcget(view._window, "width")
        check("список реплик растянут на всю ширину холста",
              int(float(width_item)) == view.canvas.winfo_width(),
              "%s против %s" % (width_item, view.canvas.winfo_width()))

        print("\n[3] Во время прокрутки облачка не меняются")
        before = widths(view)
        flips = 0
        for _ in range(20):
            view.canvas.yview_scroll(-1, "units")
            root.update_idletasks()
            root.update()
            if widths(view) != before:
                flips += 1
        check("0 изменений ширины на 20 шагов", flips == 0, flips)

        print("\n[4] Колесо мыши прокручивает чат")
        view.canvas.yview_moveto(0.0)
        root.update()

        class WheelEvent:
            delta = -120
            widget = view.canvas

        view._on_wheel(WheelEvent())
        root.update()
        after = view.canvas.yview()
        check("колесо сдвинуло чат вниз", after[0] > 0.0 or after[1] >= 0.99,
              (after, view.canvas.yview()))
        # колесо над ЧУЖИМ виджетом чат не крутит
        before_foreign = view.canvas.yview()

        class ForeignEvent:
            delta = -120
            widget = root

        view._on_wheel(ForeignEvent())
        root.update()
        check("колесо вне чата чат не крутит",
              view.canvas.yview() == before_foreign,
              (before_foreign, view.canvas.yview()))

        print("\n[5] Новая реплика показывается (чат внизу)")
        view.add_message("Вы", "свежая реплика внизу")
        for _ in range(12):
            root.update()
            time.sleep(0.01)
        first2, last2 = view.canvas.yview()
        check("после новой реплики видно конец чата", last2 >= 0.99, (first2, last2))

        print("\n[6] Облачко не шире предела, текст не обрезан")
        limit = view._bubble_max_px()
        wide = [mark for mark in view._order
                if view._messages[mark].body is not None
                and view._messages[mark].body.winfo_width() > limit + 30]
        check("все облачка в пределах допустимой ширины", not wide, wide[:3])
        clipped = []
        for mark in view._order:
            body = view._messages[mark].body
            if body is None:
                continue
            xv = body.xview()
            if xv[1] < 0.999:
                clipped.append((mark, xv))
        check("ни один текст не обрезан по ширине", not clipped, clipped[:3])

        print("\n[7] Сужение окна: реплики раскладываются заново")
        wide_before = max(widths(view))
        root.geometry("760x620")
        for _ in range(40):
            root.update()
            time.sleep(0.02)
        wide_after = max(widths(view))
        check("после сужения облачка стали уже",
              wide_after < wide_before,
              "%d → %d" % (wide_before, wide_after))
        over = [mark for mark in view._order
                if view._messages[mark].body is not None
                and view._messages[mark].body.xview()[1] < 0.999]
        check("после сужения текст по-прежнему не обрезан", not over, over[:3])

        print("\n[8] Прокрутка вверх не уходит в минус")
        view.canvas.yview_moveto(0.0)
        root.update()
        check("в самом верху начало содержимого на нуле",
              view.canvas.canvasy(0) == 0, "canvasy(0) = %d px" % view.canvas.canvasy(0))
        # крутим вверх СИЛЬНО: раньше это давало отрицательное смещение
        view.canvas.yview_scroll(-50, "units")
        root.update()
        check("сильная прокрутка вверх не даёт отрицательного смещения",
              view.canvas.canvasy(0) == 0, "canvasy(0) = %d px" % view.canvas.canvasy(0))

        # и через обработчик колеса (он же используется в жизни)
        class UpWheel:
            delta = 120
            widget = view.canvas

        view._on_wheel(UpWheel())
        root.update()
        check("обработчик колеса тоже не сдвигает чат",
              view.canvas.canvasy(0) == 0, view.canvas.canvasy(0))

        first = view._messages[view._order[0]].bubble
        offset = first.winfo_rooty() - view.canvas.winfo_rooty()
        check("первая реплика не липнет к верхнему краю (отступ >= 8 px)",
              offset >= 8, "отступ %d px" % offset)
        print("     (кэш, чтобы проверка была не на «глаз»: отступ = %d px)" % offset)
    finally:
        root.destroy()

    # ---- отдельный, чистый случай: ОДНО сообщение на большой чат ----
    root2, view2 = make_view(1160, 760, messages=1)
    try:
        print("\n[9] Одно сообщение в большом окне")
        check("весь текст помещается", view2.canvas.yview() == (0.0, 1.0),
              view2.canvas.yview())
        check("пустоты над репликой нет", view2.canvas.canvasy(0) == 0,
              view2.canvas.canvasy(0))
        view2.canvas.yview_scroll(-30, "units")
        root2.update()
        check("прокрутка вверх не оставляет пустоту",
              view2.canvas.canvasy(0) == 0, view2.canvas.canvasy(0))
        bubble = view2._messages[view2._order[0]].bubble
        gap = bubble.winfo_rooty() - view2.canvas.winfo_rooty()
        check("у первой реплики есть отступ сверху", gap >= 8, gap)
    finally:
        root2.destroy()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
