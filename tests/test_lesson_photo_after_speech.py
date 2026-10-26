# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_PHOTO_AFTER_SPEECH.PY — фото НЕ выгружается, пока Вербот говорит
# =========================================================
#   python tests\test_lesson_photo_after_speech.py
#
# ЖИВОЙ БАГ (26.10.2026). Ученик доиграл урок: последняя реплика учителя
# ОБОРВАЛАСЬ на полуслове, и сразу выгрузилось задание с фото.
#
# Почему: страховочный таймер LESSON_TAIL_FALLBACK_MS (20 с) считается от
# МОМЕНТА ОТВЕТА модели, а не от конца озвучки. До первого звука у edge-tts
# бывает 10 с (замер: «TTS: первый звук через 10.03 с»), сама реплика ещё
# 10–15 с — итог срабатывал посреди речи: похвала через _say() глушит её
# (tts.speak сначала делает tts.stop), а фото выгружалось тут же.
#
# Правило после правки: пока _speech_busy — итог, похвала и фото ЖДУТ.
# Порядок: реплика доиграла → итог → похвала → фото → просьба про фото.
# Страховка: ждём не дольше LESSON_SPEECH_WAIT_MS.
# =========================================================

import os
import sys
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config          # noqa: E402
import lesson          # noqa: E402
import ui.app as app_mod   # noqa: E402
from ui.app import EnglishTeacherApp as App   # noqa: E402

SOURCE = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def method_body(name):
    """Исходник метода (до следующего метода того же уровня)."""
    start = SOURCE.find("    def %s(" % name)
    if start < 0:
        return ""
    rest = SOURCE[start:]
    end = rest.find("\n    def ", 1)
    return rest if end < 0 else rest[:end]


# ---------- заглушки ----------
class FakeWindow:
    """Окно без Tk: after(...) запоминает колбэк и умеет его выполнить."""

    def __init__(self):
        self.calls = []

    def after(self, ms, fn=None):
        self.calls.append((ms, fn))
        return "id%d" % len(self.calls)

    def run(self):
        calls, self.calls = self.calls, []
        for _ms, fn in calls:
            if fn is not None:
                fn()
        return len(calls)


class FakeStore:
    def __init__(self):
        self.lessons = []

    def record_lesson_completed(self, lesson_id, user_id=None):
        self.lessons.append(lesson_id)
        return True


def real_session(replies=2):
    session = lesson.LessonSession("city/1.1", block_title="В городе",
                                   reply_target=replies)
    for _ in range(replies):
        session.register_reply()
    return session


def make_app():
    """Приложение-пустышка: настоящие методы порядка речи, без Tk и модели."""
    app = types.SimpleNamespace()
    app.current_user = {"id": "u1", "name": "Дамиль", "level": "A2"}
    app.teacher_name = "Verbot"
    app.messages = []
    app.said = []
    app.steps = []
    app._reply_in_flight = False
    app._deferred_finish = None
    app._deferred_deadline = None
    app._speech_busy = False
    app.window = FakeWindow()
    app.store = FakeStore()

    app.add_message = lambda sender, text, picture=None: app.messages.append(
        (sender, text)) or "msg"

    def _say(text, **kw):
        # как настоящая _say: флаг ставится СРАЗУ, звук идёт в фоне
        app.said.append(text)
        app._speech_busy = True

    app._say = _say
    app._end_lesson = lambda: app.steps.append("end_lesson")
    app._refresh_side_views = lambda: app.steps.append("refresh")
    app._lesson_state = lambda state: app.steps.append("state:" + state)
    app._start_picture_task = lambda: app.steps.append("picture")
    app._active_profile = lambda: {"id": "u1"}
    app.progress_map = types.SimpleNamespace(
        get_point_state=lambda *a, **k: (_ for _ in ()).throw(KeyError("нет точки")))

    for name in ("_on_lesson_finished", "_run_deferred_finish",
                 "_say_after_current", "_wait_for_speech", "_speech_wait_left",
                 "_test_tail_flag", "_jump_to_lesson_tail"):
        setattr(app, name, types.MethodType(getattr(App, name), app))
    return app


