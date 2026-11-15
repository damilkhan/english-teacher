# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_STT_WORDS.PY — свои слова для распознавания (§78)
# =========================================================
#   python tests\test_stt_words.py
#
# Живой случай 15.11.2026: «Balance Tower» записывалось как «balanced tower»,
# «balancing tower», «Balenci Tower» — 7 реплик подряд, ученик злился.
# Замер на его же записях (logs/stt, 7 файлов): без подсказки неверно,
# с подсказкой верно 6 из 7. Значит лечится списком своих слов.
#
# Проверяем: файл data/stt_words.txt читается, «#» и пустые строки
# пропускаются, повторы склеиваются, кэш обновляется по времени изменения,
# ключевые слова фото идут в подсказку, все источники склеиваются в строку.
# =========================================================

import os
import sys
import tempfile
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
from ui.app import EnglishTeacherApp as App            # noqa: E402

FAILED = []
BASE = getattr(config, "BASE_DIR", ROOT)


def check(name, ok, detail=""):
    print(("  \u2705 " if ok else "  \u274c ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def make_app(picture=None):
    app = types.SimpleNamespace()
    app.current_user = {"name": "Дамиль", "name_latin": "Damil"}
    app._vocab_stt_card = lambda: None
    app._scene_stt_words = lambda: []
    app._lesson_stt_words = lambda: []
    app._picture = picture
    for name in ("_stt_hotwords", "_my_stt_words", "_picture_stt_words"):
        setattr(app, name, types.MethodType(getattr(App, name), app))
    return app


def write_words(text):
    path = os.path.join(BASE, "data", "stt_words.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def main():
    print("=" * 60)
    print("СВОИ СЛОВА ДЛЯ РАСПОЗНАВАНИЯ")
    print("=" * 60)
    path = os.path.join(BASE, "data", "stt_words.txt")
    backup = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            backup = fh.read()
    try:
        print("\n[1] Файл читается, комментарии и пустые строки пропускаются")
        write_words("# comment\n\nBalance Tower\n   \nAstrakhan\n")
        app = make_app()
        words = app._my_stt_words()
        check("два слова", words == ["Balance Tower", "Astrakhan"], words)
        check("комментарий не попал", "# comment" not in words, words)

        print("\n[2] Повторы склеиваются, лимит 40")
        write_words("\n".join(["word%d" % i for i in range(50)] + ["word0"]))
        words = make_app()._my_stt_words()
        check("не больше 40", len(words) == 40, len(words))
        check("первое слово одно", words.count("word0") == 1, words[:3])

        print("\n[3] Правка файла видна БЕЗ перезапуска (кэш по mtime)")
        write_words("Balance Tower\n")
        app = make_app()
        check("сначала одно слово", app._my_stt_words() == ["Balance Tower"],
              app._my_stt_words())
        os.utime(path, (1, 1))          # сдвигаем время изменения
        write_words("Balance Tower\nAstrakhan\n")
        check("после правки два слова",
              app._my_stt_words() == ["Balance Tower", "Astrakhan"],
              app._my_stt_words())

        print("\n[4] Файла нет — тихо пусто")
        os.remove(path)
        check("пустой список", make_app()._my_stt_words() == [])

        print("\n[5] Ключевые слова фото")
        app = make_app({"points": ["tower", "big building", "sky", "x"]})
        check("слова фото", app._picture_stt_words() == ["tower", "big building", "sky"],
              app._picture_stt_words())
        check("без фото пусто", make_app(None)._picture_stt_words() == [])

        print("\n[6] Все источники склеиваются в одну строку")
        write_words("Balance Tower\n")
        app = make_app({"points": ["tower"]})
        hot = app._stt_hotwords()
        check("имя ученика есть", "Дамиль" in hot, hot)
        check("слово фото есть", "tower" in hot, hot)
        check("своё слово есть", "Balance Tower" in hot, hot)
        check("это строка через запятую", isinstance(hot, str) and "," in hot, hot)
    finally:
        if backup is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(backup)

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
