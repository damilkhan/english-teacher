# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PHOTO_CHECK.PY — мягкая проверка грамматики описания фото
# =========================================================
#   python tests\test_photo_check.py
#
# Задание «опиши фото» принимает ответ по ДЛИНЕ (picture_task.py), поэтому
# ошибки вроде «they are staying near the bus» проходили молча. Здесь
# проверяем второй слой (§42): модель возвращает исправленный ТЕКСТ, правки
# считает КОД, зачёт задания не отменяется.
#
#   1) правки находятся и печатаются по-человечески;
#   2) верный текст — «no grammar mistakes», правок нет;
#   3) смена регистра («i» → «I») правкой НЕ считается;
#   4) если модель ПЕРЕПИСАЛА текст — разбор не показываем (лучше тишина);
#   5) метки «Corrected:», кавычки, звёздочки снимаются;
#   6) правки превращаются в разбор Аналитика (для профиля);
#   7) склейка с окном: зачёт → проверка в фоне → реплика в чат;
#   8) выключатель config.PICTURE_CHECK_ENABLED и молчание при сбое модели.
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

import config                                          # noqa: E402
import photo_check                                     # noqa: E402
import profile_store                                   # noqa: E402
from ui.app import EnglishTeacherApp as App            # noqa: E402

FAILED = []

# Ответ ученика с живой ошибкой (скриншот 26.10.2026) и исправление,
# которого мы ждём от модели.
STUDENT = ("i see in this photo a bus station. there is a white bus and three or more "
           "people. they are staying near the bus. possible they are waiting when the "
           "doors of the bus will open")
CORRECTED = ("I see a bus stop in this photo. There is a white bus and three or more "
             "people. They are standing near the bus. It is possible they are waiting "
             "for the doors of the bus to open.")
GOOD_TEXT = ("There are many shops on the street. People are walking in the wet "
             "street and the sky is grey.")


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def test_changes():
    print("\n[1] Правки находятся и печатаются")
    changes = photo_check.word_changes(STUDENT, CORRECTED)
    pairs = [(c["wrong"].lower(), c["right"].lower()) for c in changes]
    check("правки вообще есть", len(changes) >= 3, changes)
    check("staying → standing",
          any("staying" in w and "standing" in r for w, r in pairs), pairs)
    check("when → for", any(w == "when" and r == "for" for w, r in pairs), pairs)
    check("в правках нет пустых пар",
          all(c["wrong"] or c["right"] for c in changes), changes)

    data = photo_check.report(STUDENT, CORRECTED)
    check("разбор показать можно", data["ok"], data)
    check("первая строка — исправленный текст",
          data["lines"][0].startswith("Better: ") and "bus stop" in data["lines"][0],
          data["lines"][:1])
    check("правки идут строками «· »",
          all(line.startswith("·") for line in data["lines"][1:]),
          data["lines"])
    check("правок в списке не больше MAX_NOTES (или есть «+N more»)",
          len(data["lines"]) - 1 <= photo_check.MAX_NOTES + 1, data["lines"])
    check("длинная правка обрезается с «…»",
          "\u2026" in photo_check._short(" ".join(["word"] * 20)),
          photo_check._short(" ".join(["word"] * 20)))


def test_correct_text():
    print("\n[2] Текст без ошибок")
    data = photo_check.report(GOOD_TEXT, GOOD_TEXT)
    check("показываем можно", data["ok"], data)
    check("правок нет", data["changes"] == [], data["changes"])
    check("одна строка похвалы", len(data["lines"]) == 1, data["lines"])
    check("в похвале «no grammar mistakes»",
          "no grammar mistakes" in data["lines"][0].lower(), data["lines"])


def test_case_only():
    print("\n[3] Смена регистра — не правка")
    data = photo_check.report("i see a bus and two people",
                              "I see a bus and two people")
    check("правок нет", data["changes"] == [], data["changes"])
    check("показана похвала", "no grammar mistakes" in data["lines"][0].lower(),
          data["lines"])


