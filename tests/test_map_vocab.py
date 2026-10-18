# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_MAP_VOCAB.PY — «📚 Повторить слова» в окне блока
# =========================================================
#   python tests\test_map_vocab.py   (нужно окно Windows, модель не нужна)
#
# Что проверяем:
#   1) метка VOCAB_RESULT не путается с id уроков учебного плана;
#   2) окно блока: кнопка «Повторить слова» возвращает метку, «Закрыть» — None,
#      «▶ Начать» по-прежнему возвращает id урока;
#   3) объяснение «почему повторять нечего» (app._vocab_empty_note);
#   4) VocabularyController собирает заход НЕЗАВИСИМО от даты последнего
#      захода: правило «не чаще раза в день» живёт только в автозапуске;
#   5) окно с карты открывается даже когда сегодня уже повторяли;
#   6) заход с карты НЕ взводит автозапуск урока;
#   7) пустой заход показывает «Повторять нечего», а не висит пустым окном;
#   8) клик по точке карты открывает повторение, а не урок (ветвление
#      on_point_click).
# =========================================================

import json
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

import profile_store                                        # noqa: E402
import user_manager                                         # noqa: E402
from progress_map import ProgressMap                         # noqa: E402
from ui.panels.block_panel import (BlockPanel, VOCAB_RESULT,
                                   VOCAB_TEXT, lesson_items)  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


# =========================================================
# 1. Метка кнопки
# =========================================================
def test_marker():
    print("\n[1] Метка «повторения» не путается с уроками")
    pm = ProgressMap()
    lesson_ids = set(pm._lesson_order)
    check("в плане есть уроки", len(lesson_ids) > 0, len(lesson_ids))
    check("метка не совпадает ни с одним id урока",
          VOCAB_RESULT not in lesson_ids, VOCAB_RESULT)
    check("метка похожа на служебную (__…__)",
          VOCAB_RESULT.startswith("__") and VOCAB_RESULT.endswith("__"), VOCAB_RESULT)
    check("на кнопке написано «Повторить слова»", "Повторить слова" in VOCAB_TEXT,
          VOCAB_TEXT)
    check("у класса есть обработчик кнопки", hasattr(BlockPanel, "_pick_vocab"))


