# -*- coding: utf-8 -*-
# =========================================================
# TESTS/SMOKE_TEST.PY — проверка после рефакторинга
# =========================================================
#   python tests\smoke_test.py          — только быстрые проверки (без окна)
#   python tests\smoke_test.py --gui    — + создание окна и живой диалог
#
# Что проверяем:
#   1) база промпта та же, КРОМЕ строки языка: сверяем с gui.py из git;
#   2) чистка тегов Gemma (clean_response);
#   3) profile_store: создание/чтение/запись во временной папке;
#   4) окно собирается, тема и режим переключаются (--gui);
#   5) реальный диалог с llama-server (--gui).
# =========================================================

import os
import subprocess
import sys
import tempfile
import textwrap
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# консоль Windows по умолчанию cp1251 — без этого тест падает на эмодзи
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import prompt_builder          # noqa: E402
import profile_store           # noqa: E402
import user_manager          # noqa: E402

FAILED = []

# Коммит, где gui.py ещё был монолитом. Нужен, чтобы проверять «промпт не
# изменился» вечно: HEAD уже указывает на фасад, а не на старую версию.
OLD_GUI_REF = "b62c09a"


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def norm(text):
    """Единственное допустимое отличие — переводы строк (\r\n vs \n)."""
    return (text or "").replace("\r\n", "\n")


# Единственная НАМЕРЕННАЯ правка базового промпта: жёсткое приказание языка
# заменено мягкой политикой (язык выбирает модель). Всё остальное в базовом
# промпте обязано совпасть с историческим gui.py байт-в-байт.
OLD_LANGUAGE_LINES = {
    "ru": "Ответь на русском языке, кратко.",
    "en": "Answer in English, keep responses short.",
}


def _expected_system(old_prompt, lang):
    """Старый системный промпт с ЗАМЕНЁННОЙ строкой языка (остальное — как было)."""
    return old_prompt.replace(OLD_LANGUAGE_LINES[lang], prompt_builder.LANGUAGE_POLICY, 1)


