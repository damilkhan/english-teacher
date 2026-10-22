# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GREETING.PY — вступительная реплика и строка уровня
# =========================================================
#   python tests\test_greeting.py     (нужно окно Windows)
#
# Решение ученика (22.10.2026): «вступительного сообщения слишком много»,
# и строка «уровень пока не определён» после теста должна ЗАМЕНЯТЬСЯ на
# «твой уровень: A2», а не висеть рядом со второй репликой «уровень
# определён: A2».
#
# Проверяем:
#   1) текст приветствия: две строки, без лишнего абзаца, уровень в нём;
#   2) update_message заменяет текст реплики и НЕ создаёт новую;
#   3) живое окно: после теста в чате ОДНА реплика Джейн с уровнем A2,
#      слова «не определён» в ней нет;
#   4) реплика, за которой уже есть сообщения, сохраняет своё место;
#   5) «Очистить» возвращает приветствие с актуальным уровнем;
#   6) смена ученика показывает ЕГО уровень.
# =========================================================

import os
import shutil
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

import user_manager                                          # noqa: E402

FAILED = []

NOT_DEFINED = "не определён"


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class TempProfiles:
    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_greet_")
        self.real_dir = user_manager.PROFILES_DIR
        self.real_last = user_manager.LAST_USER_FILE
        user_manager.PROFILES_DIR = self.dir
        user_manager.LAST_USER_FILE = os.path.join(self.dir, "last_user.txt")
        return self.dir

    def __exit__(self, *exc):
        user_manager.PROFILES_DIR = self.real_dir
        user_manager.LAST_USER_FILE = self.real_last
        shutil.rmtree(self.dir, ignore_errors=True)
        return False


# =========================================================
# 1. Текст приветствия
# =========================================================
def test_greeting_text():
    print("\n[1] Текст вступительной реплики")
    from ui.app import EnglishTeacherApp

    app = EnglishTeacherApp.__new__(EnglishTeacherApp)      # без окна
    app.current_user = {"name": "Дамиль", "avatar": "🦊", "level": None}
    text = app._greeting()
    print("     без уровня: %r" % text)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    check("две строки, а не три", len(lines) == 2, lines)
    check("имя есть", "Дамиль" in text, text)
    check("строка уровня есть", "уровень" in text.lower(), text)
    check("про «не определён» сказано", NOT_DEFINED in text, text)
    check("абзац «буду запоминать ошибки» убран",
          "запоминать" not in text.lower(), text)
    check("в тексте не больше 40 слов", len(text.split()) <= 40, len(text.split()))

    app.current_user = {"name": "Дамиль", "avatar": "🦊", "level": "A2"}
    text2 = app._greeting()
    print("     с уровнем : %r" % text2)
    check("с уровнем: ровно две строки",
          len([ln for ln in text2.splitlines() if ln.strip()]) == 2, text2)
    check("уровень A2 назван", "A2" in text2, text2)
    check("слова «не определён» больше нет", NOT_DEFINED not in text2, text2)


# =========================================================
# 2-4. update_message на живом виджете
# =========================================================
def test_update_message():
    print("\n[2] update_message: замена текста без новой реплики")
    import customtkinter as ctk
    import theme
    from ui.widgets.chat_view import ChatView

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("700x500+40+40")
    theme.resolve_fonts(root)
    view = ChatView(root, theme.DARK, on_replay=lambda text: None)
    view.pack(fill="both", expand=True)
    try:
        for _ in range(20):
            root.update()
            time.sleep(0.02)

        mark = view.add_message("Джейн", "Привет!\n🎯 Уровень пока не определён.")
        for _ in range(10):
            root.update()
        before = view.get_text()
        check("метка у реплики Джейн есть", bool(mark), mark)
        check("реплика видна", "Привет!" in before, repr(before))

        ok = view.update_message(mark, "Привет!\n🎯 Твой уровень: A2.")
        for _ in range(10):
            root.update()
        after = view.get_text()
        print("     после замены: %r" % after)

        check("замена вернула True", ok is True, ok)
        check("новый текст на месте", "A2" in after, repr(after))
        check("старый текст исчез", NOT_DEFINED not in after, repr(after))
        check("вторая реплика НЕ появилась", after.count("Привет!") == 1,
              after.count("Привет!"))
        check("имя Джейн по-прежнему одно", after.count("Джейн") == 1,
              after.count("Джейн"))

        # за репликой уже есть сообщение — текст должен остаться на своём месте
        print("\n[4] Реплика с сообщениями ПОСЛЕ неё сохраняет место")
        view.add_message("Вы", "последняя реплика ученика")
        for _ in range(10):
            root.update()
        view.update_message(mark, "Привет!\n🎯 Твой уровень: B1.")
        for _ in range(10):
            root.update()
        text = view.get_text()
        idx_greeting = text.find("B1")
        idx_user = text.find("последняя реплика")
        print("     позиция приветствия: %d, реплики ученика: %d"
              % (idx_greeting, idx_user))
        check("приветствие осталось ВЫШЕ реплики ученика",
              0 <= idx_greeting < idx_user, (idx_greeting, idx_user))

        # неизвестная метка — тихий отказ
        check("чужая метка не ломает виджет",
              view.update_message("replay_msg_999", "текст") is False)
    finally:
        try:
            view.destroy()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass


