# -*- coding: utf-8 -*-
# =========================================================
# TEST_VOCAB_REQUEST.PY — «давай повторим слова» открывает СЛОВА, а не урок
# =========================================================
# Живой баг 27.10.2026: ученик написал «let's to learn and repeat some words»,
# и приложение начало УРОК 1.4 (проверку блока) вместо окна слов — потому что
# автозапуск урока стоял ПЕРЕД проверкой просьбы о словах.
#
# Что проверяем (без окна и без модели):
#   1) распознавание просьбы: нужны И тема, И действие;
#   2) одиночное слово («слово», «flatbread») НЕ считается просьбой;
#   3) порядок в send_text: проверка слов стоит ДО автозапуска урока;
#   4) в уроке просьба о словах не перехватывается (там слова ведёт Джейн);
#   5) без урока просьба открывает окно слов.
# =========================================================

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

FAILED = []


def check(name, ok, detail=None):
    if ok:
        print("  \u2705 %s" % name)
    else:
        print("  \u274c %s  \u2192  %s" % (name, detail))
        FAILED.append(name)


# =========================================================
# 1. Распознавание просьбы
# =========================================================
def test_detect():
    print("\n[1] Просьба о словах распознаётся")
    from ui.app import _asks_for_words
    positive = [
        "let's to learn and repeat some words",
        "let's learn words",
        "давай повторим слова",
        "хочу поучить новые слова",
        "покажи карточки",
        "хочу заниматься лексикой",
        "show me words to repeat",
        "let's practice vocabulary",
        "начнём слова",
    ]
    for text in positive:
        check("«%s»" % text, _asks_for_words(text) is True, _asks_for_words(text))


# =========================================================
# 2. Одиночное слово — НЕ просьба (иначе сломается перевод)
# =========================================================
def test_negative():
    print("\n[2] Одиночное слово и обычные фразы — не просьба")
    from ui.app import _asks_for_words
    negative = [
        "слово",
        "слова",
        "flatbread",
        "lek",
        "как дела",
        "привет",
        "I like words in songs",
        "",
        None,
    ]
    for text in negative:
        check("«%s»" % text, _asks_for_words(text) is False, _asks_for_words(text))


# =========================================================
# 3. Порядок в send_text
# =========================================================
def test_order():
    print("\n[3] Проверка слов стоит ДО автозапуска урока")
    path = os.path.join(BASE, "ui", "app.py")
    with open(path, "r", encoding="utf-8") as fh:
        body = fh.read()
    start = body.find("    def send_text(self):")
    check("send_text найден", start >= 0)
    if start < 0:
        return
    chunk = body[start:start + 2000]
    words_at = chunk.find("self._open_words_on_request(text)")
    lesson_at = chunk.find("self._maybe_start_auto_lesson(text")
    check("вызов проверки слов есть", words_at >= 0, words_at)
    check("вызов автозапуска есть", lesson_at >= 0, lesson_at)
    check("слова раньше урока", 0 <= words_at < lesson_at, (words_at, lesson_at))
    check("у метода есть защита «идёт урок»",
          "if self.lesson.is_active or not self.profile_ready:" in body,
          "нет строки защиты")


# =========================================================
# 4. В уроке не перехватываем
# =========================================================
def test_in_lesson():
    print("\n[4] Во время урока слова не перехватываются")
    from ui.app import EnglishTeacherApp

    class App:
        lesson = type("L", (), {"is_active": True})()
        profile_ready = True
        teacher_name = "Verbot"
        messages = []

        def add_message(self, *args, **kwargs):
            self.messages.append(args)

        def review_vocabulary(self):
            raise AssertionError("окно слов не должно открываться в уроке")

    result = EnglishTeacherApp._open_words_on_request(App(), "давай повторим слова")
    check("в уроке вернулось False", result is False, result)
    check("в чат ничего не писали", App.messages == [], App.messages)


def test_opened():
    print("\n[5] Без урока просьба открывает окно слов")
    from ui.app import EnglishTeacherApp

    class App:
        lesson = type("L", (), {"is_active": False})()
        profile_ready = True
        teacher_name = "Verbot"
        messages = []
        opened = []

        def add_message(self, *args, **kwargs):
            self.messages.append(args)

        def review_vocabulary(self):
            self.opened.append(1)
            return "panel"

    app = App()
    result = EnglishTeacherApp._open_words_on_request(app, "давай повторим слова")
    check("вернулось True (реплику обработали)", result is True, result)
    check("окно слов открыли", app.opened == [1], app.opened)
    check("в чат ушли две строки (моя и ответ)", len(app.messages) == 2, app.messages)


def main():
    print("=" * 60)
    test_detect()
    test_negative()
    test_order()
    test_in_lesson()
    test_opened()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛОВ: %d" % len(FAILED))
        for name in FAILED:
            print("  \u274c %s" % name)
    else:
        print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
