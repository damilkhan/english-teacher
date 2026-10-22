# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_USER_RECREATE.PY — профиль создаётся заново
# =========================================================
#   python tests\test_user_recreate.py     (нужно окно Windows)
#
# Регрессия (найдена пользователем 22.10.2026): ученик удалил профиль и
# создал новый с ТЕМ ЖЕ именем. Профиль не сохранялся: панель показывала
# «Профилей: 0 / 8», в шапке висел уровень УДАЛЁННОГО ученика (A2), тест
# уровня не запускался.
#
# Причина: ui/app._form_profile отдаёт поле name_latin, а
# user_manager.create_user такого параметра НЕ принимал — вызов
# create_user(**форма) падал с TypeError. Тот же TypeError убивал и
# кнопку «+ Добавить пользователя» (она тоже создаёт профиль).
#
# Вторая причина (тише): после удаления новый профиль занимает
# ОСВОБОДИВШИЙСЯ слот и получает тот же id. select_user сравнивал только id
# и молча выходил — в памяти оставался удалённый ученик.
#
# Проверяем:
#   1) все поля формы принимаются create_user (та самая поломка);
#   2) латинское имя сохраняется;
#   3) живое окно: удалили последний профиль → создан новый, уровень НЕ
#      унаследован, тест уровня запрошен;
#   4) живое окно: «+ Добавить пользователя» реально создаёт профиль;
#   5) select_user(force=True) перечитывает профиль с тем же id.
# =========================================================

import inspect
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


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class TempProfiles:
    """Временная папка профилей (личные файлы ученика не трогаем)."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_recreate_")
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
# 1. Форма и create_user говорят на одном языке
# =========================================================
def test_form_fields_accepted():
    print("\n[1] Поля формы принимаются create_user (та самая поломка)")
    from ui.app import EnglishTeacherApp

    form_keys = set(EnglishTeacherApp._form_profile({
        "name": "Дамиль", "name_latin": "Damil", "gender": "male",
        "age": "14", "goal": "цель", "avatar": "🦊"}))
    accepted = set(inspect.signature(user_manager.create_user).parameters)
    missing = sorted(form_keys - accepted)
    check("у create_user есть параметры для всех полей формы",
          not missing, "нет параметров: %s" % missing)
    check("name_latin среди полей формы", "name_latin" in form_keys, sorted(form_keys))

    with TempProfiles():
        created = user_manager.create_user(
            name="Дамиль", name_latin="Damil", gender="male", age="14",
            goal="говорить", avatar="🦊", complete=True)
        check("create_user(**все поля формы) создаёт профиль", created is not None,
              created)
        if created:
            stored = user_manager.get_user(created["id"])
            check("профиль лёг на диск", stored is not None, created["id"])
            check("латинское имя сохранено", stored.get("name_latin") == "Damil",
                  stored.get("name_latin"))
            check("кириллическое имя сохранено", stored.get("name") == "Дамиль",
                  stored.get("name"))
            check("уровень НЕ выдуман", stored.get("level") is None,
                  stored.get("level"))
            check("профиль помечен полным", user_manager.is_complete(stored),
                  stored.get("complete"))


# =========================================================
# 2. Без латинского имени работает транслитерация
# =========================================================
def test_name_latin_optional():
    print("\n[2] Латинское имя необязательно")
    with TempProfiles():
        created = user_manager.create_user("Дамиль", "male", 14)
        check("старый вызов без name_latin работает", created is not None, created)
        if created:
            stored = user_manager.get_user(created["id"])
            check("латиница получена транслитерацией",
                  stored.get("name_latin") == "Damil", stored.get("name_latin"))
        # позиционные аргументы не должны сломаться (параметр добавлен ПОСЛЕДНИМ)
        second = user_manager.create_user("Ученик", "other", None, None, "",
                                          "🙂", complete=False)
        check("позиционный вызов из delete_user работает", second is not None, second)


# =========================================================
# 3-5. Живое окно
# =========================================================
def _build_app(tmp_dir, form_answer, level_answer="A2"):
    """Настоящее окно приложения на временной папке профилей.

    Модальные окна подменяем (как в остальных тестах проекта): форма
    профиля сразу «отвечает», тест уровня, загрузка и окно блока — молчат.
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
    level_test_panel.LevelTestPanel.ask = staticmethod(lambda *a, **k: level_answer)
    boot_panel.BootPanel.ask = staticmethod(lambda *a, **k: None)
    block_panel.BlockPanel.ask = staticmethod(lambda *a, **k: None)

    import profile_store
    real_store_path = profile_store.PROFILE_PATH
    profile_store.PROFILE_PATH = os.path.join(tmp_dir, "user_profile.json")

    from ui.app import EnglishTeacherApp
    app = EnglishTeacherApp()
    app.maybe_review_vocabulary = lambda: None
    app._arm_auto_lesson = lambda: False

    calls = []
    real_run = app.run_level_test

    def spy_run_level_test(user_id):
        calls.append(user_id)
        return real_run(user_id)

    app.run_level_test = spy_run_level_test
    for _ in range(40):
        app.window.update()
        time.sleep(0.02)
    return app, calls, real_store_path, profile_store


