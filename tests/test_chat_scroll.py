# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_CHAT_SCROLL.PY — прокрутка чата и обтекание робота
# =========================================================
#   python tests\test_chat_scroll.py
#
# Баг ученика (23.10.2026): при минимальном размере окна текст в чате
# «дёргается и прыгает», а ползунок прокрутки слишком тонкий и при
# прокрутке вниз исчезает под роботом.
#
# Причина (замер): правый отступ обтекания пересчитывался ПРЯМО ВО ВРЕМЯ
# прокрутки, каждые 30 мс. Отступ меняет перенос слов → меняется высота
# реплики → меняется решение «попадает на полосу робота или нет» → снова
# отступ. На 20 шагов колеса приходилось 11 таких переворотов, и текст
# подпрыгивал. Плюс робот стоял вплотную к правому краю и своим холстом
# накрывал полосу прокрутки шириной 6 px.
#
# Проверяем (нужен экран — создаётся Tk-окно):
#   1) полоса прокрутки достаточно широкая (>= 10 px);
#   2) холст робота НЕ накрывает полосу прокрутки;
#   3) правый отступ обтекания учитывает отступ робота;
#   4) во время прокрутки текст НЕ переформатируется (0 смен);
#   5) после остановки прокрутки состояние устойчиво (не мигает);
#   6) обтекание по-прежнему включается для реплики на полосе робота.
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
import character                     # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def make_view(width, height):
    """Окно, чат с роботом и много реплик (чтобы чат прокручивался)."""
    root = ctk.CTk()
    root.geometry("%dx%d" % (width, height))
    frame = ctk.CTkFrame(root, fg_color=theme.DARK["surface"])
    frame.pack(fill="both", expand=True)
    view = ChatView(frame, theme.DARK)
    view.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 8))
    robot = character.Character(view, width=300, inset_right=view.robot_inset)
    view.set_character_reserve(*robot.reserve)
    for i in range(14):
        view.add_message(
            "Джейн",
            "Message %d: tell me about your day, what you did in the morning "
            "and what you plan to do in the evening." % i)
        view.add_message("Вы", "I woke up at seven, had breakfast, then I went to work.")
    root.update()
    return root, view, robot


def marked_tags(view):
    """Кортеж: стоит ли отступ у каждой реплики (по порядку).

    Спрашиваем теги У САМОГО ИНДЕКСА реплики, а не сверяем начало с
    tag_ranges("avoid_robot"): соседние реплики Tk сливает в ОДИН диапазон,
    и сверка «по началам» показывала False у середины полосы.
    """
    result = []
    for tag in view._avoid_tags:
        own = view.text.tag_ranges(tag)
        if not own:
            continue
        result.append("avoid_robot" in view.text.tag_names(own[0]))
    return tuple(result)


def main():
    print("=" * 60)
    print("Проверка прокрутки чата и обтекания робота")
    print("=" * 60)

    ctk.set_appearance_mode("dark")

    print("\n[1] Полоса прокрутки достаточно широкая")
    check("SCROLLBAR_WIDTH >= 10 px",
          chat_mod.SCROLLBAR_WIDTH >= 10, chat_mod.SCROLLBAR_WIDTH)

    print("\n[2] Робот не накрывает полосу прокрутки")
    root, view, robot = make_view(1040, 620)   # минимальный размер окна
    try:
        sb = view.scrollbar
        sb_left = sb.winfo_x()
        sb_right = sb_left + sb.winfo_width()
        rb_left = robot.canvas.winfo_x()
        rb_right = rb_left + robot.canvas.winfo_width()
        overlap = max(0, min(sb_right, rb_right) - max(sb_left, rb_left))
        check("полоса прокрутки шире 10 px на экране",
              sb.winfo_width() >= 10, sb.winfo_width())
        check("холст робота НЕ накрывает полосу (0 px наложения)",
              overlap == 0, "наложение %d px (полоса %d..%d, робот %d..%d)"
              % (overlap, sb_left, sb_right, rb_left, rb_right))
        check("отступ робота = место полосы + воздух",
              view.robot_inset == chat_mod.SCROLL_PAD_X
              + chat_mod.SCROLLBAR_WIDTH + chat_mod.ROBOT_GUTTER,
              view.robot_inset)

        print("\n[3] Отступ обтекания учитывает отступ робота")
        rmargin = int(float(view.text.tag_cget("avoid_robot", "rmargin")))
        need = view._robot_w + view.robot_inset
        check("rmargin >= ширина робота + отступ", rmargin >= need,
              "rmargin=%d, нужно %d" % (rmargin, need))

        print("\n[4] Во время прокрутки текст не переформатируется")
        prev = marked_tags(view)
        flips = 0
        for _ in range(20):
            view.text.yview_scroll(-1, "units")
            root.update_idletasks()
            root.update()
            cur = marked_tags(view)
            if cur != prev:
                flips += 1
            prev = cur
        check("0 переворотов обтекания на 20 шагов колеса", flips == 0, flips)

        print("\n[5] После остановки состояние устойчиво")
        for _ in range(30):                 # дать таймеру сработать
            root.update()
            time.sleep(0.02)
        settled = marked_tags(view)
        for _ in range(12):
            root.update()
            time.sleep(0.02)
        check("обтекание не мигает после остановки",
              marked_tags(view) == settled, marked_tags(view))

        print("\n[6] Обтекание по-прежнему работает")
        view.text.see("end")
        for _ in range(30):
            root.update()
            time.sleep(0.02)
        tail = marked_tags(view)
        check("последняя реплика на полосе робота получила отступ",
              bool(tail) and tail[-1] is True, tail[-3:])
    finally:
        root.destroy()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