# =========================================================
# 3-6. Живое окно приложения
# =========================================================
def _build_app(tmp_dir, form_answer, holder):
    """Окно приложения на временной папке профилей.

    Тест уровня подменён, но он СОХРАНЯЕТ уровень в профиль — как настоящий
    (настоящий пишет его в level_test.get_result). holder["level"]=None
    означает «тест не дал уровня» (ученик прервал) — строка в приветствии
    остаётся прежней.
    """
    import tts
    tts.speak = lambda *a, **k: None

    import customtkinter as ctk
    ctk.set_appearance_mode("dark")

    import ui.first_run as first_run
    import ui.panels.level_test_panel as level_test_panel
    import ui.panels.block_panel as block_panel
    import ui.panels.boot_panel as boot_panel

    first_run.FirstRunForm.ask = staticmethod(lambda *a, **k: dict(form_answer))

    def fake_level_test(_parent, _palette, _controller, user_id, ready_probe=None):
        level = (holder or {}).get("level")
        if level:
            user_manager.update_user(user_id, {"level": level})
        return level

    level_test_panel.LevelTestPanel.ask = staticmethod(fake_level_test)
    boot_panel.BootPanel.ask = staticmethod(lambda *a, **k: None)
    block_panel.BlockPanel.ask = staticmethod(lambda *a, **k: None)

    import profile_store
    real_store = profile_store.PROFILE_PATH
    profile_store.PROFILE_PATH = os.path.join(tmp_dir, "user_profile.json")

    from ui.app import EnglishTeacherApp
    app = EnglishTeacherApp()
    app.maybe_review_vocabulary = lambda: None
    app._arm_auto_lesson = lambda: False
    for _ in range(40):
        app.window.update()
        time.sleep(0.02)
    return app, real_store, profile_store


def test_app_after_level_test():
    print("\n[3] Живое окно: после теста уровня")
    answer = {"name": "Дамиль", "name_latin": "Damil", "gender": "male",
              "age": "14", "goal": "", "avatar": "🦊"}
    with TempProfiles() as tmp:
        first = user_manager.create_user(**answer, complete=True)
        holder = {"level": None}          # тест ещё не дал уровня
        app, real_store, store_mod = _build_app(tmp, answer, holder)
        try:
            check("метка приветствия запомнена", bool(app._greeting_mark),
                  app._greeting_mark)
            before = app.chat_view.get_text()
            print("     чат при запуске: %r" % before)
            check("до теста в чате «не определён»", NOT_DEFINED in before,
                  repr(before[-120:]))
            check("вступительная реплика ОДНА",
                  before.count("Привет,") == 1, before.count("Привет,"))
            check("третьей реплики «Создан профиль» нет",
                  "Создан профиль" not in before, repr(before[-80:]))

            holder["level"] = "A2"        # теперь тест прошёл
            app.run_level_test(first["id"])
            for _ in range(40):
                app.window.update()
                time.sleep(0.02)
            after = app.chat_view.get_text()
            print("     чат после теста: %r" % after)

            check("уровень A2 показан", "A2" in after, repr(after))
            check("«не определён» больше НЕ висит", NOT_DEFINED not in after,
                  repr(after))
            check("вступительная реплика по-прежнему ОДНА",
                  after.count("Привет,") == 1, after.count("Привет,"))
            check("вторая строка уровня не добавилась",
                  after.count("Твой уровень") == 1, after.count("Твой уровень"))
            check("отдельной реплики «Уровень определён» нет",
                  "Уровень определён" not in after, repr(after))

            print("\n[5] «Очистить» возвращает приветствие")
            app.clear_chat()
            for _ in range(20):
                app.window.update()
            cleared = app.chat_view.get_text()
            check("после очистки чат не пустой", "Привет" in cleared, repr(cleared))
            check("уровень в приветствии актуальный", "A2" in cleared, repr(cleared))
            check("метка приветствия снова известна", bool(app._greeting_mark),
                  app._greeting_mark)

            print("\n[6] Смена ученика показывает ЕГО уровень")
            second = user_manager.create_user("Аня", "female", 12, complete=True)
            user_manager.update_user(second["id"], {"level": "B1"})
            app.select_user(second["id"], force=True)
            for _ in range(30):
                app.window.update()
            swapped = app.chat_view.get_text()
            check("в приветствии имя нового ученика", "Аня" in swapped, repr(swapped))
            check("в приветствии ЕГО уровень B1", "B1" in swapped, repr(swapped))
            check("уровня прошлого ученика нет", "A2" not in swapped, repr(swapped))
        finally:
            store_mod.PROFILE_PATH = real_store
            try:
                app.window.destroy()
            except Exception:
                pass


def main():
    print("=" * 62)
    print("ПРИВЕТСТВИЕ: коротко, строка уровня заменяется")
    print("=" * 62)
    test_greeting_text()
    test_update_message()
    test_app_after_level_test()

    print("\n" + "=" * 62)
    if FAILED:
        print("ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("   • " + name)
        return 1
    print("ВСЁ ЗЕЛЁНОЕ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