def test_drift():
    print("\n[4] Модель переписала текст — молчим")
    rewrite = ("The photograph shows an urban scene with retail establishments and "
               "pedestrians on a rainy day.")
    data = photo_check.report(GOOD_TEXT, rewrite)
    check("разбор НЕ показываем", data["ok"] is False, data)
    check("строк для чата нет", data["lines"] == [], data["lines"])
    check("пустой ответ модели", photo_check.report(GOOD_TEXT, "")["ok"] is False)
    check("ответ вдвое длиннее",
          photo_check.report(GOOD_TEXT, GOOD_TEXT + " " + GOOD_TEXT)["ok"] is False)
    check("is_sane: своё же предложение — да",
          photo_check.is_sane(GOOD_TEXT, GOOD_TEXT) is True)


def test_clean():
    print("\n[5] Разбор ответа модели")
    cases = [
        ("Corrected: I see a bus.", "I see a bus."),
        ('"I see a bus."', "I see a bus."),
        ("Here: *I see a bus.*", "I see a bus."),
        ("Correction - i see a bus", "i see a bus"),
        ("", ""),
    ]
    for raw, want in cases:
        got = photo_check.clean_corrected(raw)
        check("clean_corrected(%r)" % raw, got == want, "получили %r" % got)
    fence = "```\nI see a bus.\n```"
    check("блок ``` снимается",
          photo_check.clean_corrected(fence) == "I see a bus.",
          photo_check.clean_corrected(fence))
    many = "I see a bus.\nIt is red."
    check("берём первую строку",
          photo_check.clean_corrected(many) == "I see a bus.",
          photo_check.clean_corrected(many))


def test_analysis():
    print("\n[6] Правки → разбор для профиля")
    data = photo_check.report(STUDENT, CORRECTED)
    analysis = photo_check.analysis_from(data)
    errors = analysis["errors"]
    check("ошибки есть (не больше числа правок)",
          0 < len(errors) <= len(data["changes"]), errors)
    check("тип у всех grammar", all(e["type"] == "grammar" for e in errors), errors)
    check("есть поля wrong/correct", all(e["wrong"] and e["correct"] for e in errors),
          errors)
    check("move_type A (реплика удалась)", analysis["move_type"] == "A", analysis)
    check("пометка photo", analysis.get("photo") is True, analysis)
    empty = photo_check.analysis_from(photo_check.report(GOOD_TEXT, GOOD_TEXT))
    check("верный текст — ошибок ноль", empty["errors"] == [], empty)


# ---------- склейка с окном (без Tk) ----------
class FakeChat:
    def __init__(self):
        self.sent = []
        self.spans_by_mark = {}
        self.last_spans = None
        self._last_user = None

    def add_message(self, sender, text, picture=None, spans=None):
        self.sent.append((sender, text))
        self.last_spans = spans
        mark = "msg_%d" % len(self.sent)
        self.spans_by_mark[mark] = list(spans or ())
        if sender == "Вы":
            self._last_user = mark
        return mark

    def message_text(self, mark):
        try:
            return self.sent[int(mark.split("_")[1]) - 1][1]
        except Exception:
            return ""

    def last_user_mark(self):
        return self._last_user

    def mark_message(self, mark, spans):
        self.spans_by_mark[mark] = list(spans or ())
        return bool(spans)


class FakeInputBar:
    def set_counter(self, total):
        self.counter = int(total or 0)

    def clear_counter(self):
        self.counter = 0


class FakeLLM:
    """Модель-заглушка: возвращает заданный ответ или ошибку."""

    def __init__(self, ok=True, text=""):
        self.ok, self.text, self.calls = ok, text, []

    def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.ok, self.text


def make_app(llm=None):
    app = types.SimpleNamespace()
    app.current_user = {"id": "u1", "name": "Дамиль", "level": "A2"}
    app.teacher_name = "Verbot"
    app.chat = FakeChat()
    app.chat_view = app.chat
    app.input_bar = FakeInputBar()
    app.input_bar.counter = 0
    app._picture = {"level": "A2", "threshold": 105, "key": "test"}
    app.llm = llm or FakeLLM(True, CORRECTED)
    app._dispatch = lambda fn: fn()
    app.speech = []
    app._say_after_current = (lambda text, mark=None:
                             app.speech.append((text, mark)))
    app.add_message = types.MethodType(App.add_message, app)
    app._picture_level = types.MethodType(App._picture_level, app)
    app._picture_reply = types.MethodType(App._picture_reply, app)
    app._start_picture_check = types.MethodType(App._start_picture_check, app)
    app._picture_check_worker = types.MethodType(App._picture_check_worker, app)
    app._apply_picture_check = types.MethodType(App._apply_picture_check, app)
    app._remember_photo_mistakes = types.MethodType(
        App._remember_photo_mistakes, app)
    app._mark_student_text = types.MethodType(App._mark_student_text, app)
    return app


