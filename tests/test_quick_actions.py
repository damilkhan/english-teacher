# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_QUICK_ACTIONS.PY — три кнопки на старте чата
# =========================================================
#   python tests\test_quick_actions.py   (нужно окно Windows, модель не нужна)
#
# Решение ученика 27.10.2026: при запуске в чате висят кнопки
#   «🎓 Провести урок»  «📚 Слова»  «💬 Свободное общение»
# и пропадают, как только ученик что-то сделал сам.
#
# Что проверяем:
#   1) кнопки есть в окне и подписаны как договорились;
#   2) «Слова» и «Прогресс/Карта» лишнего не обещают (кнопок прогресса нет);
#   3) «Свободное общение» гасит автозапуск урока и говорит по-английски;
#   4) «Провести урок» начинает СЛЕДУЮЩИЙ урок по карте;
#   5) первое действие ученика убирает кнопки, «Очистить» возвращает;
#   6) «Слова» без материала НЕ открывает пустое окно (фраза голосом).
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

import config                                               # noqa: E402
import profile_store                                        # noqa: E402
import user_manager                                         # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def build_app(tmp):
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
    app.maybe_review_vocabulary = lambda: None
    app._arm_auto_lesson = lambda: False
    for _ in range(30):
        app.window.update()
        time.sleep(0.02)
    return app


def all_texts(widget, out=None):
    """Собрать все подписи виджетов (кнопки, метки)."""
    out = [] if out is None else out
    try:
        for child in widget.winfo_children():
            try:
                value = child.cget("text")
            except Exception:
                value = ""
            if value:
                out.append(str(value))
            all_texts(child, out)
    except Exception:
        pass
    return out


def main():
    print("=" * 60)
    print("Стартовые кнопки в чате")
    print("=" * 60)

    tmp = tempfile.mkdtemp(prefix="et_quick_")
    real_dirs = (user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE,
                 profile_store.PROFILE_PATH)
    saved_new = config.VOCAB_NEW_PER_DAY
    saved_demand = config.VOCAB_ON_DEMAND_NEW
    config.VOCAB_NEW_PER_DAY = 0
    config.VOCAB_ON_DEMAND_NEW = 0
    app = None
    try:
        app = build_app(tmp)
        print("\n[1] Кнопки есть и подписаны")
        texts = all_texts(app.quick_row)
        check("ряд кнопок создан", app.quick_row is not None)
        check("«Провести урок» есть",
              any("Провести урок" in t for t in texts), texts)
        check("«Слова» есть", any(t.strip().endswith("Слова") for t in texts), texts)
        check("«Свободное общение» есть",
              any("Свободное общение" in t for t in texts), texts)
        # подпись CTkButton живёт дважды (кнопка + её внутренняя метка)
        check("кнопок ровно три", len(set(texts)) == 3, sorted(set(texts)))
        check("ряда нет на вкладках «Карта»/«Профиль»",
              app.quick_row.master is app.chat_tab, app.quick_row.master)

        print("\n[2] Лишних кнопок не обещаем")
        check("кнопки «Мой прогресс» нет",
              not any("прогресс" in t.lower() for t in all_texts(app)), [
                  t for t in all_texts(app) if "рогресс" in t])

        print("\n[3] Видны на старте")
        check("ряд на экране", bool(app.quick_row.winfo_manager()),
              app.quick_row.winfo_manager())

        print("\n[4] «Свободное общение»: урок НЕ начинается")
        started = []
        real_start = app.start_lesson
        app.start_lesson = lambda *a, **k: started.append((a, k))
        app._auto_lesson_armed = True
        said = []
        app._say = lambda text, **_kw: said.append(text) or True
        app._quick_talk()
        for _ in range(10):
            app.window.update()
        check("урок не начался", started == [], started)
        check("автозапуск погашен", app._auto_lesson_armed is False,
              app._auto_lesson_armed)
        check("бот ответил по-английски",
              bool(said) and not any("\u0400" <= ch <= "\u04ff" for ch in said[0]),
              said)
        check("кнопки убрались", not app.quick_row.winfo_manager(),
              app.quick_row.winfo_manager())

        print("\n[5] «Очистить» возвращает кнопки")
        app.clear_chat()
        for _ in range(10):
            app.window.update()
        check("ряд вернулся", bool(app.quick_row.winfo_manager()),
              app.quick_row.winfo_manager())
        check("чат снова с приветствием", len(app.chat_view.get_text()) > 0)

        print("\n[6] «Провести урок» начинает следующий урок по карте")
        started = []
        app.start_lesson = lambda lid, *a, **k: started.append(lid)
        app._auto_lesson_armed = True
        app._quick_lesson()
        for _ in range(10):
            app.window.update()
        expect = app.progress_map.next_lesson(app._active_profile())
        check("урок выбран по карте", started == [expect], (started, expect))
        check("автозапуск больше не ждёт реплики", app._auto_lesson_armed is False)
        check("кнопки убрались", not app.quick_row.winfo_manager())

        print("\n[7] «Слова» без материала: окна НЕТ, фраза голосом")
        import vocab_lines
        from controllers.vocabulary_controller import VocabularyController
        app.start_lesson = real_start
        app._show_quick()
        app.vocab = VocabularyController(user_id=(app.current_user or {}).get("id"),
                                         cards=[])
        said = []
        app._say = lambda text, **_kw: said.append(text) or True
        app._quick_words()
        for _ in range(10):
            app.window.update()
        check("окно слов не открылось", app.vocab_panel is None, app.vocab_panel)
        check("фраза из EMPTY_LINES",
              len(said) == 1 and said[0] in vocab_lines.EMPTY_LINES, said)

        print("\n[8] Ученик начал писать сам — кнопки ушли")
        app._show_quick()
        app.input_bar.set_text("hello")
        app.send_text = app.send_text          # настоящий метод
        app.send_text()
        for _ in range(10):
            app.window.update()
        check("после своей реплики ряда нет", not app.quick_row.winfo_manager(),
              app.quick_row.winfo_manager())
    finally:
        try:
            if app is not None:
                app.on_closing()
        except Exception:
            pass
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE, \
            profile_store.PROFILE_PATH = real_dirs
        config.VOCAB_NEW_PER_DAY = saved_new
        config.VOCAB_ON_DEMAND_NEW = saved_demand
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