def test_gui_recreate():
    print("\n[3] Живое окно: удалили профиль → создали новый с тем же именем")
    answer = {"name": "Дамиль", "name_latin": "Damil", "gender": "male",
              "age": "14", "goal": "говорить", "avatar": "🦊"}
    with TempProfiles() as tmp:
        first = user_manager.create_user(**answer, complete=True)
        user_manager.update_user(first["id"], {"level": "A2"})
        check("стартовый профиль с уровнем A2",
              (user_manager.get_user(first["id"]) or {}).get("level") == "A2",
              first["id"])

        app, calls, real_store, store_mod = _build_app(tmp, answer)
        try:
            check("окно подхватило профиль",
                  app.current_user["id"] == first["id"], app.current_user)
            check("в шапке уровень старого профиля",
                  "A2" in app._hero_subtitle(), app._hero_subtitle())

            app.delete_user(first["id"])
            for _ in range(60):
                app.window.update()
                time.sleep(0.02)

            users = user_manager.list_users()
            check("профиль создан заново и ЛЕЖИТ НА ДИСКЕ", len(users) == 1, users)
            if not users:
                return
            fresh = users[0]
            check("имя сохранено", fresh.get("name") == "Дамиль", fresh.get("name"))
            check("уровень удалённого профиля НЕ унаследован",
                  fresh.get("level") is None, fresh.get("level"))
            check("у активного профиля в памяти уровень сброшен",
                  app.current_user.get("level") is None,
                  app.current_user.get("level"))
            check("в шапке «не определён», а не старый A2",
                  "A2" not in app._hero_subtitle()
                  and "не определён" in app._hero_subtitle(),
                  app._hero_subtitle())
            check("тест уровня запрошен для нового профиля",
                  fresh["id"] in calls, calls)
            check("панель показывает 1 профиль",
                  "1 /" in app.users_panel.count_label.cget("text"),
                  app.users_panel.count_label.cget("text"))
            check("активный профиль в памяти = профиль на диске",
                  app.current_user["id"] == fresh["id"]
                  and app.current_user.get("name") == fresh.get("name"),
                  (app.current_user.get("id"), fresh.get("id")))
            check("прогресс нового профиля создан",
                  os.path.exists(user_manager.progress_path(fresh["id"])),
                  user_manager.progress_path(fresh["id"]))
        finally:
            store_mod.PROFILE_PATH = real_store
            try:
                app.window.destroy()
            except Exception:
                pass


def test_gui_add_user():
    print("\n[4] Живое окно: «+ Добавить пользователя» создаёт профиль")
    answer = {"name": "Аня", "name_latin": "Anya", "gender": "female",
              "age": "12", "goal": "", "avatar": "🐼"}
    with TempProfiles() as tmp:
        first = user_manager.create_user("Дамиль", "male", 14, complete=True)
        app, calls, real_store, store_mod = _build_app(tmp, answer)
        try:
            app.add_user()
            for _ in range(60):
                app.window.update()
                time.sleep(0.02)

            users = user_manager.list_users()
            names = [u.get("name") for u in users]
            check("профилей стало два", len(users) == 2, names)
            check("новый профиль сохранён", "Аня" in names, names)
            if "Аня" in names:
                new_user = [u for u in users if u.get("name") == "Аня"][0]
                check("новый профиль стал активным",
                      app.current_user["id"] != first["id"]
                      and app.current_user.get("name") == "Аня",
                      app.current_user)
                check("тест уровня запрошен для нового профиля",
                      new_user["id"] in calls, calls)
                check("латинское имя нового профиля сохранено",
                      new_user.get("name_latin") == "Anya",
                      new_user.get("name_latin"))
        finally:
            store_mod.PROFILE_PATH = real_store
            try:
                app.window.destroy()
            except Exception:
                pass


def test_select_user_force():
    print("\n[5] select_user(force=True) перечитывает профиль с тем же id")
    answer = {"name": "Дамиль", "name_latin": "Damil", "gender": "male",
              "age": "14", "goal": "", "avatar": "🦊"}
    with TempProfiles() as tmp:
        first = user_manager.create_user(**answer, complete=True)
        user_manager.update_user(first["id"], {"level": "A2"})
        app, _calls, real_store, store_mod = _build_app(tmp, answer)
        try:
            same_id = app.current_user["id"]
            user_manager.update_user(same_id, {"level": None, "goal": "новая цель"})

            app.select_user(same_id, force=True)     # тот же id — но данные новые
            for _ in range(20):
                app.window.update()
                time.sleep(0.02)
            check("уровень перечитан (A2 → не определён)",
                  app.current_user.get("level") is None,
                  app.current_user.get("level"))
            check("цель перечитана", app.current_user.get("goal") == "новая цель",
                  app.current_user.get("goal"))

            app.current_user["goal"] = "локальная правка"
            app.select_user(same_id)                 # без force — выходим сразу
            check("без force профиль не перечитывается (как раньше)",
                  app.current_user.get("goal") == "локальная правка",
                  app.current_user.get("goal"))
        finally:
            store_mod.PROFILE_PATH = real_store
            try:
                app.window.destroy()
            except Exception:
                pass


def main():
    print("=" * 62)
    print("ПРОФИЛЬ: удалили и создали заново с тем же именем")
    print("=" * 62)
    test_form_fields_accepted()
    test_name_latin_optional()
    test_gui_recreate()
    test_gui_add_user()
    test_select_user_force()

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
