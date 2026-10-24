# =========================================================
# TESTS/TEST_EXAM_LESSON.PY — экзамен в занятии (проверка блока)
# =========================================================
#   python tests\test_exam_lesson.py
#
# ЗАЧЕМ. Правила балла лежат в exam.py и уже проверены
# (tests/test_exam_score.py). Здесь — как экзамен ВСТРАИВАЕТСЯ в занятие:
#   * проверка блока = экзамен: 10 вопросов, словаря нет, подсказок нет;
#   * балл за ответ ставится ПОСЛЕ разбора Аналитика (иначе правило
#     «2+ ошибки → 1 балл» не сработало бы никогда);
#   * 10-й ответ закрывает экзамен, итог уходит в чат, лучший балл — в профиль;
#   * без сдачи блок НЕ засчитывается (пересдач сколько угодно).
# Окно не создаём: методы проверяем на «пустышке» без Tk.
# =========================================================

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import exam                                                      # noqa: E402
import lesson                                                    # noqa: E402
from ui.app import EnglishTeacherApp, EXAM_NO_HINT_NOTE           # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeLesson:
    """Контроллер занятия без Tk: считает реплики и запоминает финиш."""

    def __init__(self, session):
        self.session = session
        self.finished = 0

    def is_active(self):
        return bool(self.session and self.session.is_active)

    def current(self):
        return self.session

    def register_reply(self):
        if self.session and self.session.is_active:
            self.session.register_reply()
        return self.session.state() if self.session else None

    def finish(self):
        if self.session:
            self.session.finish()
            self.finished += 1
        return self.session


class FakeInput:
    def __init__(self, text="", locked=False):
        self.text = str(text)
        self.is_locked = bool(locked)
        self.cleared = 0

    def get_text(self):
        return self.text

    def clear_text(self):
        self.cleared += 1
        self.text = ""


def make_app(check_lesson=True):
    """Приложение-пустышка: только то, что трогают методы экзамена."""
    kind = lesson.CHECK if check_lesson else lesson.SPEAKING
    session = lesson.LessonSession("desert/1.4", lesson_type=kind, code="1.4")
    app = types.SimpleNamespace(
        lesson=FakeLesson(session),
        input_bar=FakeInput("", True),
        teacher_name="Verbot",
        current_user={"id": 7},
        messages=[],
        saved=[],
        bar=[],
        ended=0,
        side=0,
        state_seen=[],
    )
    app.add_message = lambda who, what: app.messages.append((who, what))
    app._maybe_start_auto_lesson = lambda t, who: False
    app._show_translation_hint = lambda t: app.messages.append(("hint", t))
    app._handle_text = lambda t, skip_translate=False: app.messages.append(("handled", t))
    app._refresh_side_views = lambda: None
    app._lesson_state = lambda s: app.state_seen.append(s)
    app._end_lesson = lambda: setattr(app, "ended", app.ended + 1)
    app.lesson_bar = types.SimpleNamespace(
        set_progress=lambda t: app.bar.append(t))
    app._wants_translation = lambda t: EnglishTeacherApp._wants_translation(app, t)
    # методы самого приложения, которые зовут друг друга
    app._exam_session = lambda: EnglishTeacherApp._exam_session(app)
    app._exam_score_answer = (lambda r=None:
                              EnglishTeacherApp._exam_score_answer(app, r))
    app._register_lesson_reply = (lambda text="":
                                  EnglishTeacherApp._register_lesson_reply(app, text))
    app.exam_summary_text = EnglishTeacherApp.exam_summary_text
    app._on_lesson_finished = (lambda s:
                               EnglishTeacherApp._on_lesson_finished(app, s))
    app._finish_exam = lambda: EnglishTeacherApp._finish_exam(app)
    app._exam_pending = []
    app._exam = exam.ExamSession(session.lesson_id) if check_lesson else None
    app._exam_done = False
    app._exam_last = None
    return app


def profile_box(monkeypatch_list):
    """Подменяем запись в профиль: настоящий файл в тесте не трогаем."""
    return monkeypatch_list


