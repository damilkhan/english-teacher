# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_BAR.PY — виджеты занятия (нужен экран)
# =========================================================
#   python tests\test_lesson_bar.py
#
# Проверяем:
#   1) LessonBar: скрыта без урока, показывает урок/тип/прогресс, обновляет
#      счётчик, прячется по clear(), перекрашивается темой;
#   2) InputBar.set_locked: мягкая блокировка текста (поле не редактируется,
#      подсказка-замок на месте) и правильное снятие блокировки;
#   3) сосуществование ДВУХ состояний поля: гейт (профиль/сервер) и занятие
#      не «перетирают» друг друга;
#   4) ControlBar.set_record_enabled: кнопка записи гаснет в chat-уроке.
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

import customtkinter as ctk                                     # noqa: E402
import theme                                                    # noqa: E402
from ui.widgets.control_bar import ControlBar                   # noqa: E402
from ui.widgets.input_bar import InputBar, LOCK_HINT            # noqa: E402
from ui.widgets.lesson_bar import LessonBar                     # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def pump(root, n=12):
    for _ in range(n):
        root.update()


def visible(widget):
    return widget.winfo_manager() == "pack"


def main():
    print("=" * 60)
    print("Проверка виджетов занятия (полоса, поле ввода, кнопка записи)")
    print("=" * 60)

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("900x560")

    chat = ctk.CTkFrame(root, fg_color=theme.DARK["surface"])
    chat.pack(fill="both", expand=True)
    chat_view = ctk.CTkFrame(chat, fg_color=theme.DARK["chat_bg"])
    chat_view.pack(side="top", fill="both", expand=True)

    exits = []
    bar = LessonBar(chat, theme.DARK, on_exit=lambda: exits.append(True), before=chat_view)
    input_bar = InputBar(chat, theme.DARK, on_send=lambda: None)
    input_bar.pack(side="bottom", fill="x")
    control = ControlBar(chat, theme.DARK)
    control.pack(side="bottom", fill="x")
    pump(root)

    # ---------- 1. LessonBar ----------
    print("\n[1] Полоса урока (LessonBar)")
    check("без урока полоса скрыта", not visible(bar), bar.winfo_manager())
    check("текст пуст", bar.text == "", repr(bar.text))

    bar.set_lesson("Урок 1.1 · Hello / Hi", "говорение", "0/12")
    pump(root)
    check("полоса показана", visible(bar), bar.winfo_manager())
    check("в строке есть название урока", "Hello / Hi" in bar.text, bar.text)
    check("в строке есть тип", "говорение" in bar.text, bar.text)
    check("в строке есть прогресс", "0/12" in bar.text, bar.text)
    check("иконка урока на месте", "🎓" in bar.text, bar.text)

    bar.set_progress("5/12")
    pump(root)
    check("счётчик обновился", "5/12" in bar.text and "0/12" not in bar.text, bar.text)
    check("название не потерялось при смене счётчика", "Hello / Hi" in bar.text, bar.text)

    bar.clear()
    pump(root)
    check("после clear полоса спрятана", not visible(bar), bar.winfo_manager())

    bar.set_lesson("Урок 2.3 · Age", "текст", "1/12")
    pump(root)
    bar.apply_theme(theme.LIGHT)
    pump(root)
    check("apply_theme меняет фон полосы",
          bar.cget("fg_color") == theme.LIGHT["accent_soft"], bar.cget("fg_color"))
    check("после смены темы полоса видна", visible(bar))

    bar.exit_btn.invoke()
    check("кнопка «Выйти» зовёт обработчик", exits == [True], exits)
    bar.clear()
    pump(root)

    # ---------- 2. Мягкая блокировка ввода ----------
    print("\n[2] Блокировка текста в уроке «говорение»")
    check("поле изначально редактируемо", "disabled" not in str(input_bar._field.cget("state")))
    check("is_locked = False", input_bar.is_locked is False)

    input_bar.set_locked(True, "🔒 Слушай и отвечай голосом")
    pump(root)
    check("is_locked = True", input_bar.is_locked is True)
    check("поле НЕ редактируется", str(input_bar._field.cget("state")) == "disabled",
          input_bar._field.cget("state"))
    check("подсказка-замок видна",
          input_bar.textbox.get("0.0", "end-1c") == "🔒 Слушай и отвечай голосом",
          input_bar.textbox.get("0.0", "end-1c"))
    check("get_text() не отдаёт подсказку", input_bar.get_text() == "", repr(input_bar.get_text()))
    check("кнопка отправки показывает «голосом»", "Голосом" in input_bar.send_btn.cget("text"),
          input_bar.send_btn.cget("text"))

    input_bar.set_locked(False)
    pump(root)
    check("после снятия поле снова редактируемо",
          "disabled" not in str(input_bar._field.cget("state")))
    check("вернулась обычная подсказка",
          input_bar.textbox.get("0.0", "end-1c") == "Напиши сообщение…",
          input_bar.textbox.get("0.0", "end-1c"))

    input_bar.set_locked(True, LOCK_HINT)
    pump(root)
    check("подсказка по умолчанию тоже работает", LOCK_HINT in input_bar.textbox.get("0.0", "end-1c"))
    input_bar.set_locked(False)
    pump(root)

    # ---------- 3. Гейт + занятие вместе ----------
    print("\n[3] Гейт (профиль/сервер) и занятие не спорят")
    input_bar.set_enabled(False, "Заполни профиль")
    pump(root)
    check("гейт гасит отправку", str(input_bar.send_btn.cget("state")) == "disabled")
    check("на кнопке видна причина гейта",
          input_bar.send_btn.cget("text") == "Заполни профиль",
          input_bar.send_btn.cget("text"))

    input_bar.set_enabled(True)
    input_bar.set_locked(True, LOCK_HINT)
    pump(root)
    check("занятие заблокировало текст поверх включённого гейта",
          input_bar.is_locked and "disabled" in str(input_bar._field.cget("state")))

    # гейт закрылся ВО ВРЕМЯ урока — поле остаётся заблокированным занятием
    input_bar.set_enabled(False, "Загружаю модель…")
    pump(root)
    check("занятие остаётся главным для поля", "disabled" in str(input_bar._field.cget("state")))
    check("на кнопке причина гейта (он важнее)",
          input_bar.send_btn.cget("text") == "Загружаю модель…",
          input_bar.send_btn.cget("text"))

    # урок закончился, но гейт всё ещё закрыт — текст остаётся недоступен
    input_bar.set_locked(False)
    pump(root)
    check("после урока поле разблокировано", "disabled" not in str(input_bar._field.cget("state")))
    check("гейт по-прежнему держит отправку",
          input_bar.send_btn.cget("text") == "Загружаю модель…",
          input_bar.send_btn.cget("text"))

    input_bar.set_enabled(True)
    pump(root)
    check("после гейта кнопка снова обычная",
          input_bar.send_btn.cget("text") == "Отправить", input_bar.send_btn.cget("text"))

    # ---------- 4. Кнопка записи ----------
    print("\n[4] Кнопка записи в chat-уроке")
    control.set_record_enabled(True)
    pump(root)
    check("кнопка записи включена", str(control.record_btn.cget("state")) == "normal",
          control.record_btn.cget("state"))
    control.set_record_enabled(False)
    pump(root)
    check("в chat-уроке кнопка записи выключена",
          str(control.record_btn.cget("state")) == "disabled",
          control.record_btn.cget("state"))
    control.set_record_enabled(True)
    pump(root)

    root.destroy()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
