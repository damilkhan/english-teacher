# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_DICT.PY — словарь во время урока (без экрана)
# =========================================================
#   python tests\test_lesson_dict.py
#
# ЗАЧЕМ. Ученик во время урока «только голосом» не помнит слово и хочет
# посмотреть перевод. Раньше поле ввода было ЗАПРЕТОВАНО целиком: ни буквы,
# ни перевода. Решение ученика (23.10.2026): замок урока отнимает ОТПРАВКУ
# английского, но НЕ ввод. Русское слово → «💡 Перевести» → ученик ЧИТАЕТ
# английский вариант вслух, и только так отвечает преподавателю.
#
# Проверяем:
#   1) has_cyrillic — «просит перевода» или «это ответ»;
#   2) решение send_text: урок + русское слово → перевод (в чат НИЧЕГО),
#      урок + английский → записка «говори в микрофон», вне урока — как было;
#   3) подсказки урока (lesson.locked_hint) во всех трёх типах зовут написать
#      по-русски, а не молчать.
# Модель, микрофон и сеть не нужны.
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

import lesson                                                   # noqa: E402
from ui.app import EnglishTeacherApp, LOCKED_TEXT_NOTE          # noqa: E402
from ui.widgets.input_bar import has_cyrillic                   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeInput:
    """Поле ввода без Tk: помнит текст, замок и сколько раз его чистили."""

    def __init__(self, text="", locked=False):
        self.text = str(text)
        self.is_locked = bool(locked)
        self.cleared = 0

    def get_text(self):
        return self.text

    def clear_text(self):
        self.cleared += 1
        self.text = ""


def fake_app(text, locked):
    """Ученик, у которого есть только то, что нужно send_text()."""
    box = {"messages": [], "hints": [], "handled": [], "started": []}
    app = types.SimpleNamespace(
        input_bar=FakeInput(text, locked),
        teacher_name="Verbot",
        add_message=lambda who, what: box["messages"].append((who, what)),
        _maybe_start_auto_lesson=lambda t, who: box["started"].append(t) or False,
        _show_translation_hint=lambda t: box["hints"].append(t),
        _handle_text=lambda t, skip_translate=False: box["handled"].append(t),
    )
    app._wants_translation = lambda t: EnglishTeacherApp._wants_translation(app, t)
    return app, box


def main():
    # ---------- 1. Кириллица: просьба о переводе или ответ ----------
    print("[1] has_cyrillic")
    check("«ключ» — русское слово", has_cyrillic("ключ") is True)
    check("«key» — английское", has_cyrillic("key") is False)
    check("смешанное — считается русским", has_cyrillic("I need ключ") is True)
    check("«Ёлка» (заглавная Ё)", has_cyrillic("Ёлка") is True)
    check("цифры и знаки — не русский", has_cyrillic("123 !? ok") is False)
    check("пусто — не русский", has_cyrillic("") is False)
    check("None не падает", has_cyrillic(None) is False)

    # ---------- 2. Решение send_text ----------
    print("\n[2] Что делает send_text")

    app, box = fake_app("ключ", locked=True)
    EnglishTeacherApp.send_text(app)
    check("урок + русское слово → перевод", box["hints"] == ["ключ"], box["hints"])
    check("в чат ничего не пишем (русское не ответ)", box["messages"] == [], box["messages"])
    check("в диалог к преподавателю не уходит", box["handled"] == [], box["handled"])
    check("урок не запускается заново", box["started"] == [], box["started"])
    check("поле очищено", app.input_bar.cleared == 1, app.input_bar.cleared)

    app, box = fake_app("I need a key", locked=True)
    EnglishTeacherApp.send_text(app)
    check("урок + английский → записка «говори в микрофон»",
          box["messages"] == [("Verbot", LOCKED_TEXT_NOTE)], box["messages"])
    check("английский в уроке НЕ уходит в диалог", box["handled"] == [], box["handled"])
    check("и перевода не просит", box["hints"] == [], box["hints"])
    check("набранное не стираем (ученик сам решит)",
          app.input_bar.cleared == 0, app.input_bar.cleared)

    app, box = fake_app("I need a key", locked=False)
    EnglishTeacherApp.send_text(app)
    check("вне урока английский идёт в диалог",
          box["handled"] == ["I need a key"], box["handled"])
    app, box = fake_app("ключ", locked=False)
    EnglishTeacherApp.send_text(app)
    check("вне урока «ключ» → перевод", box["hints"] == ["ключ"], box["hints"])
    check("вне урока перевод не пишется в чат", box["messages"] == [], box["messages"])

    # пустое поле: ничего не происходит вообще
    app, box = fake_app("", locked=True)
    EnglishTeacherApp.send_text(app)
    check("пустое поле — тишина",
          not box["messages"] and not box["hints"] and not box["handled"], box)

    # ---------- 3. Подсказки урока ----------
    print("\n[3] Подсказка в поле во время урока")
    # ЭКЗАМЕН (check) здесь больше не в списке: решением ученика 24.10.2026
    # на экзамене подсказок нет вообще — его проверки в tests/test_exam_lesson.py.
    for kind, label in (("speaking", "говорение"),
                        ("listening", "рассказ")):
        hint = lesson.locked_hint(kind)
        check("%s: подсказка зовёт написать по-русски" % label,
              "по-русски" in hint, hint)
        check("%s: подсказка зовёт говорить голосом" % label,
              "голосом" in hint or "микрофон" in hint, hint)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
