# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_TRANSLATE_LESSON.PY — урок-перевод русских фраз (§82)
# =========================================================
#   python tests/test_translate_lesson.py
#
# Решение ученика 15.11.2026: уроки ДО петли — перевод РУССКОЙ фразы.
# Фразу показывает ПРИЛОЖЕНИЕ (model её не сочиняет), сверка — translate_task.
# Здесь проверяется:
#   1) фаза перевода в сессии урока (число заданий, подпись полосы);
#   2) урок с фразами запускается приложением, урок без фраз — нет;
#   3) OK засчитывает задание, NO — подсказка без зачёта и без ошибки в базе;
#   4) промах идёт в базу пробелов с ПРАВИЛОМ из фразы, текст без латиницы — нет;
#   5) после третьей попытки эталон показывается, задание сдано «с подсказкой».
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
import profile_store                                     # noqa: E402
import translate_task                                    # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    mark = "\u2705" if ok else "\u274c"
    print("  " + mark + " " + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


# ---------------------------------------------------------
def test_phase():
    print("\n[1] Фаза перевода в сессии урока")
    check("константа TASK_TRANSLATE есть",
          getattr(lesson_mod, "TASK_TRANSLATE", "") == "translate")
    session = lesson_mod.LessonSession("city/5.1", lesson_type=lesson_mod.SPEAKING,
                                       title="Present Perfect", code="5.1")
    check("в уроке 5 заданий", session.tasks_total == config.LESSON_TASKS,
          session.tasks_total)
    check("до перевода фаза — ask", session.task_phase == lesson_mod.TASK_ASK)
    check("start_translate включается", session.start_translate() is True)
    check("фаза стала translate", session.task_phase == "translate",
          session.task_phase)
    check("полоса пишет «Перевод 1/5»", session.progress_text() == "Перевод 1/5",
          session.progress_text())
    session.credit_task("have you ever been to new york")
    check("после зачёта фаза снова ask (её ставят заново)",
          session.task_phase == lesson_mod.TASK_ASK, session.task_phase)


def test_material():
    print("\n[2] Материал: фразы пилота")
    check("фразы для city/5.1 есть", translate_task.has("city/5.1") is True)
    check("фразы для city/4.1 нет (урок идёт как раньше)",
          translate_task.has("city/4.1") is False)
    phrase = translate_task.pick("city/5.1", 0)
    check("у фразы есть ru/en/rule",
          bool(phrase.get("ru") and phrase.get("en") and phrase.get("rule")),
          phrase)
    check("номер больше списка — берём по кругу",
          translate_task.pick("city/5.1", 99) is not None)


# ---------------------------------------------------------
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
    """Только то, что нужно уроку-переводу (без Tk и без модели)."""

    _start_translate_lesson = None
    _translate_ask = None
    _translate_reply = None
    _translate_verdict = None
    _translate_pass = None
    _translate_miss = None
    _translate_record = None
    _current_phrase = None
    _after_credit = None

    def __init__(self, session):
        self.lesson = FakeLesson(session)
        self.lesson_bar = FakeBar()
        self.current_user = {"id": None}
        self.server_ready = False
        self.teacher_name = "Verbot"
        self.messages = []
        self.said = []
        self.alts = []
        self.credited = []
        self.recorded = []
        self._meaning_busy = False

    # --- заглушки окружения ---
    def add_message(self, sender, text, **kw):
        self.messages.append(str(text))

    def _say(self, text):
        self.said.append(str(text))

    _say_after_current = _say

    def _offer_alts(self, phrase):
        self.alts.append(str(phrase))

    def _credit_task(self, session, text="", marked=False):
        self.credited.append((marked, text))
        return session.credit_task(text, marked=marked) is not None

    def _sync_lesson_prompt(self, *a, **k):
        return {}

    def _meaning_second_look(self, said, want, on_verdict):
        return False        # модель недоступна: решение даёт код


def _bind():
    from ui.app import EnglishTeacherApp as App
    FakeApp._start_translate_lesson = App._start_translate_lesson
    FakeApp._translate_ask = App._translate_ask
    FakeApp._translate_reply = App._translate_reply
    FakeApp._translate_verdict = App._translate_verdict
    FakeApp._translate_pass = App._translate_pass
    FakeApp._translate_miss = App._translate_miss
    FakeApp._translate_record = App._translate_record
    FakeApp._current_phrase = App._current_phrase
    FakeApp._after_credit = App._after_credit


def _app(lesson_id="city/5.1"):
    session = lesson_mod.LessonSession(lesson_id, lesson_type=lesson_mod.SPEAKING,
                                       title="Present Perfect", code="5.1")
    return FakeApp(session)


def test_start():
    print("\n[3] Урок запускает приложение, а не модель")
    app = _app()
    started = app._start_translate_lesson(app.lesson.session)
    check("урок с фразами стартовал", started is True)
    check("первая фраза показана",
          any("Say it in English" in m for m in app.messages), app.messages)
    check("фраза показана по-русски",
          any("Ты когда-нибудь" in m for m in app.messages), app.messages)
    check("модель не звали (озвучки нет)", app.said == [], app.said)
    check("фаза перевода стоит",
          app.lesson.session.task_phase == "translate")
    check("полоса урока показывает перевод",
          app.lesson_bar.text == "Перевод 1/5", app.lesson_bar.text)

    app2 = _app("city/4.1")
    check("урок без фраз переводу не подчиняется",
          app2._start_translate_lesson(app2.lesson.session) is False)


def test_ok():
    print("\n[4] Верный перевод — зачёт")
    app = _app()
    app._start_translate_lesson(app.lesson.session)
    session = app.lesson.session
    phrase = translate_task.pick("city/5.1", 0)
    taken = app._translate_reply(phrase["en"])
    check("реплика забрана уроком-переводом", taken is True)
    check("задание засчитано без пометки", app.credited == [(False, phrase["en"])],
          app.credited)
    check("эталон сказан вслух", app.said == [phrase["en"]], app.said)
    check("«почему» объяснено", any("have been" in m for m in app.messages),
          app.messages[-2:])
    check("следующая фраза показана (Task 2/5)",
          any("Task 2/5" in m for m in app.messages), app.messages[-1])


def test_russian():
    print("\n[5] По-русски — это не ответ (NO)")
    app = _app()
    app._start_translate_lesson(app.lesson.session)
    session = app.lesson.session
    taken = app._translate_reply("ты когда-нибудь был в нью-йорке?")
    check("реплика забрана (в модель не уходит)", taken is True)
    check("задание НЕ засчитано", app.credited == [], app.credited)
    check("попытка посчитана", session.task_attempts == 1, session.task_attempts)
    check("подсказка «по-английски»",
          any("In English" in m for m in app.messages), app.messages[-1])
    check("ошибка в пробелы не пошла (пустая реплика не ответ)",
          app.recorded == [], app.recorded)


def test_miss():
    print("\n[6] Промах: подсказка с правилом, задание стоит")
    app = _app()
    app._start_translate_lesson(app.lesson.session)
    session = app.lesson.session
    taken = app._translate_reply("I like tea very much")
    check("реплика забрана", taken is True)
    check("задание НЕ засчитано", app.credited == [], app.credited)
    check("подсказка про правило урока",
          any("Think about" in m for m in app.messages), app.messages[-1])
    check("ответа на задание не показали (нет эталона)",
          all("Have you ever" not in m for m in app.messages),
          app.messages[-1])


def test_reveal_and_record():
    print("\n[7] Три попытки: эталон, зачёт с пометкой, правило в пробелы")
    app = _app()
    app._start_translate_lesson(app.lesson.session)
    phrase = translate_task.pick("city/5.1", 0)
    saved = {}

    original = profile_store.record_analysis

    def fake_record(analysis, user_text, jane_response="", user_id=None,
                    count_session=True):
        saved["analysis"] = analysis
        saved["text"] = user_text
        saved["count_session"] = count_session
        return []

    profile_store.record_analysis = fake_record
    try:
        for _ in range(lesson_mod.MAX_TASK_ATTEMPTS):
            app._translate_reply("I like tea very much")
    finally:
        profile_store.record_analysis = original

    check("показан эталон",
          any(m.startswith("👉 Correct: " + phrase["en"]) for m in app.messages),
          [m for m in app.messages if "Correct" in m])
    check("задание сдано с пометкой", app.credited == [(True, "I like tea very much")],
          app.credited)
    check("промах записан в базу", bool(saved), saved)
    errors = (saved.get("analysis") or {}).get("errors") or [{}]
    check("правило из фразы доехало", errors[0].get("rule") == phrase["rule"],
          errors[0].get("rule"))
    check("как надо — эталон", errors[0].get("correct") == phrase["en"],
          errors[0].get("correct"))
    check("урок записан в ошибку", (saved.get("analysis") or {}).get("lesson")
          == "city/5.1", (saved.get("analysis") or {}).get("lesson"))
    check("промах не считается концом занятия",
          saved.get("count_session") is False, saved.get("count_session"))
    check("следующая фраза после зачёта",
          any("Task 2/5" in m for m in app.messages), app.messages[-1])


def test_record_guard():
    print("\n[8] Текст без английских слов в пробелы не пишем")
    app = _app()
    app._start_translate_lesson(app.lesson.session)
    phrase = translate_task.pick("city/5.1", 0)
    saved = {}
    original = profile_store.record_analysis

    def fake_record(analysis, user_text, jane_response="", user_id=None,
                    count_session=True):
        saved["analysis"] = analysis
        return []

    profile_store.record_analysis = fake_record
    try:
        empty = app._translate_record(app.lesson.session, "", phrase)
        russian = app._translate_record(app.lesson.session, "не знаю", phrase)
    finally:
        profile_store.record_analysis = original
    check("пустая реплика — не пробел", empty is False)
    check("русская реплика — не пробел", russian is False)
    check("в базу ничего не ушло", saved == {}, saved)


def test_finish():
    print("\n[9] Последнее задание закрывает урок")
    app = _app()
    app._start_translate_lesson(app.lesson.session)
    session = app.lesson.session
    for index in range(session.tasks_total):
        phrase = translate_task.pick(session.lesson_id, session.tasks_done)
        app._translate_reply(phrase["en"])
    check("все задания сданы", session.all_tasks_done, session.tasks_done)
    check("урок больше не активен", session.is_active is False)
    check("новой фразы после конца урока не показали",
          app.messages[-1].count("Task") == 0, app.messages[-1])


def main():
    _bind()
    test_phase()
    test_material()
    test_start()
    test_ok()
    test_russian()
    test_miss()
    test_reveal_and_record()
    test_record_guard()
    test_finish()
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
