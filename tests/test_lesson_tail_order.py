# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_TAIL_ORDER.PY — итог урока НЕ влезает раньше ответа
# =========================================================
#   python tests\test_lesson_tail_order.py
#
# ЖИВОЙ БАГ (25.10.2026). Ученик ответил на 12-ю реплику урока. Приложение
# сначала посчитало реплику (в счётчике урока она последняя), а уже ПОТОМ
# отправляло её учителю. Итог сработал мгновенно:
#   итог «Nice try! 12 replies…» → задание с фото → и только затем ответ
#   учителя на 12-ю реплику.
# Плюс tts.speak() в начале глушит предыдущую реплику (tts.stop()), поэтому
# просьба про фото обрывала похвалу — «Вербот запнулся».
#
# Правило после правки: реплика, закрывающая урок, НЕ показывает итог сразу.
# Итог ждёт (1) ответа учителя, (2) конца его озвучки — и только потом
# появляются итог, похвала и фото. Просьба про фото говорится ПОСЛЕ похвалы.
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
    """Окно без Tk: после(...) запоминает колбэк и умеет его выполнить."""

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
    """Настоящая сессия урока (чтобы итог считал те же числа)."""
    session = lesson.LessonSession("city/1.1", block_title="В городе",
                                   reply_target=replies)
    for _ in range(replies):
        session.register_reply()
    return session


def make_app(store=None):
    """Заглушка приложения: настоящие методы порядка, без Tk и модели."""
    app = types.SimpleNamespace()
    app.current_user = {"id": "u1", "name": "Дамиль", "level": "A2"}
    app.teacher_name = "Verbot"
    app.messages = []           # (кто, текст)
    app.said = []               # что просили озвучить
    app.steps = []              # порядок действий
    app._reply_in_flight = False
    app._deferred_finish = None
    app._speech_busy = False
    app.window = FakeWindow()

    app.add_message = lambda sender, text, picture=None: app.messages.append(
        (sender, text)) or "msg"
    app._say = lambda text, **kw: app.said.append(text)
    app._end_lesson = lambda: app.steps.append("end_lesson")
    app._refresh_side_views = lambda: app.steps.append("refresh")
    app._lesson_state = lambda state: app.steps.append("state:" + state)
    app._start_picture_task = lambda: app.steps.append("picture")
    app._active_profile = lambda: {"id": "u1"}
    app.progress_map = types.SimpleNamespace(
        get_point_state=lambda *a, **k: (_ for _ in ()).throw(KeyError("нет точки")))

    for name in ("_on_lesson_finished", "_run_deferred_finish"):
        setattr(app, name, types.MethodType(getattr(App, name), app))
    app.store = store or FakeStore()
    return app


# ---------- проверки ----------
def test_config():
    print("\n[1] Страховочный таймер в config")
    value = getattr(config, "LESSON_TAIL_FALLBACK_MS", None)
    check("LESSON_TAIL_FALLBACK_MS есть", value is not None, value)
    check("это разумное число (> 5 с)", isinstance(value, int) and value > 5000, value)


def test_send_marks_in_flight():
    print("\n[2] Реплика помечает «ответ учителя в пути»")
    body = method_body("_send_to_teacher")
    check("флаг ставится в _send_to_teacher", "_reply_in_flight = True" in body, body)
    check("флаг ставится ДО счёта реплики",
          body.find("_reply_in_flight = True") < body.find("_register_lesson_reply"),
          (body.find("_reply_in_flight = True"),
           body.find("_register_lesson_reply")))
    check("реплика уходит учителю после счёта",
          body.find("_register_lesson_reply") < body.find("self.chat.send("))

    app = make_app()
    app.chat = types.SimpleNamespace(send=lambda t: app.steps.append("send"))
    app._register_lesson_reply = lambda text: app.steps.append("count")
    App._send_to_teacher(app, "today i ate flatbread")
    check("порядок: флаг → счёт → отправка",
          app.steps == ["count", "send"] and app._reply_in_flight is True,
          (app.steps, app._reply_in_flight))


def test_finish_is_deferred():
    print("\n[3] Итог ждёт ответа: пока флаг стоит — ничего не показываем")
    app = make_app()
    app._reply_in_flight = True
    session = real_session()

    old_store = app_mod.profile_store
    app_mod.profile_store = app.store
    try:
        App._on_lesson_finished(app, session)
    finally:
        app_mod.profile_store = old_store

    check("итог НЕ показан", app.messages == [], app.messages)
    check("похвала НЕ озвучена", app.said == [], app.said)
    check("урок НЕ закрыт", "end_lesson" not in app.steps, app.steps)
    check("фото НЕ начато", "picture" not in app.steps, app.steps)
    check("сессия запомнена", app._deferred_finish is session, app._deferred_finish)
    check("страховочный таймер взведён", len(app.window.calls) == 1,
          app.window.calls)