def with_store(app, fn):
    """Запись урока — в заглушку, настоящий профиль не трогаем."""
    old = app_mod.profile_store
    app_mod.profile_store = app.store
    try:
        return fn()
    finally:
        app_mod.profile_store = old


# ---------- проверки ----------
def test_config():
    print("\n[1] Страховка ожидания речи в config")
    value = getattr(config, "LESSON_SPEECH_WAIT_MS", None)
    tail = getattr(config, "LESSON_TAIL_FALLBACK_MS", 0)
    check("LESSON_SPEECH_WAIT_MS есть", isinstance(value, int), value)
    check("больше страховки итога (%d мс)" % tail,
          isinstance(value, int) and value > tail, value)


def test_source_order():
    print("\n[2] Фото показывается через ожидание речи")
    body = method_body("_on_lesson_finished")
    check("фото не стартует напрямую",
          "self._start_picture_task()" not in body.replace(
              "self._wait_for_speech(self._start_picture_task)", ""), body)
    check("фото ждёт конца речи",
          "self._wait_for_speech(self._start_picture_task)" in body, body)
    body = method_body("_run_deferred_finish")
    check("итог ждёт конца речи", "_speech_busy" in body, body)


def test_finish_waits_for_speech():
    print("\n[3] Итог НЕ показывается, пока реплика звучит")
    app = make_app()
    session = real_session()
    app._reply_in_flight = True
    app._speech_busy = True             # ответ учителя ещё звучит

    with_store(app, lambda: App._on_lesson_finished(app, session))
    check("итог отложен", app._deferred_finish is session, app._deferred_finish)

    with_store(app, lambda: App._run_deferred_finish(app))   # таймер сработал
    check("итог НЕ показан", app.messages == [], app.messages)
    check("похвала НЕ озвучена", app.said == [], app.said)
    check("урок НЕ закрыт", "end_lesson" not in app.steps, app.steps)
    check("фото НЕ выгружено", "picture" not in app.steps, app.steps)
    check("сессия сохранена на потом", app._deferred_finish is session,
          app._deferred_finish)
    # два «будильника»: страховка итога (20 с) и наша проверка речи (200 мс)
    check("ждём через окно", len(app.window.calls) == 2,
          [ms for ms, _fn in app.window.calls])


def test_photo_after_praise():
    print("\n[4] Речь доиграла: итог → похвала → (звук) → фото")
    app = make_app()
    session = real_session()
    app._reply_in_flight = True
    app._speech_busy = True

    with_store(app, lambda: App._on_lesson_finished(app, session))
    app._speech_busy = False            # реплика доиграла
    with_store(app, lambda: app.window.run())

    check("итог в чате", len(app.messages) == 2, app.messages)
    check("похвала озвучена", len(app.said) == 1, app.said)
    check("урок закрыт", "end_lesson" in app.steps, app.steps)
    check("фото ждёт конца похвалы", "picture" not in app.steps, app.steps)
    check("ждём через окно", len(app.window.calls) == 1, app.window.calls)

    app._speech_busy = False            # похвала доиграла
    app.window.run()
    check("фото выгружено после речи", "picture" in app.steps, app.steps)
    check("фото ПОСЛЕ закрытия урока",
          app.steps.index("picture") > app.steps.index("end_lesson"), app.steps)


def test_timeout_is_honest():
    print("\n[5] Страховка: зависшая озвучка не съедает итог навсегда")
    app = make_app()
    session = real_session()
    app._reply_in_flight = True
    app._speech_busy = True
    app._deferred_deadline = time.monotonic() - 1.0   # время ожидания вышло

    with_store(app, lambda: App._on_lesson_finished(app, session))
    with_store(app, lambda: App._run_deferred_finish(app))

    check("итог показан вопреки речи", len(app.messages) == 2, app.messages)
    check("урок закрыт", "end_lesson" in app.steps, app.steps)
    check("отметка ожидания снята", app._deferred_deadline is None,
          app._deferred_deadline)