def test_glue():
    print("\n[7] Склейка: зачёт → проверка → реплика в чат")
    saved = []
    original = profile_store.record_analysis
    profile_store.record_analysis = lambda analysis, text, resp="", uid=None: (
        saved.append((analysis, text, uid)) or [])
    try:
        app = make_app()
        started = []
        app._start_picture_check = lambda text: started.append(text) or True
        handled = app._picture_reply(STUDENT)
        check("задание засчитано", handled is True and app._picture is None)
        check("проверка запущена с текстом ученика", started == [STUDENT], started)
        check("счётчик букв убран", app.input_bar.counter == 0)

        app2 = make_app()
        app2._picture_check_worker(STUDENT)      # воркер вызываем напрямую
        texts = [t for _, t in app2.chat.sent]
        check("воркер спросил модель", len(app2.llm.calls) == 1, app2.llm.calls)
        messages, kwargs = app2.llm.calls[0]
        check("в запросе есть текст ученика",
              STUDENT in messages[-1]["content"], messages)
        check("просим исправленный текст (system)",
              "corrected text only" in messages[0]["content"].lower(),
              messages[0]["content"][:120])
        check("temperature 0 (без фантазии)", kwargs.get("temperature") == 0.0, kwargs)
        check("в чате появился разбор", len(texts) == 1 and "Better:" in texts[0],
              texts)
        check("правки записаны в профиль", len(saved) == 1, saved)
        check("записаны к ученику u1", saved and saved[0][2] == "u1", saved)
        check("в профиль ушли именно правки",
              saved and len(saved[0][0]["errors"]) >= 3,
              saved[0][0] if saved else None)
    finally:
        profile_store.record_analysis = original


def test_quiet_failures():
    print("\n[8] Выключатель и сбои модели — молчим")
    original_flag = config.PICTURE_CHECK_ENABLED
    try:
        config.PICTURE_CHECK_ENABLED = False
        app = make_app()
        check("выключено — проверка не стартует",
              app._start_picture_check(STUDENT) is False)
        config.PICTURE_CHECK_ENABLED = True
        bad = make_app(llm=FakeLLM(False, "таймаут"))
        bad._picture_check_worker(STUDENT)
        check("модель не ответила — в чат ничего", bad.chat.sent == [], bad.chat.sent)
        drift = make_app(llm=FakeLLM(True,
                               "The photo shows an urban scene with people."))
        drift._picture_check_worker(STUDENT)
        check("модель переписала текст — в чат ничего",
              drift.chat.sent == [], drift.chat.sent)
        empty = make_app()
        check("пустой текст не проверяем",
              empty._start_picture_check("   ") is False)
        boom = make_app(llm=types.SimpleNamespace(
            complete=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("сеть"))))
        boom._picture_check_worker(STUDENT)
        check("исключение модели не роняет приложение",
              boom.chat.sent == [], boom.chat.sent)
    finally:
        config.PICTURE_CHECK_ENABLED = original_flag


