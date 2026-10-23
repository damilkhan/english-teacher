# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_CHAT_LAYOUT.PY — раскладка вкладки «Чат»: робот ПОД чатом
# =========================================================
#   python tests\test_chat_layout.py   (нужен экран — создаётся Tk-окно)
#
# Решение ученика 23.10.2026: робот больше не лежит поверх чата. Он стоит
# отдельным блоком ПОД чатом справа, а поле ввода и кнопки уехали влево.
# Чат стал мессенджером с облачками (ui/widgets/chat_view.py).
#
# Проверяем:
#   1) робот в своей полосе ПОД чатом и НЕ перекрывает его;
#   2) чат занимает всю ширину вкладки, робот не отнимает у него место;
#   3) блок ввода + робот вместе занимают ровно ширину вкладки;
#   4) кнопки нижнего ряда не вылезают за край (на минимальном окне тоже);
#   5) облачка: преподаватель слева, ученик справа, цвета из theme.py;
#   6) ChatView больше не знает про робота (обтекание не вернулось).
# =========================================================

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                                                    # noqa: E402
import profile_store                                             # noqa: E402
import theme                                                     # noqa: E402
import user_manager                                              # noqa: E402
from ui.widgets import chat_view as chat_mod                     # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class TempProfiles:
    """Временная папка профилей: реальные файлы ученика не трогаем."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_layout_")
        self.real = (user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE)
        user_manager.PROFILES_DIR = self.dir
        user_manager.LAST_USER_FILE = os.path.join(self.dir, "last_user.txt")
        profile_store.set_active_user(None)
        return self.dir

    def __exit__(self, *exc):
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE = self.real
        profile_store.set_active_user(None)
        return False


def build_app():
    """Настоящее окно приложения на временной папке профилей (без звука)."""
    import stt_engine
    import tts
    tts.speak = lambda *a, **k: None
    stt_engine.STTEngine.preload = lambda self: None

    import customtkinter as ctk
    from ui.app import EnglishTeacherApp
    from ui.panels.block_panel import BlockPanel
    from ui.panels.boot_panel import BootPanel
    from ui.panels.level_test_panel import LevelTestPanel
    from ui.first_run import FirstRunForm
    for cls in (BootPanel, LevelTestPanel, FirstRunForm, BlockPanel):
        cls.ask = staticmethod(lambda *a, **k: None)

    ctk.set_appearance_mode("dark")
    app = EnglishTeacherApp()
    app.maybe_review_vocabulary = lambda: None
    app._arm_auto_lesson = lambda: False
    for _ in range(40):
        app.window.update()
        time.sleep(0.02)
    return app


def geometry(app):
    """Прямоугольники в координатах окна: (x, y, w, h)."""
    def box(widget):
        return (widget.winfo_rootx() - app.window.winfo_rootx(),
                widget.winfo_rooty() - app.window.winfo_rooty(),
                widget.winfo_width(), widget.winfo_height())
    return box


def main():
    print("=" * 60)
    print("Проверка раскладки чата (робот под чатом, облачка)")
    print("=" * 60)

    with TempProfiles():
        app = build_app()
        box = geometry(app)
        try:
            print("\n[1] Робот под чатом, вне чата")
            check("блок робота создан", app.robot_host is not None, app.robot_host)
            check("робот подключён", bool(getattr(app.character, "available", False)),
                  app.character)
            chat = box(app.chat_view)
            robot = box(app.robot_host)
            print("     чат:    x=%d y=%d w=%d h=%d" % chat)
            print("     робот:  x=%d y=%d w=%d h=%d" % robot)
            overlap_v = max(0, (chat[1] + chat[3]) - robot[1])
            overlap_h = max(0, min(chat[0] + chat[2], robot[0] + robot[2])
                            - max(chat[0], robot[0]))
            check("робот НИЖЕ чата (0 px наложения по высоте)", overlap_v == 0,
                  "наложение %d px" % overlap_v)
            check("робот не «внутри» чата по горизонтали",
                  overlap_h == 0 or robot[1] >= chat[1] + chat[3],
                  "пересечение по X %d px" % overlap_h)
            check("робот справа (правее середины вкладки)",
                  robot[0] > chat[0] + chat[2] // 2, (robot[0], chat[0] + chat[2]))
            check("робот стоит над нижним краем окна",
                  robot[1] + robot[3] <= box(app.left_frame)[1]
                  + box(app.left_frame)[3] + 1, robot)

            print("\n[2] Чат занимает всю ширину вкладки")
            check("ширина чата = ширине нижнего ряда (± 2 px)",
                  abs(chat[2] - box(app.bottom_row)[2]) <= 2,
                  (chat[2], box(app.bottom_row)[2]))
            check("чат шире, чем блок ввода с кнопками",
                  chat[2] > box(app.input_control)[2],
                  (chat[2], box(app.input_control)[2]))

            print("\n[3] Нижний ряд: ввод слева, робот справа")
            left = box(app.input_control)
            gap = robot[0] - (left[0] + left[2])
            check("зазор между вводом и роботом не отрицательный", gap >= 0, gap)
            check("ввод и робот вместе занимают ряд",
                  abs((left[2] + gap + robot[2]) - box(app.bottom_row)[2]) <= 2,
                  (left[2], gap, robot[2], box(app.bottom_row)[2]))

            print("\n[3b] В колонке ввода нет пустой полосы")
            ib = box(app.input_bar)
            check("поле ввода начинается сверху колонки (0 px пустоты)",
                  ib[1] - left[1] == 0, "пустота %d px" % (ib[1] - left[1]))
            check("поле ввода занимает всю высоту, кроме кнопок",
                  ib[3] >= left[3] - box(app.control_bar)[3] - 10,
                  (ib[3], left[3], box(app.control_bar)[3]))
            check("поле ввода не выше 130 px (не раздулось)",
                  ib[3] <= 130, ib[3])

            print("\n[4] Кнопки не вылезают за край")
            for name, btn in (("record", app.control_bar.record_btn),
                              ("clear", app.control_bar.clear_btn),
                              ("users", app.control_bar.users_btn),
                              ("settings", app.control_bar.settings_btn)):
                b = box(btn)
                check("кнопка %s внутри ряда" % name,
                      b[0] + b[2] <= left[0] + left[2] + 1,
                      "%d > %d" % (b[0] + b[2], left[0] + left[2]))

            print("\n[5] Облачка: ученик СЛЕВА, преподаватель СПРАВА")
            view = app.chat_view
            teacher_mark = view.add_message(app.teacher_name,
                                            "Привет! Как дела? 😊")
            view.add_message("Вы", "Всё хорошо, спасибо!")
            for _ in range(12):
                app.window.update()
                time.sleep(0.01)
            t_msg = view._messages[teacher_mark]
            # у реплик ученика метки нет (add_message вернул None) — берём
            # последнюю по порядку
            u_msg = view._messages[view._order[-1]]
            left_edge = view.canvas.winfo_rootx() + chat_mod.SIDE_PAD
            # холст уже не включает полосу прокрутки (она рядом, sibling),
            # поэтому отступаем только SIDE_PAD — как и слева
            right_edge = (view.canvas.winfo_rootx() + view.canvas.winfo_width()
                          - chat_mod.SIDE_PAD)
            check("реплика ученика левее реплики преподавателя",
                  u_msg.bubble.winfo_rootx() < t_msg.bubble.winfo_rootx(),
                  (u_msg.bubble.winfo_rootx(), t_msg.bubble.winfo_rootx()))
            # облачко стоит сразу за своим «хвостиком» (6 px воздуха)
            check("облачко ученика начинается сразу за хвостиком",
                  abs((u_msg.bubble.winfo_rootx()
                       - (u_msg.tail.winfo_rootx() + u_msg.tail.winfo_width())) - 6) <= 1,
                  (u_msg.bubble.winfo_rootx(), u_msg.tail.winfo_rootx(),
                   u_msg.tail.winfo_width()))
            check("облачко преподавателя кончается сразу за хвостиком",
                  abs((t_msg.tail.winfo_rootx()
                       - (t_msg.bubble.winfo_rootx() + t_msg.bubble.winfo_width())) - 6) <= 1,
                  (t_msg.tail.winfo_rootx(),
                   t_msg.bubble.winfo_rootx() + t_msg.bubble.winfo_width()))
            check("облачко ученика у левого края чата (с учётом хвостика)",
                  abs(u_msg.tail.winfo_rootx() - left_edge) <= 6,
                  (u_msg.tail.winfo_rootx(), left_edge))
            check("облачко преподавателя у правого края чата (с учётом хвостика)",
                  abs((t_msg.tail.winfo_rootx() + t_msg.tail.winfo_width())
                      - right_edge) <= 8,
                  (t_msg.tail.winfo_rootx() + t_msg.tail.winfo_width(),
                   right_edge))
            check("«хвостик» ученика слева от его облачка",
                  u_msg.tail.winfo_rootx() < u_msg.bubble.winfo_rootx(),
                  (u_msg.tail.winfo_rootx(), u_msg.bubble.winfo_rootx()))
            check("«хвостик» преподавателя справа от его облачка",
                  t_msg.tail.winfo_rootx() > t_msg.bubble.winfo_rootx(),
                  (t_msg.tail.winfo_rootx(), t_msg.bubble.winfo_rootx()))
            p = app.palette
            check("фон облачка преподавателя из theme.py",
                  t_msg.bubble.cget("fg_color") == p["bubble_teacher"],
                  t_msg.bubble.cget("fg_color"))
            check("фон облачка ученика из theme.py",
                  u_msg.bubble.cget("fg_color") == p["bubble_user"],
                  u_msg.bubble.cget("fg_color"))
            check("фон облачка отличается от фона чата",
                  p["bubble_teacher"] != p["chat_bg"] != p["bubble_user"],
                  (p["bubble_teacher"], p["chat_bg"], p["bubble_user"]))
            check("у реплик есть «хвостик»",
                  t_msg.tail is not None and u_msg.tail is not None)

            print("\n[6] ChatView больше не знает про робота")
            check("нет set_character_reserve", not hasattr(view, "set_character_reserve"))
            check("нет robot_inset", not hasattr(view, "robot_inset"))
            check("нет тега обтекания", not hasattr(view, "set_character_reserve")
                  and not hasattr(view, "_apply_avoid"))

            print("\n[7] Минимальное окно: всё помещается")
            app.window.geometry("1040x620")
            for _ in range(40):
                app.window.update()
                time.sleep(0.02)
            chat = box(app.chat_view)
            robot = box(app.robot_host)
            left = box(app.input_control)
            print("     чат:    %dx%d" % (chat[2], chat[3]))
            print("     робот:  %dx%d" % (robot[2], robot[3]))
            print("     ввод:   %dx%d" % (left[2], left[3]))
            check("на минимальном окне робот по-прежнему ниже чата",
                  max(0, (chat[1] + chat[3]) - robot[1]) == 0,
                  "наложение %d" % max(0, (chat[1] + chat[3]) - robot[1]))
            check("на минимальном окне чат не ниже 150 px", chat[3] >= 150, chat[3])
            check("на минимальном окне в колонке ввода нет пустоты",
                  box(app.input_bar)[1] - left[1] == 0,
                  box(app.input_bar)[1] - left[1])
            check("на минимальном окне кнопке «Настройки» хватает места",
                  box(app.control_bar.settings_btn)[0]
                  + box(app.control_bar.settings_btn)[2]
                  <= left[0] + left[2] + 1,
                  (box(app.control_bar.settings_btn), left))
        finally:
            app.on_closing()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