# =========================================================
# 1. Промпт: старое из git vs новое из prompt_builder
# =========================================================
def _old_gui_source():
    """Старый монолитный gui.py из истории git (НЕ из HEAD — там уже фасад)."""
    for ref in (OLD_GUI_REF, "HEAD"):
        try:
            out = subprocess.run(["git", "show", f"{ref}:gui.py"], cwd=ROOT,
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
            if out.returncode == 0 and "def get_dynamic_prompt" in (out.stdout or ""):
                print(f"  (сверяемся с {ref}:gui.py — {len(out.stdout.splitlines())} строк)")
                return out.stdout
        except Exception as exc:
            print(f"  (git {ref} недоступен: {exc})")
    return None


def _extract_method(src, name):
    start = src.index(f"    def {name}(self")
    end = src.index("\n    def ", start + 10)
    return textwrap.indent(textwrap.dedent(src[start:end]), "    ")


def _make_fake_app(src, profile, mode, lang, history):
    """Собирает объект со СТАРЫМИ методами get_dynamic_prompt и ask_jane из gui.py."""
    class FakeResponse:
        status_code = 200
        def json(self):
            return {"content": "Тестовый ответ"}

    class FakeHttp:
        def __init__(self):
            self.payload = None
        def post(self, url, json=None, timeout=None):
            self.payload = json
            return FakeResponse()

    body = _extract_method(src, "get_dynamic_prompt") + "\n" + _extract_method(src, "ask_jane")
    ns = {}
    exec("import re\nimport json\nclass FakeApp:\n" + body, ns)

    app = ns["FakeApp"]()
    app.mode = mode
    app.current_lang = lang
    app.conversation_history = list(history)
    app.llm_url = "http://test"
    app._http = FakeHttp()
    app.get_student_profile = lambda: profile
    return app


def test_prompt_unchanged():
    print("\n[1] Промпт: база та же, КРОМЕ строки языка (сверка с gui.py из git)")
    src = _old_gui_source()
    if not src:
        print("  ⚠️ пропущено: не нашёл монолитный gui.py в истории git")
        print(f"     (ожидался коммит {OLD_GUI_REF}; проверьте: git log --oneline)")
        return

    profiles = [
        {"mistakes": {"grammar": [], "vocabulary": []}, "strengths": [], "topics_passed": [], "total_lessons": 0},
        {
            "mistakes": {"grammar": [{"jane_response": "You should use Past Simple here"}],
                         "vocabulary": [{"jane_response": "Wrong spelling of 'though'"}]},
            "strengths": [{"jane_response": "Good job with the article!"}],
            "topics_passed": ["Present Simple", "Travel"],
            "total_lessons": 7,
        },
    ]
    cases = [("lesson", "ru", []), ("lesson", "en", []), ("free", "ru", []), ("free", "en", [])]

    # Системный промпт: единственная намеренная правка — политика языка.
    for pi, profile in enumerate(profiles):
        for mode, lang, _ in cases:
            fake = _make_fake_app(src, profile, mode, lang, [])
            old_prompt = _expected_system(fake.get_dynamic_prompt(), lang)
            new_prompt = prompt_builder.build_system_prompt(mode, profile, lang)
            check(f"system-промпт mode={mode} lang={lang} профиль#{pi} (кроме строки языка)",
                  norm(old_prompt) == norm(new_prompt),
                  f"было {len(old_prompt)} симв., стало {len(new_prompt)}")

    sys_ru = prompt_builder.build_system_prompt("lesson", profiles[0], "ru")
    sys_en = prompt_builder.build_system_prompt("lesson", profiles[0], "en")
    check("мягкая политика языка на месте (ru и en)",
          prompt_builder.LANGUAGE_POLICY in sys_ru and prompt_builder.LANGUAGE_POLICY in sys_en)
    check("жёсткого приказа языка больше нет",
          "ТОЛЬКО НА РУССКОМ" not in sys_ru and "Answer ONLY in English" not in sys_en)

    # Полный промпт: история — НАСТОЯЩИМИ тёрнами Gemma, реплика ученика — как есть.
    history = ["Student: hello", "Assistant: hi there"]
    for mode, lang in [("lesson", "ru"), ("lesson", "en"), ("free", "en")]:
        profile = profiles[1]
        system = prompt_builder.build_system_prompt(mode, profile, lang)
        full = prompt_builder.build_conversation_prompt(system, history, "How are you?", lang)
        check(f"полный промпт {mode}/{lang}: system-тёрн в начале",
              full.startswith("<start_of_turn>system\n" + system + "<end_of_turn>\n"), full[:60])
        check(f"полный промпт {mode}/{lang}: история — user-тёрн",
              "<start_of_turn>user\nhello<end_of_turn>\n" in full, full)
        check(f"полный промпт {mode}/{lang}: история — model-тёрн",
              "<start_of_turn>model\nhi there<end_of_turn>\n" in full, full)
        check(f"полный промпт {mode}/{lang}: реплика ученика как есть",
              full.endswith("<start_of_turn>user\nHow are you?<end_of_turn>\n<start_of_turn>model\n"), full[-70:])
        check(f"полный промпт {mode}/{lang}: нет жёсткого приказа языка",
              "Answer ONLY in English" not in full and "ТОЛЬКО НА РУССКОМ" not in full, full)
        check(f"полный промпт {mode}/{lang}: «сырых» строк Student:/Assistant: нет",
              "Student: hello" not in full and "Assistant: hi there" not in full, full)

    # «слабые темы» из теста уровня: блок появляется ТОЛЬКО когда данные есть
    # (иначе вывод промпта обязан остаться байт-в-байт прежним — см. выше)
    base = {"mistakes": {}, "strengths": [], "topics_passed": [], "total_lessons": 0}
    with_weak = dict(base, weak_topics=[{"topic": "travel and transport",
                                         "correct": 0, "total": 3}])
    p_with = prompt_builder.build_system_prompt("lesson", with_weak, "en")
    p_without = prompt_builder.build_system_prompt("lesson", base, "en")
    check("слабые темы добавляются в промпт",
          "WEAK TOPICS" in p_with and "travel and transport" in p_with)
    check("без слабых тем промпт не меняется", "WEAK TOPICS" not in p_without)


def test_clean_response():
    print("\n[2] Чистка ответа модели")
    cases = [
        ("Привет!<end_of_turn>", "Привет!"),
        ("<|thought|>размышляю\nОтвет", "Ответ"),
        ("Текст <|channel|> ещё", "Текст  ещё"),
        ("ГотовоRU", "Готово"),
        ("Ответ **жирный** тут", "Ответ жирный тут"),
        ("Готово <end_turn>", "Готово"),
        ("  пробелы  ", "пробелы"),
        ("", ""),
        (None, ""),
    ]
    for raw, expected in cases:
        got = prompt_builder.clean_response(raw)
        check(f"clean_response({raw!r})", got == expected, f"получено {got!r}, ждали {expected!r}")

    check("detect_language: русский", prompt_builder.detect_language("привет") == "ru")
    check("detect_language: английский", prompt_builder.detect_language("hello") == "en")


# =========================================================
# 3. profile_store
# =========================================================
def test_profile_store():
    print("\n[3] profile_store во временной папке")
    real_path = profile_store.PROFILE_PATH
    tmp = tempfile.mkdtemp(prefix="et_profile_")
    try:
        profile_store.PROFILE_PATH = os.path.join(tmp, "student_profile.json")

        profile, created = profile_store.ensure_profile()
        check("ensure_profile создаёт файл", created and os.path.exists(profile_store.PROFILE_PATH))
        check("структура по умолчанию", "mistakes" in profile and profile["total_lessons"] == 0)

        profile, created = profile_store.ensure_profile()
        check("повторный вызов не пересоздаёт", created is False)

        notes = profile_store.record_from_dialogue(
            "I go to school yesterday",
            "Небольшая ошибка: нужен Past Simple — I went to school yesterday.")
        check("ошибка записана (grammar)", "grammar" in notes[0], notes)
        saved = profile_store.load()
        check("ошибка в файле", len(saved["mistakes"]["grammar"]) == 1)
        check("total_lessons увеличен", saved["total_lessons"] == 1)
        check("last_lesson проставлен", bool(saved["last_lesson"]))

        notes = profile_store.record_from_dialogue(
            "I have been learning English for five years",
            "Excellent! Your Present Perfect is correct, well done!")
        saved = profile_store.load()
        check("похвала записана в strengths", len(saved["strengths"]) == 1)
        check("без ошибок нет заметки", notes == [], notes)

        with open(profile_store.PROFILE_PATH, "w", encoding="utf-8") as fh:
            fh.write("{ битый json")
        check("битый файл не роняет загрузку", isinstance(profile_store.load(), dict))
    finally:
        profile_store.PROFILE_PATH = real_path


# =========================================================
# 4. Команды смены режима (перенесены из консольной версии)
# =========================================================
def test_commands():
    print("\n[4] Команды смены режима")
    import commands

    cases = [
        ("урок", "lesson"), ("Урок!", "lesson"), ("заниматься", "lesson"), ("учитель", "lesson"),
        ("перерыв", "free"), ("Перерыв.", "free"), ("отдохнем", "free"), ("друг", "free"),
        ("привет, друг!", "None"), ("давай перерыв на десять минут", "None"),
        ("", "None"), (None, "None"),
    ]
    for text, expected in cases:
        got = commands.parse_mode_command(text)
        check(f"команда {text!r} → {expected}", str(got) == expected, got)

    check("приветствие для урока есть", bool(commands.GREETINGS.get("lesson")))
    check("приветствие для свободного режима есть", bool(commands.GREETINGS.get("free")))


# =========================================================
# 5-6. GUI и живой диалог
# =========================================================
def test_gui(e2e=False):
    print("\n[5] Сборка окна и переключение темы/режима")
    import tts
    tts.speak = lambda *a, **k: None          # без звука во время теста

    import gui
    import theme
    from ui.app import EnglishTeacherApp

    check("gui.EnglishTeacherApp — тот же класс из ui.app",
          gui.EnglishTeacherApp is EnglishTeacherApp)

    app = EnglishTeacherApp()
    for _ in range(30):
        app.window.update()
        time.sleep(0.02)

    check("чат создан и доступен", app.chat_view is not None)
    check("контроллеры созданы", app.chat is not None and app.recorder is not None)

    before = app.chat_view.get_text()
    app.add_message("Тест", "проверка вывода")
    for _ in range(10):
        app.window.update()
    check("add_message пишет в чат", "проверка вывода" in app.chat_view.get_text(),
          repr(app.chat_view.get_text()[-60:]))
    check("чат не пустой изначально", len(before.strip()) > 0, repr(before[:40]))

    app.open_panel()
    app.window.update()
    check("панель настроек открывается", app.panel_visible)
    app.right_panel.mode_var.set("free")
    app.right_panel.theme_var.set("light")
    app.save_settings()
    for _ in range(10):
        app.window.update()
    check("режим применён к контроллеру чата", app.chat.mode == "free", app.chat.mode)
    check("тема применена", app.palette["window"] == theme.LIGHT["window"], app.current_theme)
    check("панель закрылась", not app.panel_visible)
    check("сообщение о смене режима в чате",
          "Свободное общение" in app.chat_view.get_text())

    app.right_panel.theme_var.set("dark")
    app.save_settings()
    for _ in range(10):
        app.window.update()
    check("возврат к тёмной теме", app.palette["window"] == theme.DARK["window"])

    # --- раскладка: при минимальном размере окна ничего не обрезается ---
    # Регрессия: раньше чат запрашивал 24 строки текста, из-за чего суммарный
    # запрос детей превышал высоту карточки и последний упакованный виджет
    # (панель кнопок) уезжал за нижний край при ЛЮБОМ размере окна.
    for geo in ("920x620", "1160x760"):
        app.window.geometry(geo)
        for _ in range(30):
            app.window.update()
            time.sleep(0.02)
        card_h = app.left_frame.winfo_height()
        clipped = []
        for name, widget in (("шапка", app.hero), ("эквалайзер", app.visualizer),
                             ("чат", app.chat_view), ("поле ввода", app.input_bar),
                             ("панель кнопок", app.control_bar)):
            bottom = widget.winfo_y() + widget.winfo_height()
            if not (widget.winfo_ismapped() and widget.winfo_height() > 0 and bottom <= card_h + 1):
                clipped.append(f"{name} (низ {bottom} > {card_h})")
        check(f"при окне {geo} все элементы помещаются", not clipped, "; ".join(clipped))
        check(f"при окне {geo} чат не схлопнулся",
              app.chat_view.winfo_height() > 120, app.chat_view.winfo_height())

    # команда смены режима должна работать локально, без сервера
    app.input_bar.set_text("перерыв")
    app.input_bar.on_send()
    for _ in range(10):
        app.window.update()
    check("команда «перерыв» включает свободный режим", app.chat.mode == "free", app.chat.mode)

    app.input_bar.set_text("урок")
    app.input_bar.on_send()
    for _ in range(10):
        app.window.update()
    check("команда «урок» возвращает режим урока", app.chat.mode == "lesson", app.chat.mode)
    check("панель настроек показывает новый режим",
          app.right_panel.mode_var.get() == "lesson", app.right_panel.mode_var.get())

    if e2e:
        print("\n[6] Живой диалог с llama-server")
        state = app.check_server()
        check("сервер готов", state == "ready", state)
        if state == "ready":
            app.input_bar.set_text("Hello, my name is Damil.")
            app.input_bar.on_send()
            deadline = time.time() + 120
            while app.chat.busy and time.time() < deadline:
                app.window.update()
                time.sleep(0.05)
            for _ in range(40):
                app.window.update()
                time.sleep(0.02)
            text = app.chat_view.get_text()
            check("ответ Джейн появился", "Джейн" in text.split("Hello, my name is Damil.")[-1],
                  text[-200:])
            check("нет ошибки в ответе", "[Ошибка]" not in text, text[-200:])
            check("история диалога заполнена", len(app.chat.history) >= 2, app.chat.history)
            print("  --- последние 400 символов чата ---")
            print(textwrap.indent(text[-400:], "  | "))

    app.on_closing()

# =========================================================
# 4b. user_manager — многопользовательская система
# =========================================================
def test_users():
    print("\n[4b] user_manager во временной папке")
    real_dir, real_last = user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE
    tmp = tempfile.mkdtemp(prefix="et_users_")
    try:
        user_manager.PROFILES_DIR = tmp
        user_manager.LAST_USER_FILE = os.path.join(tmp, "last_user.txt")

        check("вначале пусто", user_manager.count() == 0 and user_manager.list_users() == [])

        u = user_manager.create_user("Аня", "female", 14, "A2", "Говорить свободно", "🦊")
        check("профиль создан (id=1)", bool(u) and u["id"] == 1 and u["name"] == "Аня")
        check("файл профиля на месте", os.path.exists(user_manager.identity_path(1)))
        check("get_last_user", user_manager.get_last_user()["id"] == 1)
        check("get_user", user_manager.get_user(1)["level"] == "A2")
        check("update_user меняет поле",
              user_manager.update_user(1, {"level": "B1"}) and user_manager.get_user(1)["level"] == "B1")
        check("update_user без уровня сохраняет его",
              user_manager.update_user(1, {"goal": "цель"}) and
              user_manager.get_user(1)["level"] == "B1")
        check("save_user сохраняет", user_manager.save_user(1, {"name": "Аня-2"})
              and user_manager.get_user(1)["name"] == "Аня-2")

        for i in range(2, 9):
            user_manager.create_user("U%d" % i)
        check("лимит 8 соблюдается", user_manager.count() == 8 and user_manager.is_full())
        check("профиль без теста → уровень не определён",
              user_manager.get_user(2)["level"] is None)
        check("level_label: известный уровень", user_manager.level_label("B1") == "B1")
        check("level_label: нет уровня",
              user_manager.level_label(None) == user_manager.LEVEL_UNKNOWN_TEXT)
        check("9-й профиль не создаётся", user_manager.create_user("X") is None)

        user_manager.set_last_user(3)
        check("delete_user удаляет", user_manager.delete_user(3) and user_manager.get_user(3) is None)
        check("активный переключён на живой", user_manager.get_last_user_id() != 3)

        # прогресс привязан к пользователю
        profile_store.set_active_user(1)
        prof, created = profile_store.ensure_profile(1)
        check("файл прогресса создан", created and os.path.exists(user_manager.progress_path(1)))
        profile_store.save(dict(prof), 1)
        check("прогресс сохранён у #1", profile_store.load(1).get("total_lessons", 0) >= 1)
        check("у другого ученика прогресс пуст",
              profile_store.load(5).get("total_lessons", 0) == 0)
        check("пути прогресса разные",
              user_manager.progress_path(1) != user_manager.progress_path(5))

        with open(user_manager.identity_path(6), "w", encoding="utf-8") as fh:
            fh.write("{ битый json")
        check("битый профиль не роняет список",
              all(x["id"] != 6 for x in user_manager.list_users()))
    finally:
        user_manager.PROFILES_DIR = real_dir
        user_manager.LAST_USER_FILE = real_last
        profile_store.set_active_user(None)


# =========================================================
# 4c. level_test — адаптивный тест уровня (без живой модели)
# =========================================================
def test_level_test():
    print("\n[4c] level_test: адаптивность и запись уровня")
    import level_test

    # Варианты ответа теперь ПЕРЕМЕШИВАЮТСЯ, поэтому «отвечать нулём» нельзя.
    # Тестовые помощники берут правильный индекс прямо из сессии.
    def correct_index(u):
        return level_test._SESSIONS[int(u)]["current"]["correct"]

    def wrong_index(u):
        return (correct_index(u) + 1) % 4

    class FakeLLM:
        def complete(self, prompt, max_tokens=None, temperature=None,
                     stop=None, timeout=None):
            return True, ('{"question": "Pick one?", "options": ["a","b","c","d"], '
                          '"correct": 0}')

    class DeadLLM:
        def complete(self, *a, **k):
            return False, "offline"

    real_dir, real_last = user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE
    tmp = tempfile.mkdtemp(prefix="et_level_")
    try:
        user_manager.PROFILES_DIR = tmp
        user_manager.LAST_USER_FILE = os.path.join(tmp, "last_user.txt")
        uid = user_manager.create_user("Тест", "other", None, "A1", "", "🙂")["id"]

        level_test.set_client(FakeLLM())
        q = level_test.start_test(uid)
        check("старт со сложности A2", q["difficulty_label"] == "A2" and len(q["options"]) == 4)
        check("правильный ответ наружу не отдаётся", "correct" not in q)
        ci = correct_index(uid)
        check("перемешивание вариантов сохраняет правильный ответ",
              ci in range(4) and level_test.check_answer(uid, ci)["correct_answer"] == "a",
              "correct=%d options=%s" % (ci, q["options"]))

        traj = [q["difficulty"]]
        total = 0
        while True:
            nxt = level_test.get_next_question(uid, correct_index(uid))   # всегда верно
            if nxt.get("finished"):
                total = nxt["result"]["total"]
                break
            traj.append(nxt["difficulty"])
        check("верные ответы повышают сложность до C1", traj[-1] == 5, "траектория %s" % traj)
        check("вопросов в пределах 10–15", 10 <= total <= 15, "их %d" % total)

        res = level_test.get_result(uid)
        check("уровень из A1–C1", res["level"] in level_test.LEVELS, res["level"])
        text = open(user_manager.identity_path(uid), encoding="utf-8").read()
        check("уровень записан в профиль",
              user_manager.get_user(uid)["level"] == res["level"] and '"level_test"' in text)
        prog = profile_store.load(uid)
        check("история теста записана в прогресс",
              len(prog.get("level_tests", [])) == 1
              and len(prog["level_tests"][-1]["answers"]) == res["total"],
              "тестов: %d" % len(prog.get("level_tests", [])))
        ans0 = prog["level_tests"][-1]["answers"][0]
        check("в истории есть дата/тема/уровень/верно-неверно",
              bool(ans0.get("date")) and bool(ans0.get("topic"))
              and ans0.get("level") in level_test.LEVELS
              and isinstance(ans0.get("correct"), bool), ans0)

        level_test.set_client(FakeLLM())
        q = level_test.start_test(uid)
        down = [q["difficulty"]]
        while True:
            nxt = level_test.get_next_question(uid, wrong_index(uid))     # всегда ошибка
            if nxt.get("finished"):
                break
            down.append(nxt["difficulty"])
        check("ошибки понижают сложность до A1", down[-1] == 1, "траектория %s" % down)
        level_test.get_result(uid)        # контроллер зовёт его в финале — и мы тоже
        weak = profile_store.load(uid).get("weak_topics", [])
        check("слабые темы появились после ошибок", len(weak) >= 1, weak)

        level_test.set_client(DeadLLM())
        q = level_test.start_test(uid)
        check("оффлайн: вопрос из резервного банка",
              bool(q["question"]) and len(q["options"]) == 4)

        class StuckLLM:
            # «Застрявшая» модель: всегда один и тот же вопрос (так ведёт себя
            # реальная модель на одной сложности, т.к. не помнит, что спросила).
            def complete(self, prompt, **k):
                return True, ('{"question": "Same one?", "options": ["a","b","c","d"], '
                              '"correct": 0}')

        level_test.set_client(StuckLLM())
        texts = [level_test.start_test(uid)["question"]]
        for _ in range(8):      # держимся на полу A1 и жмём неверные ответы
            nxt = level_test.get_next_question(uid, wrong_index(uid))
            if nxt.get("finished"):
                break
            texts.append(nxt["question"])
        check("повтор от модели не выдаётся дважды", texts[1] != texts[0],
              "%r" % (texts[:2],))
        check("подряд одинаковых вопросов нет (даже когда пул вычерпан)",
              all(texts[i] != texts[i - 1] for i in range(1, len(texts))), texts)

        level_test.set_client(FakeLLM())
        level_test.start_test(uid)
        check("check_answer понимает буквы", level_test.check_answer(uid, "B")["chosen_index"] == 1)
        level_test.start_test(uid)
        check("повторный check_answer — из кэша",
              level_test.check_answer(uid, "d") == level_test.check_answer(uid, "A"))

        before = user_manager.get_user(uid)["level"]
        level_test.start_test(uid)
        level_test.get_next_question(uid, 0)
        level_test.cancel_test(uid)
        check("прерывание не меняет профиль", user_manager.get_user(uid)["level"] == before)
    finally:
        level_test.set_client(None)
        user_manager.PROFILES_DIR = real_dir
        user_manager.LAST_USER_FILE = real_last


def main():
    e2e = "--gui" in sys.argv
    print("=" * 60)
    print("Проверка после рефакторинга" + ("  (+GUI, +диалог)" if e2e else "  (без GUI)"))
    print("=" * 60)

    test_prompt_unchanged()
    test_clean_response()
    test_profile_store()
    test_commands()
    test_users()
    test_level_test()

    if e2e:
        # во время теста не трогаем реальный профиль ученика
        real = profile_store.PROFILE_PATH
        tmp = tempfile.mkdtemp(prefix="et_gui_profile_")
        profile_store.PROFILE_PATH = os.path.join(tmp, "student_profile.json")
        if os.path.exists(real):
            with open(real, "r", encoding="utf-8") as src, \
                 open(profile_store.PROFILE_PATH, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        # многопользовательский режим: тоже уводим на временную папку
        um_dir, um_last = user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE
        user_manager.PROFILES_DIR = tmp
        user_manager.LAST_USER_FILE = os.path.join(tmp, "last_user.txt")
        user_manager.create_user("Тест", "other", 20, "A1", "прогон", "🙂")
        try:
            test_gui(e2e=True)
        finally:
            profile_store.PROFILE_PATH = real
            user_manager.PROFILES_DIR = um_dir
            user_manager.LAST_USER_FILE = um_last
            profile_store.set_active_user(None)
    else:
        print("\n(GUI-проверки пропущены: запустите с флагом --gui)")

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