def test_spans():
    print("\n[9] Раскраска: ошибки красным, исправления зелёным")
    data = photo_check.report(STUDENT, CORRECTED)
    text = data["text"]
    check("раскраска есть", len(data["spans"]) >= 2, data["spans"])
    good = [text[a:b] for a, b, st in data["spans"] if st == "ok"]
    bad = [text[a:b] for a, b, st in data["spans"] if st == "err"]
    check("исправленный текст красится целиком",
          any(piece.startswith("I see a bus stop") for piece in good), good)
    check("верный вариант правки зелёный",
          any("standing" in piece for piece in good), good)
    check("неверное слово красное", any("staying" in piece for piece in bad), bad)
    check("все куски внутри текста",
          all(0 <= a < b <= len(text) for a, b, _ in data["spans"]),
          data["spans"])
    # Смещения считаются по тексту реплики, а эмодзи в облачке — КАРТИНКА
    # (один символ в индексах tk.Text, ноль в тексте). Поэтому в этом
    # сообщении эмодзи быть не должно — проверяем по-настоящему, через
    # разборщик, а не по коду символа («→» — не эмодзи, а обычный глиф).
    from ui import emoji_render
    parts = emoji_render.split(text)
    check("в тексте нет эмодзи-картинок (иначе смещения уедут)",
          not any(kind is True for kind, _chunk in parts),
          [chunk for kind, chunk in parts if kind is True])
    check("верный текст — раскрашивать нечего",
          photo_check.report(GOOD_TEXT, GOOD_TEXT)["spans"] == [])

    spans = photo_check.spans_for_changes(STUDENT, data["changes"])
    check("ошибки найдены в тексте УЧЕНИКА", len(spans) >= 1, spans)
    check("все они красные", all(st == "err" for _, _, st in spans), spans)
    check("куски — настоящие слова ученика",
          all(STUDENT[a:b].strip() for a, b, _ in spans),
          [(a, b) for a, b, _ in spans])
    check("куски идут по порядку и не наезжают",
          all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1)),
          spans)
    check("пустые правки — пустая раскраска",
          photo_check.spans_for_changes("I see a bus.", []) == [])
    check("мусор в правках не ломает",
          photo_check.spans_for_changes("abc", [None, {}, {"wrong": ""}]) == [])


def test_voice_and_marks():
    print("\n[10] Голос и подсветка в живом чате")
    saved = []
    original = profile_store.record_analysis
    profile_store.record_analysis = lambda *a, **k: (saved.append(a) or [])
    try:
        app = make_app()
        app._start_picture_check = lambda text: False
        app._picture_reply(STUDENT)
        check("зачёт озвучен",
              bool(app.speech) and app.speech[-1][0].startswith("Task accepted"),
              app.speech)
        check("у зачёта есть метка (значок 🔊)",
              bool(app.speech) and app.speech[-1][1] is not None, app.speech)

        app2 = make_app()
        app2.add_message("Вы", STUDENT)       # реплика ученика, как в жизни
        app2._picture_check_worker(STUDENT)   # воркер проверки — напрямую
        texts = [t for _, t in app2.chat.sent]
        check("разбор появился в чате",
              any(t.startswith("Better: ") for t in texts), texts)
        check("у разбора есть раскраска", bool(app2.chat.last_spans),
              app2.chat.last_spans)
        check("голосом читают исправленный текст",
              bool(app2.speech) and app2.speech[-1][0].startswith("Better."),
              app2.speech)
        check("у разбора есть метка (значок 🔊)",
              bool(app2.speech) and app2.speech[-1][1] is not None, app2.speech)
        mark = app2.chat.last_user_mark()
        check("реплика ученика запомнена", mark is not None, mark)
        user_spans = app2.chat.spans_by_mark.get(mark) or []
        check("ошибки в реплике ученика подсвечены",
              bool(user_spans) and all(st == "err" for _, _, st in user_spans),
              user_spans)

        quiet = make_app(llm=FakeLLM(True, GOOD_TEXT))
        quiet.add_message("Вы", GOOD_TEXT)
        quiet._picture_check_worker(GOOD_TEXT)
        check("верный текст: голос хвалит без ошибок",
              bool(quiet.speech) and quiet.speech[-1][0].startswith("No grammar"),
              quiet.speech)
        check("верный текст: ничего не красим",
              not (quiet.chat.spans_by_mark.get(quiet.chat.last_user_mark()) or []),
              quiet.chat.spans_by_mark)
    finally:
        profile_store.record_analysis = original


def main():
    print("=" * 60)
    print("ПРОВЕРКА ГРАММАТИКИ В ОПИСАНИИ ФОТО")
    print("=" * 60)
    test_changes()
    test_correct_text()
    test_case_only()
    test_drift()
    test_clean()
    test_analysis()
    test_glue()
    test_quiet_failures()
    test_spans()
    test_voice_and_marks()
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
