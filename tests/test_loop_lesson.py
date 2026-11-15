# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LOOP_LESSON.PY — урок-петля вместо экзамена (§80)
# =========================================================
#   python tests/test_loop_lesson.py
#
# Решение ученика 15.11.2026: 4-й урок блока — не экзамен, а работа над
# ошибками. Урок идёт, пока loop_progress.progress()["pass"] не станет True.
# Проверяется:
#   1) материал петли (loop_tasks): фразы по ПРАВИЛУ из трёх файлов;
#   2) фаза петли в сессии урока (план, текущий пункт, подпись полосы);
#   3) приложение само показывает пункт и засчитывает ответ;
#   4) верный ответ двигает серию правила, промах — пишет пробел;
#   5) порог взят — урок закрывается сразу, лишние пункты не нужны;
#   6) бар в окне блока: тип «петля», процент и метка порога.
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _utf8():
    for _stream in (sys.stdout, sys.stderr):
        try:
            if _stream.encoding and _stream.encoding.lower() != "utf-8":
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_utf8()

import config                                            # noqa: E402
config.STT_SAVE_AUDIO = False

import lesson as lesson_mod                              # noqa: E402
import loop_progress                                     # noqa: E402
import loop_tasks                                        # noqa: E402
import profile_store                                     # noqa: E402
import stats_store                                       # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    mark = "✅" if ok else "❌"
    print("  " + mark + " " + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def title(text):
    print("")
    print(text)


# ---------------------------------------------------------
def test_material():
    title("[1] Материал петли: фразы по правилу")
    table = loop_tasks.by_rule()
    check("материал собран по правилам", bool(table), list(table)[:3])
    check("правило word_choice есть (пары «было → стало»)",
          bool(table.get("word_choice")), len(table.get("word_choice") or []))
    check("правило word_order есть (фразы для петли)",
          bool(table.get("word_order")), len(table.get("word_order") or []))
    item = (table.get("word_order") or [{}])[0]
    check("у пункта есть ru/en/why/rule",
          bool(item.get("ru") and item.get("en") and item.get("why")
               and item.get("rule")), item)
    check("библиотечная пара в чужое правило не попадает",
          all(not str(k).startswith("a2.") for k in table), list(table)[:5])
    check("дубликатов фраз нет",
          all(len({(i["ru"], i["en"]) for i in items}) == len(items)
              for items in table.values()))

    plan = loop_tasks.plan(["word_choice", "verb_form", "word_order"])
    check("в плане 9 пунктов (по 3 на правило)", len(plan) == 9, len(plan))
    check("правила в плане перемешаны",
          [i["rule"] for i in plan[:3]]
          == ["word_choice", "verb_form", "word_order"],
          [i["rule"] for i in plan[:3]])
    check("правило без материала пропускается, а не выдумывается",
          loop_tasks.plan(["nonsense_rule"]) == [])
    check("missing() честно перечисляет пустые правила",
          loop_tasks.missing(["nonsense_rule"]) == ["nonsense_rule"])


def test_session():
    title("[2] Фаза петли в сессии урока")
    check("тип loop известен",
          lesson_mod.normalize_type("loop") == lesson_mod.LOOP)
    check("подпись типа — «петля»", lesson_mod.type_label("loop") == "петля")
    check("петля — не экзамен",
          lesson_mod.is_check_lesson("loop") is False)
    check("в петле можно и голосом, и текстом",
          lesson_mod.allowed_inputs("loop") == {"voice", "text"})
    session = lesson_mod.LessonSession("city/4.4", lesson_type="loop",
                                       title="Работа над ошибками", code="4.4")
    check("сессия знает, что она петля", session.is_loop is True)
    items = loop_tasks.plan(["word_choice", "word_order"])
    check("план ставится в сессию", session.start_loop(items) is True)
    check("заданий стало по числу пунктов",
          session.tasks_total == len(items), session.tasks_total)
    check("правила запомнены без повторов",
          session.loop_rules == ["word_choice", "word_order"],
          session.loop_rules)
    check("полоса пишет «Петля 1/6»",
          session.progress_text() == "Петля 1/%d" % len(items),
          session.progress_text())
    check("текущий пункт — первый", session.loop_current() == items[0])
    session.credit_task("we have never eaten anything like this")
    check("после зачёта пункт сдвинулся", session.loop_current() == items[1])
    check("фазу после зачёта ставят заново", session.start_loop() is True)
    check("фаза снова петля", session.task_phase == lesson_mod.TASK_LOOP)


class FakeLesson(object):
    def __init__(self, session):
        self.session = session

    def current(self):
        return self.session


class FakeBar(object):
    def __init__(self):
        self.text = ""

    def set_progress(self, text):
        self.text = str(text)


class FakeApp(object):
    _start_loop_lesson = None
    _loop_ask = None
    _loop_finish = None
    _loop_exhausted = None
    _current_phrase = None
    _after_credit = None
    _translate_reply = None
    _translate_pass = None
    _translate_miss = None
    _translate_verdict = None
    _translate_record = None

    def __init__(self, session):
        self.lesson = FakeLesson(session)
        self.lesson_bar = FakeBar()
        self.current_user = {"id": None}
        self.server_ready = False
        self.teacher_name = "Verbot"
        self.messages = []
        self.said = []
        self.credited = []
        self.closed = 0
        self._meaning_busy = False

    def add_message(self, sender, text, **kw):
        self.messages.append(str(text))

    def _say(self, text):
        self.said.append(str(text))

    _say_after_current = _say

    def _offer_alts(self, phrase):
        return []

    def _credit_task(self, session, text="", marked=False):
        self.credited.append((marked, text))
        session.credit_task(text, marked=marked)
        return True

    def _sync_lesson_prompt(self, *a, **k):
        return {}

    def _meaning_second_look(self, said, want, on_verdict):
        return False

    def _close_lesson_after_credit(self):
        self.closed += 1


def _bind():
    from ui.app import EnglishTeacherApp as App
    for name in ("_start_loop_lesson", "_loop_ask", "_loop_finish",
                 "_loop_exhausted", "_current_phrase", "_after_credit",
                 "_translate_reply", "_translate_pass", "_translate_miss",
                 "_translate_verdict", "_translate_record"):
        setattr(FakeApp, name, getattr(App, name))


def _app():
    session = lesson_mod.LessonSession("city/4.4", lesson_type="loop",
                                       title="Работа над ошибками", code="4.4")
    return FakeApp(session)


def test_start():
    title("[3] Пункт петли показывает приложение")
    app = _app()
    original = loop_progress.session_rules
    loop_progress.session_rules = lambda *a, **k: [
        {"rule": "word_order"}, {"rule": "verb_form"}]
    try:
        started = app._start_loop_lesson(app.lesson.session)
    finally:
        loop_progress.session_rules = original
    session = app.lesson.session
    check("петля стартовала", started is True)
    check("правила объявлены по-русски",
          any("порядок слов" in m for m in app.messages), app.messages[:1])
    check("первый пункт с русской фразой",
          any("🇷🇺" in m for m in app.messages), app.messages[-1])
    check("заданий — по числу пунктов плана",
          session.tasks_total == 6, session.tasks_total)
    check("фаза петли стоит", session.task_phase == lesson_mod.TASK_LOOP)
    check("полоса урока показывает петлю",
          app.lesson_bar.text == "Петля 1/6", app.lesson_bar.text)

    other = FakeApp(lesson_mod.LessonSession("city/5.1",
                                             lesson_type=lesson_mod.SPEAKING))
    check("обычный урок петлёй не становится",
          other._start_loop_lesson(other.lesson.session) is False)


def test_answer():
    title("[4] Ответ: зачёт двигает серию правила")
    app = _app()
    original_rules = loop_progress.session_rules
    original_ok = stats_store.drill_ok
    original_fail = stats_store.drill_fail
    original_progress = loop_progress.progress
    marks = []
    loop_progress.session_rules = lambda *a, **k: [{"rule": "word_order"}]
    stats_store.drill_ok = lambda rule, step=1, user_id=None: (
        marks.append(("ok", rule)) or {"streak": step, "mastered_at": ""})
    stats_store.drill_fail = lambda rule, user_id=None: (
        marks.append(("fail", rule)) or {})
    loop_progress.progress = lambda *a, **k: {"percent": 33, "pass": False,
                                              "pass_percent": 80, "rules": []}
    try:
        app._start_loop_lesson(app.lesson.session)
        session = app.lesson.session
        item = session.loop_current()
        app._translate_reply(item["en"])
        check("серия правила выросла", marks == [("ok", "word_order")], marks)
        check("задание засчитано", len(app.credited) == 1, app.credited)
        check("следующий пункт показан (2/3: одно правило в сессии)",
              any("2/3" in m for m in app.messages), app.messages[-1])
        check("урок ещё идёт", session.is_active is True)

        loop_progress.progress = lambda *a, **k: {"percent": 100, "pass": True,
                                                  "pass_percent": 80,
                                                  "rules": []}
        item = session.loop_current()
        app.messages = []
        app._translate_reply(item["en"])
        check("порог объявлен ученику",
              any("Порог взят" in m for m in app.messages), app.messages[-1])
        check("урок закрыт", session.finished is True)
        check("итог урока запущен", app.closed == 1, app.closed)
        check("план сокращён до сделанного (итог не врёт)",
              session.tasks_total == session.tasks_done,
              (session.tasks_total, session.tasks_done))
    finally:
        loop_progress.session_rules = original_rules
        loop_progress.progress = original_progress
        stats_store.drill_ok = original_ok
        stats_store.drill_fail = original_fail


def test_miss():
    title("[5] Промах в петле: серия сброшена, пробел записан")
    app = _app()
    original_rules = loop_progress.session_rules
    original_ok = stats_store.drill_ok
    original_fail = stats_store.drill_fail
    original_progress = loop_progress.progress
    original_record = profile_store.record_analysis
    marks = []
    saved = {}
    loop_progress.session_rules = lambda *a, **k: [{"rule": "word_order"}]
    stats_store.drill_ok = lambda rule, step=1, user_id=None: {
        "streak": step, "mastered_at": ""}
    stats_store.drill_fail = lambda rule, user_id=None: (
        marks.append(("fail", rule)) or {})
    loop_progress.progress = lambda *a, **k: {"percent": 0, "pass": False,
                                              "pass_percent": 80, "rules": []}

    def fake_record(analysis, user_text, jane_response="", user_id=None,
                    count_session=True):
        saved["analysis"] = analysis
        return []

    profile_store.record_analysis = fake_record
    try:
        app._start_loop_lesson(app.lesson.session)
        for _ in range(lesson_mod.MAX_TASK_ATTEMPTS):
            app._translate_reply("I like tea very much")
        check("серия правила сброшена", marks == [("fail", "word_order")], marks)
        errors = (saved.get("analysis") or {}).get("errors") or [{}]
        check("правило пункта ушло в пробелы",
              errors[0].get("rule") == "word_order", errors[0].get("rule"))
        check("задание сдано с пометкой",
              app.credited == [(True, "I like tea very much")], app.credited)
    finally:
        loop_progress.session_rules = original_rules
        loop_progress.progress = original_progress
        stats_store.drill_ok = original_ok
        stats_store.drill_fail = original_fail
        profile_store.record_analysis = original_record


def test_bar():
    title("[6] Бар в окне блока")
    import ui.panels.block_panel as block_panel
    check("тип «петля» подписан",
          block_panel.TYPE_LABELS.get("loop") == "петля")
    check("окно знает тип петли", block_panel.LOOP_TYPE == "loop")
    state = block_panel.loop_state()
    check("состояние бара считается",
          isinstance(state, dict) and ("percent" in state or not state), state)
    src = open(os.path.join(ROOT, "ui", "panels", "block_panel.py"),
               encoding="utf-8").read()
    check("бар рисуется только у петли", "_loop_bar" in src
          and "LOOP_TYPE" in src)
    check("метка порога стоит на своём месте",
          "pass_percent" in src and "relx=edge / 100.0" in src)
    check("цвет по спектру red→green",
          "loop_progress.color(percent, edge)" in src)


def main():
    _bind()
    test_material()
    test_session()
    test_start()
    test_answer()
    test_miss()
    test_bar()
    print("")
    if FAILED:
        print("❌ ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("   - " + name)
        return 1
    print("✅ ВСЁ ЗЕЛЁНОЕ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
