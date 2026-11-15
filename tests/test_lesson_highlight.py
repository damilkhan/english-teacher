# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_HIGHLIGHT.PY — подсветка ошибок в реплике (§77)
# =========================================================
#   python tests\test_lesson_highlight.py
#
# Решение ученика 12.11.2026: при ошибке в уроке — выделение куска,
# клик по нему и карточка с правилом. Здесь проверяется ПЕРВЫЙ шаг.
#
# Без Tk: методы App зовём на заглушке (как tests/test_picture_flow.py).
#   1) speaking: ошибка из разбора красится в ЕГО реплике;
#   2) правка, которой в реплике нет, не красится (выдумка Аналитика);
#   3) chat-урок: не красим — там «молчим и копим»;
#   4) экзамен: не красим — подсветка была бы подсказкой;
#   5) нет ошибок / нет реплики / урок закрыт — тихо ничего.
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

import lesson as L                                    # noqa: E402
from ui.app import EnglishTeacherApp as App            # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  \u2705 " if ok else "  \u274c ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeChatView(object):
    """Запоминает, что и где покрасили."""

    def __init__(self, mark="m1"):
        self.mark = mark
        self.painted = []

    def last_user_mark(self):
        return self.mark

    def mark_message(self, mark, spans):
        self.painted.append((mark, list(spans)))
        return True


class FakeLesson(object):
    def __init__(self, lesson_type, active=True):
        self.session = types.SimpleNamespace(
            lesson_type=lesson_type, is_active=active)

    def current(self):
        return self.session


def make_app(lesson_type, text="my shoes is brown", active=True, mark="m1"):
    app = types.SimpleNamespace()
    app.chat_view = FakeChatView(mark)
    app.lesson = FakeLesson(lesson_type, active)
    app._last_student_text = text
    app._highlight_mistakes = types.MethodType(App._highlight_mistakes, app)
    return app


def result(errors):
    return {"ok": True, "move_type": "A", "move_status": "P", "errors": errors}


SHOES = [{"type": "grammar", "wrong": "is", "correct": "are", "rule": "verb_form"}]


def test_speaking_paints():
    print("\n[1] speaking: ошибка красится в реплике ученика")
    app = make_app("speaking")
    done = app._highlight_mistakes(result(SHOES))
    check("подсветка сработала", done == 1, done)
    check("реплика передана в mark_message", len(app.chat_view.painted) == 1,
          app.chat_view.painted)
    spans = app.chat_view.painted[0][1] if app.chat_view.painted else []
    check("кусок — именно 'is'", [app._last_student_text[i[0]:i[1]] for i in spans] == ["is"],
          spans)
    check("стиль err", spans and spans[0][2] == "err", spans)
    # §79: кусок несёт ПРАВИЛО ошибки — по нему клик открывает карточку.
    check("правило доехало до куска", spans and spans[0][3] == "verb_form", spans)
    check("и 'как надо' тоже", spans and spans[0][4] == "are", spans)


def test_unknown_correction_skipped():
    print("\n[2] Выдуманная правка не красится")
    app = make_app("speaking", text="i like colors this shirt")
    done = app._highlight_mistakes(
        result([{"type": "vocabulary", "wrong": "jacket", "correct": "shirt"}]))
    check("ничего не покрашено", done == 0, done)
    check("mark_message не звали", not app.chat_view.painted, app.chat_view.painted)


def test_chat_silent():
    print("\n[3] chat-урок: не красим (молчим и копим)")
    app = make_app("chat")
    check("подсветки нет", app._highlight_mistakes(result(SHOES)) == 0)
    check("mark_message не звали", not app.chat_view.painted, app.chat_view.painted)
    check("corrects_on_the_fly(chat) == False", L.corrects_on_the_fly("chat") is False)


def test_exam_silent():
    print("\n[4] Экзамен: не красим — это была бы подсказка")
    app = make_app("check")
    check("подсветки нет", app._highlight_mistakes(result(SHOES)) == 0)
    check("corrects_on_the_fly(check) == False", L.corrects_on_the_fly("check") is False)


def test_quiet_cases():
    print("\n[5] Молчаливые случаи")
    app = make_app("speaking")
    check("нет ошибок -> 0", app._highlight_mistakes(result([])) == 0)
    check("разбор не удался -> 0", app._highlight_mistakes({"ok": False}) == 0)
    check("пустая реплика -> 0",
          make_app("speaking", text="   ")._highlight_mistakes(result(SHOES)) == 0)
    check("урок закрыт -> 0",
          make_app("speaking", active=False)._highlight_mistakes(result(SHOES)) == 0)
    check("нет метки реплики -> 0",
          make_app("speaking", mark=None)._highlight_mistakes(result(SHOES)) == 0)
    check("ничего не покрашено за все случаи", not app.chat_view.painted)


def test_regex_guard():
    print("\n[6] Подсветка только там, где правки по ходу разрешены")
    check("speaking разрешает", L.corrects_on_the_fly("speaking") is True)
    check("неизвестный тип — как раньше (разрешает)",
          L.corrects_on_the_fly("whatever") is True)
    check("listening молчит", L.corrects_on_the_fly("listening") is False)


def main():
    print("=" * 60)
    print("ПОДСВЕТКА ОШИБОК В РЕПЛИКЕ (§77)")
    print("=" * 60)
    test_speaking_paints()
    test_unknown_correction_skipped()
    test_chat_silent()
    test_exam_silent()
    test_quiet_cases()
    test_regex_guard()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("  - " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