def main():
    # ---------- 1. Проверка блока = экзамен ----------
    print("[1] Тип занятия: проверка = экзамен")
    check("10 вопросов у проверки",
          lesson.LessonSession("x", lesson_type="check").reply_target
          == exam.QUESTIONS)
    check("на проверке словаря нет",
          lesson.allows_dictionary("check") is False)
    check("на обычном уроке словарь есть",
          lesson.allows_dictionary("speaking") is True
          and lesson.allows_dictionary("listening") is True)
    hint = lesson.locked_hint("check")
    check("подсказка поля: «Экзамен» и «подсказок нет»",
          "Экзамен" in hint and "подсказок нет" in hint, hint)
    check("подсказка поля не зовёт писать по-русски",
          "по-русски" not in hint, hint)

    state = lesson.LessonSession("x", lesson_type="check").state()
    check("в состоянии есть флаг exam", state.get("exam") is True, state)
    check("в состоянии есть флаг dictionary=False",
          state.get("dictionary") is False, state)
    plain = lesson.LessonSession("y", lesson_type="speaking").state()
    check("обычный урок: exam=False, dictionary=True",
          plain.get("exam") is False and plain.get("dictionary") is True, plain)

    # ---------- 2. send_text на экзамене: ни перевода, ни отправки ----------
    print("\n[2] send_text на экзамене")
    app = make_app()
    app.input_bar.text = "ключ"
    EnglishTeacherApp.send_text(app)
    texts = [t for _, t in app.messages]
    check("русское слово НЕ переводится", not any(t == "ключ" for t in texts), texts)
    check("ученик видит «подсказок нет»",
          any(EXAM_NO_HINT_NOTE == t for t in texts), texts)
    check("поле не трогали без нужды", app.input_bar.cleared == 0)
    check("в чат ответа не ушло",
          not any(kind in ("handled",) for kind, _ in app.messages), app.messages)

    app2 = make_app()
    app2.input_bar.text = "I like apples"
    EnglishTeacherApp.send_text(app2)
    check("английский тоже не уходит в чат",
          not any(kind == "handled" for kind, _ in app2.messages), app2.messages)

    # ---------- 3. Балл ставится ПОСЛЕ разбора ----------
    print("\n[3] Балл за ответ и разбор Аналитика")
    app = make_app()
    EnglishTeacherApp._register_lesson_reply(app, "I like it very much")
    check("текст ответа отложен", app._exam_pending == ["I like it very much"],
          app._exam_pending)
    check("без разбора балл ещё не ставился", app._exam.answered == 0,
          app._exam.answered)
    step = EnglishTeacherApp._exam_score_answer(app, {"ok": True, "errors": []})
    check("после разбора балл есть", app._exam.answered == 1, app._exam.answered)
    check("чистый ответ = 2 балла", step["score"] == 2, step)
    check("полоса урока показала 1/10", app.bar == ["1/10"], app.bar)

    EnglishTeacherApp._register_lesson_reply(app, "I goes to school every day")
    step = EnglishTeacherApp._exam_score_answer(
        app, {"ok": True, "errors": [{"a": 1}, {"b": 2}]})
    check("2 ошибки → 1 балл", step["score"] == 1, step)
    check("ошибки попали в итог", app._exam.mistakes == 2, app._exam.mistakes)

    EnglishTeacherApp._register_lesson_reply(app, "я не знаю")
    step = EnglishTeacherApp._exam_score_answer(app, None)
    check("по-русски → 0 баллов", step["score"] == 0, step)
    check("разбора не было — ошибок не прибавилось", app._exam.mistakes == 2)

    check("пустой список ожидания — балла нет",
          EnglishTeacherApp._exam_score_answer(app, None) is None)

    # ---------- 4. Десятый ответ закрывает экзамен ----------
    print("\n[4] 10-й ответ: итог и запись в профиль")
    app = make_app()
    app._exam.last_state = None
    final = None
    for i in range(exam.QUESTIONS):
        EnglishTeacherApp._register_lesson_reply(app, "I like it very much")
        step = EnglishTeacherApp._exam_score_answer(app, {"ok": True, "errors": []})
        if step and step.get("finished"):
            final = step
    check("финал на 10-м ответе", final is not None and final["index"] == exam.QUESTIONS,
          final)
    check("у экзамена 10 оценок", len(app._exam.scores) == 10, app._exam.scores)
    check("итог 10.0 и сдал", app._exam.score == 10.0 and app._exam.passed is True)

    summary = EnglishTeacherApp.exam_summary_text(app._exam.result())
    check("в итоге есть балл", "10 из 10" in summary, summary)
    check("в итоге есть баллы за ответы", "2 2 2 2 2 2 2 2 2 2" in summary, summary)
    check("в итоге сказано, что сдал", "Сдал" in summary, summary)
    check("в итоге есть ошибки и подсказки",
          "Ошибок в разборе: 0" in summary, summary)

    weak = exam.ExamSession("desert/1.4")
    for _ in range(exam.QUESTIONS):
        weak.answer("I like it")                       # по 1 баллу за ответ
    low = EnglishTeacherApp.exam_summary_text(weak.result())
    check("слабый итог: «Пока не сдал»", "Пока не сдал" in low, low)
    check("слабый итог зовёт пересдавать", "Пересдача" in low, low)
    check("пустой итог не падает",
          EnglishTeacherApp.exam_summary_text(None) == "🎯 Экзамен закончен.")

    # ---------- 5. Без сдачи блок не засчитывается ----------
    print("\n[5] Не сдал — блок закрыт, сдал — открыт")
    class FakeSession:
        lesson_id = "desert/1.4"
        point_id = "desert/1"
        block_title = "Daily Routine"

    saved = {"lessons": [], "exams": []}
    fake_store = types.SimpleNamespace(
        record_lesson_completed=lambda lid, uid=None: saved["lessons"].append(lid),
        record_exam=lambda lid, score, passed, uid=None:
            saved["exams"].append((lid, score, passed)),
    )
    import ui.app as app_mod
    real_store = app_mod.profile_store
    app_mod.profile_store = fake_store
    try:
        for passed, label in ((False, "не сдал"), (True, "сдал")):
            saved["lessons"].clear()
            app = make_app()
            app._active_profile = lambda: {}
            app.progress_map = types.SimpleNamespace(
                get_point_state=lambda pid, prof: "locked")
            app._exam_last = {"score": 6.0 if passed else 4.0,
                              "passed": passed, "answers": [2] * 10,
                              "questions": 10, "correct_full": 6,
                              "mistakes": 1}
            EnglishTeacherApp._on_lesson_finished(app, FakeSession())
            if passed:
                check("сдал → урок засчитан",
                      saved["lessons"] == ["desert/1.4"], saved["lessons"])
            else:
                check("не сдал → урок НЕ засчитан",
                      saved["lessons"] == [], saved["lessons"])
            check("%s → итог показан в чате" % label, len(app.messages) == 1,
                  app.messages)
            check("%s → занятие закрыто" % label, app.ended == 1, app.ended)
    finally:
        app_mod.profile_store = real_store

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