def test_deferred_runs_once():
    print("\n[4] Отложенный итог показывается РОВНО один раз")
    app = make_app()
    app._reply_in_flight = True
    session = real_session()

    old_store = app_mod.profile_store
    app_mod.profile_store = app.store
    try:
        App._on_lesson_finished(app, session)      # отложили
        App._run_deferred_finish(app)              # показали
        first = list(app.messages)
        App._run_deferred_finish(app)              # второй раз — тишина
        App._run_deferred_finish(app)
    finally:
        app_mod.profile_store = old_store

    check("итог показан один раз", len(app.messages) == 2, app.messages)
    check("записано, что урок засчитан", app.store.lessons == ["city/1.1"],
          app.store.lessons)
    check("порядок: итог → похвала", first == app.messages and len(first) == 2, first)
    check("похвала озвучена", len(app.said) == 1, app.said)
    check("фото начато ПОСЛЕ итога",
          app.steps.index("picture") > app.steps.index("end_lesson"), app.steps)
    check("сессия очищена", app._deferred_finish is None, app._deferred_finish)


def test_exam_untouched():
    print("\n[5] Экзамен не сломан: без флага итог показывается сразу")
    app = make_app()
    app._reply_in_flight = False
    app._exam_last = {"passed": True, "score": 8, "answers": [2] * 10}
    app.exam_summary_text = App.exam_summary_text   # staticmethod: (result)
    exam_session = real_session()

    old_store = app_mod.profile_store
    app_mod.profile_store = app.store
    try:
        App._on_lesson_finished(app, exam_session)
    finally:
        app_mod.profile_store = old_store

    check("итог экзамена в чате", any("ЭКЗАМЕН" in t for _s, t in app.messages),
          app.messages)
    check("обычного итога урока нет", not any("Отвечено" in t for _s, t in app.messages),
          app.messages)
    check("фото в ветке экзамена НЕ начинали", "picture" not in app.steps, app.steps)


def test_speech_chained():
    print("\n[6] Ответ → досказал → итог (связка через _finish_speech)")
    body = method_body("_on_response")
    check("_on_response снимает флаг", "_reply_in_flight = False" in body, body)
    body = method_body("_finish_speech")
    check("_finish_speech показывает отложенный итог",
          "_run_deferred_finish()" in body, body)

    app = make_app()
    app.chat_view = types.SimpleNamespace(enable_replay=lambda m: app.steps.append("replay"))
    app._run_deferred_finish = lambda: app.steps.append("tail")
    app._character_state = lambda s: None
    app._story_end_at = 0.0
    app.character = None
    app._mood_plan = None
    App._finish_speech(app, None, False)
    check("итог запускается после речи", app.steps[:1] == ["tail"], app.steps)


def test_picture_prompt_waits():
    print("\n[7] Просьба про фото ждёт конца похвалы")
    app = make_app()
    app._say = lambda text, **kw: app.said.append(text)
    app._say_after_current = types.MethodType(App._say_after_current, app)

    # речь идёт — говорим НЕ сейчас
    app._speech_busy = True
    app._say_after_current("Look at the photo and describe it, please.")
    check("пока идёт речь — молчим", app.said == [], app.said)
    check("ждём через окно", len(app.window.calls) == 1, app.window.calls)

    # «речь доиграла» — повторяем попытку
    app._speech_busy = False
    app.window.run()
    check("речь кончилась — сказали", app.said == [
        "Look at the photo and describe it, please."], app.said)

    # и сразу, если ничего не звучит
    app2 = make_app()
    app2._say = lambda text, **kw: app2.said.append(text)
    app2._say_after_current = types.MethodType(App._say_after_current, app2)
    app2._speech_busy = False
    app2._say_after_current("Look at the photo and describe it, please.")
    check("тишина — сразу", app2.said == [
        "Look at the photo and describe it, please."], app2.said)


def test_speech_flag_sync():
    print("\n[8] _speech_busy ставится ДО запуска потока (иначе гонка)")
    body = method_body("_say")
    pos_flag = body.find("self._speech_busy = True")
    pos_thread = body.find("threading.Thread(target=_worker")
    check("флаг в _say есть", pos_flag > 0, pos_flag)
    check("флаг раньше потока", 0 < pos_flag < pos_thread, (pos_flag, pos_thread))


def main():
    print("=" * 60)
    print("ПОРЯДОК ИТОГА УРОКА: ответ → речь → итог → фото")
    print("=" * 60)
    test_config()
    test_send_marks_in_flight()
    test_finish_is_deferred()
    test_deferred_runs_once()
    test_exam_untouched()
    test_speech_chained()
    test_picture_prompt_waits()
    test_speech_flag_sync()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
