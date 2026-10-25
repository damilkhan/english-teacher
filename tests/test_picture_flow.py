# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PICTURE_FLOW.PY — задание с картинкой в окне
# =========================================================
#   python tests\test_picture_flow.py
#
# Проверяем склейку без Tk-окна (методы ui/app.py зовём с заглушкой):
#   1) _start_picture_task показывает фото репликой и включает порог;
#   2) короткий ответ в модель НЕ уходит, подсказка честная (сколько не хватает);
#   3) повтор одного слова и мало разных слов — тоже не уходят;
#   4) после набора порога задание закрыто, счётчик убран, есть «принято»;
#   5) _handle_text при активном задании не доходит до модели;
#   6) clear_chat сбрасывает задание (по исходнику app.py).
# =========================================================

import os
import re
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

import picture_task                                    # noqa: E402
from ui.app import EnglishTeacherApp as App            # noqa: E402

FAILED = []
GOOD = ("There are many shops on the street. People are walking in the wet "
        "street. The sky is grey and the weather is cloudy. I can see a bus "
        "and two red cars near the old building.")


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeChat:
    def __init__(self):
        self.sent = []          # (sender, text)
        self.pictures = []      # пути фото в репликах

    def add_message(self, sender, text, picture=None):
        self.sent.append((sender, text))
        self.pictures.append(picture)
        return "msg_%d" % len(self.sent)


class FakeInputBar:
    def __init__(self):
        self.counter = 0
        self.history = []

    def set_counter(self, total):
        self.counter = int(total or 0)
        self.history.append(self.counter)

    def clear_counter(self):
        self.counter = 0


def make_app(level="A2"):
    """Заглушка приложения: живые методы App, но без Tk и модели."""
    app = types.SimpleNamespace()
    app.current_user = {"id": "u1", "name": "Дамиль", "level": level}
    app.teacher_name = "Verbot"
    app.chat = FakeChat()
    app.chat_view = app.chat
    app.input_bar = FakeInputBar()
    app._picture = None
    app.said = []

    app.add_message = types.MethodType(App.add_message, app)
    app._picture_level = types.MethodType(App._picture_level, app)
    app._start_picture_task = types.MethodType(App._start_picture_task, app)
    app._picture_reply = types.MethodType(App._picture_reply, app)
    app._picture_hint = types.MethodType(App._picture_hint, app)
    app._say = lambda *a, **k: app.said.append(a[0] if a else "")
    app.glossary_controller = types.SimpleNamespace(request=lambda text: None)
    return app


def texts(app):
    """Только реплики преподавателя (без служебных)."""
    return [t for _s, t in app.chat.sent]


def test_start():
    print("\n[1] Задание стартует с фото")
    app = make_app()
    check("задание началось", app._start_picture_task() is True)
    check("порог включён (105)", app.input_bar.counter == 105, app.input_bar.counter)
    check("реплика с фото отправлена", len(app.chat.sent) == 1, app.chat.sent)
    path = app.chat.pictures[0]
    check("фото передано в чат", bool(path) and os.path.exists(path), path)
    check("в тексте назван порог", "105" in texts(app)[0], texts(app)[0])
    check("преподаватель попросил описать по-английски",
          "describe" in (app.said[-1] or ""), app.said)
    check("данные задания сохранены", (app._picture or {}).get("threshold") == 105,
          app._picture)


def test_short():
    print("\n[2] Короткий ответ")
    app = make_app()
    app._start_picture_task()
    before = len(app.chat.sent)
    handled = app._picture_reply("A street with people.")
    check("реплика обработана локально", handled is True)
    check("появилась подсказка", len(app.chat.sent) == before + 1)
    last = texts(app)[-1]
    check("сказано, сколько букв", "17" in last and "105" in last, last)
    check("сказано, сколько добавить", "88" in last, last)
    check("задание НЕ закрыто", app._picture is not None)
    check("счётчик на месте", app.input_bar.counter == 105)


def test_repeat_and_few():
    print("\n[3] Накрутка повтором и мало разных слов")
    app = make_app()
    app._start_picture_task()
    app._picture_reply("cat " * 60)
    last = texts(app)[-1]
    check("повтор поймали", "повторяется" in last, last)
    check("сказано про другие слова", "ДРУГИМИ" in last, last)

    app2 = make_app()
    app2._start_picture_task()
    app2._picture_reply("one two three one two three " * 10)
    last2 = texts(app2)[-1]
    check("мало разных слов поймали", "Мало разных слов" in last2, last2)


def test_good():
    print("\n[4] Порог набран")
    app = make_app()
    app._start_picture_task()
    res = picture_task.check_description(GOOD, "A2")
    check("текст вообще годится", res["ok"], res)
    handled = app._picture_reply(GOOD)
    check("реплика обработана локально", handled is True)
    check("задание закрыто", app._picture is None)
    check("счётчик убран", app.input_bar.counter == 0, app.input_bar.counter)
    last = texts(app)[-1]
    check("сказано «принято»", "принято" in last, last)
    check("число букв в ответе", str(res["letters"]) in last, last)


def test_handle_text():
    print("\n[5] _handle_text при активном задании")
    source = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
    body = source[source.find("def _handle_text("):]
    body = body[:body.find("def _send_to_teacher(")]
    check("есть проверка задания до модели",
          "_picture_reply" in body and "_picture is not None" in body)
    check("проверка стоит ДО отправки учителю",
          body.find("_picture_reply") < body.find("_send_to_teacher("),
          (body.find("_picture_reply"), body.find("_send_to_teacher(")))

    clear = source[source.find("def clear_chat("):]
    clear = clear[:clear.find("def _show_panel(")]
    check("clear_chat сбрасывает задание", "self._picture = None" in clear)
    check("clear_chat убирает счётчик", "clear_counter" in clear)

    finish = source[source.find("def _on_lesson_finished("):]
    finish = finish[:finish.find("def _on_lesson_aborted(")]
    check("задание стартует в конце обычного урока",
          "_start_picture_task()" in finish)
    check("в ветках экзамена задания НЕТ",
          finish.count("_start_picture_task()") == 1,
          finish.count("_start_picture_task()"))


def test_unknown_level():
    print("\n[6] Уровень не определён")
    app = make_app(level="")
    app._start_picture_task()
    check("порог по умолчанию (A2 = 105)", app.input_bar.counter == 105,
          app.input_bar.counter)
    check("уровень задания — A2", (app._picture or {}).get("level") == "A2",
          app._picture)


def main():
    print("=" * 60)
    print("ЗАДАНИЕ С КАРТИНКОЙ: склейка с окном")
    print("=" * 60)
    test_start()
    test_short()
    test_repeat_and_few()
    test_good()
    test_handle_text()
    test_unknown_level()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛОВ: %d" % len(FAILED))
        for name in FAILED:
            print("  - " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