def test_photo_task_itself():
    print("\n[6] _wait_for_speech: тишина → сразу, речь → по таймеру")
    app = make_app()
    app._speech_busy = False
    App._wait_for_speech(app, lambda: app.steps.append("now"))
    check("тишина — сразу", app.steps == ["now"], app.steps)

    app2 = make_app()
    app2._speech_busy = True
    App._wait_for_speech(app2, lambda: app2.steps.append("later"))
    check("речь идёт — ждём", app2.steps == [] and len(app2.window.calls) == 1,
          (app2.steps, app2.window.calls))
    app2._speech_busy = False
    app2.window.run()
    check("доиграло — сделали", app2.steps == ["later"], app2.steps)


def test_test_flag():
    print("\n[7] 🧪 Тестовый режим «сразу конец урока» (флаг-файл)")
    real = getattr(config, "LESSON_TEST_TAIL_FLAG", "")
    check("путь к флаг-файлу в config", bool(real), real)

    # свой временный флаг, чтобы не трогать настоящий в папке проекта
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_tmp_tail_flag.flag")
    config.LESSON_TEST_TAIL_FLAG = tmp
    app = make_app()
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
        check("нет файла — режим выключен", App._test_tail_flag() is False)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("test")
        check("есть файл — режим включён", App._test_tail_flag() is True)
    finally:
        config.LESSON_TEST_TAIL_FLAG = real
        try:
            os.remove(tmp)
        except OSError:
            pass

    session = lesson.LessonSession("city/1.1", block_title="В городе",
                                   reply_target=12)
    app._jump_to_lesson_tail(session)
    check("осталась ОДНА реплика",
          session.replies == session.hard_reply_limit - 1, session.replies)
    check("ждём последнюю реплику", session.should_finish is False)
    check("осталось ОДНО задание", session.tasks_done == session.tasks_total - 1,
          (session.tasks_done, session.tasks_total))
    check("задание последнее по счёту",
          session.task_index == session.tasks_total, session.task_index)
    check("урок всё ещё идёт", session.is_active is True)
    check("в чат сказано, что это тест (по-английски!)",
          any("TEST MODE" in t for _s, t in app.messages), app.messages)
    check("русского текста в чат не шлём (он переключил бы урок)",
          not any(any(ch in t for ch in "абвгдежзийклмнопрстуфхцчшщыэюя")
                  for _s, t in app.messages), app.messages)

    # §38: на плане реплик (12) урок НЕ закрывается — иначе бот бросал тему
    session.replies = session.reply_target
    check("на плане реплик урок ещё идёт", session.should_finish is False,
          (session.replies, session.reply_target))

    session.replies = session.hard_reply_limit - 1
    session.register_reply()          # последняя реплика ученика
    check("после ответа урок закрывается", session.should_finish is True,
          (session.replies, session.hard_reply_limit))

    source = SOURCE
    body = method_body("_begin_lesson")
    check("в _begin_lesson есть тестовый прыжок",
          "_jump_to_lesson_tail(session)" in body, body[:200])
    check("тест берёт урок НЕ экзамен (_test_lesson_id)",
          "_test_lesson_id()" in method_body("_arm_auto_lesson"),
          method_body("_arm_auto_lesson")[-300:])
    check("экзамен тестовым прыжком пропускается",
          "is_check_lesson(session.lesson_type)" in method_body("_jump_to_lesson_tail"),
          method_body("_jump_to_lesson_tail")[:300])


def main():
    print("=" * 60)
    print("ФОТО И ИТОГ — ТОЛЬКО ПОСЛЕ РЕЧИ УЧИТЕЛЯ")
    print("=" * 60)
    test_config()
    test_source_order()
    test_finish_waits_for_speech()
    test_photo_after_praise()
    test_timeout_is_honest()
    test_photo_task_itself()
    test_test_flag()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