# =========================================================
# 2. Почему повторять нечего
# =========================================================
class temp_profile:
    """Временный файл прогресса: настоящий профиль ученика не трогаем."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_map_vocab_")
        self.real = profile_store.PROFILE_PATH
        profile_store.PROFILE_PATH = os.path.join(self.dir, "student_profile.json")
        profile_store.set_active_user(None)
        profile_store.ensure_profile()
        return profile_store.PROFILE_PATH

    def __exit__(self, *exc):
        profile_store.PROFILE_PATH = self.real


def test_empty_note():
    print("\n[2] Объяснение «повторять нечего»")
    from ui.app import EnglishTeacherApp
    note = EnglishTeacherApp._vocab_empty_note          # статический метод
    with temp_profile():
        check("пустой словарь → «В словаре пока пусто»",
              "пусто" in note(), note())
        profile_store.add_vocabulary("ключ", ["key \u2014 Open the door with this key."])
        check("есть слово на сегодня → объяснять нечего", note() == "", note())
        path = profile_store.PROFILE_PATH
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        raw["vocabulary"][0]["next_due"] = "2030-01-01"     # ещё рано
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, ensure_ascii=False)
        check("слова есть, но не созрели → «Сегодня повторять нечего»",
              "Сегодня повторять нечего" in note(), note())


# =========================================================
# 3. Заход собирается независимо от даты
# =========================================================
def test_controller_ignores_day():
    print("\n[3] Сборка захода не зависит от «сегодня уже было»")
    from controllers.vocabulary_controller import VocabularyController

    class Store:
        def __init__(self, cards):
            self.cards = cards
            self.marks = 0

        def vocabulary_cards(self, user_id=None):
            return self.cards

        def mark_vocab_session(self, day=None, user_id=None):
            self.marks += 1
            return "2026-10-18"

        def update_vocabulary_card(self, word, en, success, user_id=None):
            return None

    with temp_profile():
        profile_store.add_vocabulary("ключ", ["key \u2014 Open the door with this key."])
        profile_store.mark_vocab_session()          # «сегодня уже повторяли»
        cards = profile_store.vocabulary_cards()
        ctrl = VocabularyController(store=Store(cards))
        queue = ctrl.start()
        check("слова всё равно собраны", len(queue) == 1 and ctrl.is_active, queue)
        check("карточка та самая", ctrl.current()["en"] == "key", ctrl.current())


# =========================================================
# 4-7. Окно: кнопка, пустой заход, автозапуск
# =========================================================
def _build_app(tmp):
    """Приложение на временных профилях, модальные окна заглушены."""
    import stt_engine
    import tts
    from ui import first_run
    from ui.panels import boot_panel, level_test_panel

    tts.speak = lambda *a, **k: True
    stt_engine.STTEngine.preload = lambda self: None
    boot_panel.BootPanel.ask = staticmethod(lambda *a, **k: None)
    level_test_panel.LevelTestPanel.ask = staticmethod(lambda *a, **k: None)
    first_run.FirstRunForm.ask = staticmethod(lambda *a, **k: None)

    user_manager.PROFILES_DIR = tmp
    user_manager.LAST_USER_FILE = os.path.join(tmp, "last_user.txt")
    user = user_manager.create_user("Тест", "other", 20, "A1", "учёба", "🙂",
                                    complete=True)
    user_manager.set_last_user(user["id"])
    profile_store.set_active_user(user["id"])
    profile_store.ensure_profile(user["id"])

    from ui.app import EnglishTeacherApp
    app = EnglishTeacherApp()
    # автозаход повторения при старте не нужен: тест открывает окно сам
    app.maybe_review_vocabulary = lambda: None
    app._arm_auto_lesson = lambda: False
    for _ in range(30):
        app.window.update()
        time.sleep(0.02)
    return app


def test_window():
    print("\n[4] Кнопки окна блока")
    tmp = tempfile.mkdtemp(prefix="et_map_vocab_app_")
    real_dirs = (user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE,
                 profile_store.PROFILE_PATH)
    app = None
    try:
        app = _build_app(tmp)

        point = ProgressMap().points_of("desert")[0]
        panel = BlockPanel(app.window, app.palette, point, "Пустыня")
        for _ in range(20):
            app.window.update()
            time.sleep(0.02)
        texts = []

        def walk(widget):
            try:
                for child in widget.winfo_children():
                    try:
                        value = child.cget("text")
                    except Exception:
                        value = ""
                    if value:
                        texts.append(str(value))
                    walk(child)
            except Exception:
                pass

        walk(panel)
        check("в окне блока есть кнопка «Повторить слова»",
              any("Повторить слова" in t for t in texts), texts[:12])
        check("кнопка «▶  Начать» осталась",
              any("Начать" in t for t in texts), texts[:12])

        panel._pick_vocab()
        app.window.update()
        check("кнопка вернула метку повторения", panel.result == VOCAB_RESULT,
              panel.result)
        check("окно закрылось", not panel.winfo_exists())

        panel2 = BlockPanel(app.window, app.palette, point, "Пустыня")
        for _ in range(20):
            app.window.update()
            time.sleep(0.02)
        first_lesson = lesson_items(point)[0]["id"]
        panel2._pick(first_lesson)
        app.window.update()
        check("«Начать» по-прежнему возвращает id урока",
              panel2.result == first_lesson, panel2.result)

        print("\n[5] Окно повторения с карты")
        profile_store.add_vocabulary("ключ", ["key \u2014 Open the door with this key."],
                                    (app.current_user or {}).get("id"))
        profile_store.mark_vocab_session(user_id=(app.current_user or {}).get("id"))
        app.vocab = type(app.vocab)(user_id=(app.current_user or {}).get("id"))
        armed = []
        app._arm_auto_lesson = lambda: (armed.append(1), False)[1]

        panel3 = app.review_vocabulary()
        for _ in range(10):
            app.window.update()
        check("окно открылось, хотя сегодня уже повторяли", panel3 is not None)
        check("в заходе есть слово", app.vocab.total == 1, app.vocab.total)
        check("окно ещё не закрыто", panel3 is not None and panel3.is_open)

        panel3.accept_text("key")
        app.window.update()
        check("ответ принят окном (вердикт «Похоже»)",
              "Похоже" in panel3.verdict_lbl.cget("text"),
              panel3.verdict_lbl.cget("text"))

        panel3._close()
        for _ in range(10):
            app.window.update()
        check("окно закрылось и забыто", app.vocab_panel is None)
        check("заход с карты НЕ взвёл автозапуск урока", not armed, armed)

        print("\n[6] Пустой заход: «Повторять нечего»")
        from controllers.vocabulary_controller import VocabularyController
        app.vocab = VocabularyController(user_id=(app.current_user or {}).get("id"),
                                         cards=[])
        panel4 = app.review_vocabulary()
        for _ in range(10):
            app.window.update()
        check("пустое окно всё равно открылось", panel4 is not None)
        check("окно сразу показывает итог", panel4 is not None and panel4.finished)
        check("написано «Повторять нечего»",
              "Повторять нечего" in panel4.counter_lbl.cget("text"),
              panel4.counter_lbl.cget("text"))
        check("кнопка записи выключена", panel4.record_btn.cget("state") == "disabled",
              panel4.record_btn.cget("state"))
        check("кнопка закрытия называется «Понятно»",
              panel4.next_btn.cget("text") == "Понятно", panel4.next_btn.cget("text"))
        panel4._close()
        for _ in range(10):
            app.window.update()

        print("\n[7] Клик по точке карты: повторение вместо урока")
        started = []
        app.start_lesson = lambda lid, pid=None, **kw: started.append(lid)
        BlockPanel.ask = staticmethod(lambda *a, **k: VOCAB_RESULT)
        app.on_point_click(str(point.get("id")))
        for _ in range(10):
            app.window.update()
        check("клик по точке открыл повторение", app.vocab_panel is not None,
              app.vocab_panel)
        check("урок не начался", not started, started)
        if app.vocab_panel is not None:
            app.vocab_panel._close()
            for _ in range(10):
                app.window.update()

        BlockPanel.ask = staticmethod(lambda *a, **k: "1.1")
        app.on_point_click(str(point.get("id")))
        check("обычный урок с карты по-прежнему стартует", started == ["1.1"], started)
    finally:
        try:
            if app is not None:
                app.on_closing()
        except Exception:
            pass
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE,             profile_store.PROFILE_PATH = real_dirs
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=" * 60)
    print("Проверка «📚 Повторить слова» в окне блока")
    print("=" * 60)
    test_marker()
    test_empty_note()
    test_controller_ignores_day()
    test_window()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
