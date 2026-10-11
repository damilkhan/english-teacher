# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_CHAT_REPLAY.PY — кнопка «прослушать повторно»
# =========================================================
#   python tests\test_chat_replay.py
#
# Проверяем (нужен экран — создаётся Tk-окно):
#   1) у реплики Джейн есть метка (для вставки кнопки), у «Вы» — нет;
#   2) до enable_replay кнопки нет; после — есть, ровно одна;
#   3) повторный enable_replay не дублирует кнопку;
#   4) клик по кнопке зовёт on_replay с текстом ИМЕННО этой реплики;
#   5) get_text() не включает кнопку (это не текст);
#   6) clear() убирает кнопки.
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
from ui.widgets.chat_view import ChatView  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("=" * 60)
    print("Проверка кнопки «прослушать повторно» (ChatView)")
    print("=" * 60)

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("600x300")
    captured = []
    view = ChatView(root, theme.DARK, on_replay=lambda t: captured.append(t))
    view.pack(fill="both", expand=True)
    root.update()

    print("\n[1] Метки реплик")
    jane_mark = view.add_message("Джейн", "Hello, my friend! 😊")
    user_mark = view.add_message("Вы", "Привет")
    check("реплика Джейн вернула метку", bool(jane_mark), jane_mark)
    check("реплика «Вы» метки не вернула", user_mark is None, user_mark)
    root.update()

    print("\n[2] Появление кнопки")
    check("до enable_replay кнопки нет", len(view.text.window_names()) == 0,
          view.text.window_names())
    view.enable_replay(jane_mark)
    root.update()
    windows = view.text.window_names()
    check("после enable_replay кнопка появилась", len(windows) == 1, windows)

    print("\n[3] Идемпотентность")
    view.enable_replay(jane_mark)
    root.update()
    check("повторный enable_replay не дублирует кнопку",
          len(view.text.window_names()) == 1, view.text.window_names())

    print("\n[4] Клик по кнопке")
    name = view.text.window_names()[0]
    widget = view.text.nametowidget(name)
    widget.event_generate("<Button-1>")
    root.update()
    check("клик вызвал on_replay с текстом реплики",
          captured == ["Hello, my friend! 😊"], captured)

    print("\n[5] get_text не включает кнопку")
    text = view.get_text()
    check("текст реплики на месте", "Hello, my friend!" in text, text[-80:])
    check("в get_text нет служебной метки/иконки", "🔊" not in text, text[-80:])

    print("\n[6] clear убирает кнопки")
    view.clear()
    root.update()
    check("после clear кнопок нет", len(view.text.window_names()) == 0,
          view.text.window_names())

    print("\n[7] Неизвестная метка не роняет")
    try:
        view.enable_replay("нет-такой-метки")
        ok = True
    except Exception as exc:          # noqa: BLE001
        ok = False
        print("     ", exc)
    check("неизвестная метка игнорируется", ok)

    root.destroy()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
