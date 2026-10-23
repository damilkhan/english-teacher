# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_CHAT_REPLAY.PY — кнопка «прослушать повторно» в облачке
# =========================================================
#   python tests\test_chat_replay.py
#
# Чат переписан на облачка (23.10.2026), поэтому кнопка живёт не в общем
# tk.Text, а в шапке облачка своей реплики. Проверяем то же самое:
#   1) у реплики преподавателя есть метка (для кнопки), у «Вы» — нет;
#   2) до enable_replay кнопки нет; после — есть, ровно одна;
#   3) повторный enable_replay не дублирует кнопку;
#   4) клик по кнопке зовёт on_replay с текстом ИМЕННО этой реплики;
#   5) get_text() не включает кнопку (это не текст);
#   6) clear() убирает кнопки;
#   7) неизвестная метка и реплика ученика игнорируются.
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


def replay_buttons(view):
    """Сколько реплик сейчас показывают кнопку «прослушать повторно»."""
    return [mark for mark in view._order
            if view._messages[mark].replay is not None]


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
    jane_mark = view.add_message("Verbot", "Hello, my friend! 😊")
    user_mark = view.add_message("Вы", "Привет")
    check("реплика преподавателя вернула метку", bool(jane_mark), jane_mark)
    check("реплика «Вы» метки не вернула", user_mark is None, user_mark)
    root.update()

    print("\n[2] Появление кнопки")
    check("до enable_replay кнопки нет", replay_buttons(view) == [],
          replay_buttons(view))
    view.enable_replay(jane_mark)
    root.update()
    check("после enable_replay кнопка появилась",
          replay_buttons(view) == [jane_mark], replay_buttons(view))
    widget = view._messages[jane_mark].replay
    check("кнопка стоит в шапке своей реплики",
          widget is not None and widget.master is view._messages[jane_mark].header,
          getattr(widget, "master", None))

    print("\n[3] Идемпотентность")
    view.enable_replay(jane_mark)
    root.update()
    check("повторный enable_replay не дублирует кнопку",
          replay_buttons(view) == [jane_mark], replay_buttons(view))

    print("\n[4] Клик по кнопке")
    widget.event_generate("<Button-1>")
    root.update()
    check("клик вызвал on_replay с текстом реплики",
          captured == ["Hello, my friend! 😊"], captured)

    print("\n[5] get_text не включает кнопку")
    text = view.get_text()
    check("текст реплики на месте", "Hello, my friend!" in text, text[-80:])
    check("в get_text нет служебной иконки", "🔊" not in text, text[-80:])
    check("имя отправителя в get_text есть", "Verbot" in text, text[:60])

    print("\n[6] clear убирает кнопки")
    view.clear()
    root.update()
    check("после clear кнопок нет", replay_buttons(view) == [], replay_buttons(view))
    check("после clear реплик нет", view._order == [], view._order)
    check("после clear в списке нет виджетов",
          len(view.list_frame.winfo_children()) == 0,
          view.list_frame.winfo_children())

    print("\n[7] Неизвестная метка и реплика ученика не роняют")
    try:
        ok_unknown = view.enable_replay("нет-такой-метки") is False
        ok_user = view.enable_replay(view.add_message("Вы", "ещё реплика")) is False
        ok = ok_unknown and ok_user
    except Exception as exc:          # noqa: BLE001
        ok = False
        print("     ", exc)
    check("неизвестная метка и реплика ученика игнорируются", ok)

    root.destroy()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
