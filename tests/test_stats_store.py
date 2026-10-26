# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_STATS_STORE.PY — база ошибок ученика (stats_store.py, §46)
# =========================================================
#   python tests\test_stats_store.py
#
# Что проверяем:
#   1) путь к базе: profiles/stats_<id>.db, без ученика — stats_student.db;
#   2) запись ошибок и чтение обратно (rule/type/source/lesson сохраняются);
#   3) мусор в списке не пишется, пустая пара «было/стало» не пишется;
#   4) перенос старых записей из JSON-профиля — ОДИН раз, без дублей;
#   5) clear() чистит таблицу;
#   6) record_analysis пишет в ДВА места: JSON (с полем rule) и SQLite.
# =========================================================

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import profile_store              # noqa: E402
import stats_store                # noqa: E402
import user_manager               # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  OK   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class temp_profile_dir:
    """Временная папка профилей: реальные файлы ученика не трогаем."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_stats_")
        self.real = (user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE)
        user_manager.PROFILES_DIR = self.dir
        user_manager.LAST_USER_FILE = os.path.join(self.dir, "last_user.txt")
        profile_store.set_active_user(None)
        stats_store.forget_migrated()
        return self.dir

    def __exit__(self, *exc):
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE = self.real
        profile_store.set_active_user(None)
        stats_store.forget_migrated()


# =========================================================
# 1. Путь к базе
# =========================================================
def test_paths():
    print("\n[1] Путь к базе")
    with temp_profile_dir() as folder:
        path = stats_store.db_path(3)
        check("имя файла stats_3.db", path.endswith("stats_3.db"), path)
        check("файл лежит в папке профилей", os.path.dirname(path) == folder, path)
        check("id строкой тоже работает", stats_store.db_path("3").endswith("stats_3.db"))
        legacy = stats_store.db_path("не число")
        check("мусор вместо id -> запасной файл", legacy.endswith(stats_store.LEGACY_DB_NAME), legacy)


# =========================================================
# 2. Запись и чтение
# =========================================================
def test_add_and_rows():
    print("\n[2] Запись и чтение")
    with temp_profile_dir():
        uid = 1
        check("сначала пусто", stats_store.count(uid) == 0, stats_store.count(uid))
        added = stats_store.add_mistakes([
            {"wrong": "I make", "correct": "I made", "rule": "past_simple",
             "type": "grammar", "source": "chat", "lesson": "city/1.1", "date": "2026-10-20T10:00:00"},
            {"wrong": "normaly", "correct": "normally", "rule": "spelling",
             "type": "vocabulary", "source": "photo"},
        ], uid)
        check("записано две строки", added == 2, added)
        check("count совпадает", stats_store.count(uid) == 2, stats_store.count(uid))
        rows = stats_store.rows(uid)
        check("чтение вернуло обе", len(rows) == 2, rows)
        first = rows[0]
        check("sorted по дате (свежая первой)", first.get("wrong") == "normaly", first)
        second = rows[1]
        check("rule сохранён", second.get("rule") == "past_simple", second)
        check("lesson сохранён", second.get("lesson") == "city/1.1", second)
        check("source сохранён", second.get("source") == "chat", second)
        check("порядок по возрастанию даты",
              stats_store.rows(uid, newest_first=False)[0].get("wrong") == "I make")


# =========================================================
# 3. Мусор не пишется
# =========================================================
def test_junk():
    print("\n[3] Мусор не пишется")
    with temp_profile_dir():
        uid = 2
        check("пустой список -> 0", stats_store.add_mistakes([], uid) == 0)
        check("не список словарей -> 0", stats_store.add_mistakes(["нет", 5], uid) == 0)
        check("пара без слов -> 0",
              stats_store.add_mistakes([{"wrong": "", "correct": "", "rule": "other"}], uid) == 0)
        check("база осталась пустой", stats_store.count(uid) == 0, stats_store.count(uid))
        stats_store.add_mistakes([{"wrong": "go", "correct": "went"}], uid)
        row = stats_store.rows(uid)[0]
        check("правило по умолчанию - other", row.get("rule") == "other", row)
        check("тип по умолчанию - grammar", row.get("type") == "grammar", row)
        check("дата подставлена", bool(row.get("date")), row)


# =========================================================
# 4. Перенос старых записей из JSON
# =========================================================
def test_migration():
    print("\n[4] Перенос старых записей из JSON")
    with temp_profile_dir():
        uid = 4
        profile = {
            "mistakes": {
                "grammar": [
                    {"date": "2026-10-01T10:00:00", "wrong": "I make", "correct": "I made", "note": "tense"},
                    {"date": "2026-10-02T10:00:00", "wrong": "two book", "correct": "two books", "note": "plural"},
                ],
                "vocabulary": [
                    {"date": "2026-10-03T10:00:00", "wrong": "normaly", "correct": "normally", "note": ""},
                ],
                "pronunciation": [],
            }
        }
        moved = stats_store.ensure_migrated(profile, uid)
        check("перенесено три записи", moved == 3, moved)
        rows = stats_store.rows(uid)
        rules = sorted(r.get("rule") for r in rows)
        check("правила угаданы", rules == ["past_simple", "plural", "spelling"], rules)
        check("повторный перенос ничего не делает",
              stats_store.ensure_migrated(profile, uid) == 0)
        check("дублей нет", stats_store.count(uid) == 3, stats_store.count(uid))

        stats_store.forget_migrated()
        check("непустая база не переносится заново",
              stats_store.ensure_migrated(profile, uid) == 0)
        check("по-прежнему три записи", stats_store.count(uid) == 3, stats_store.count(uid))


# =========================================================
# 5. clear()
# =========================================================
def test_clear():
    print("\n[5] clear()")
    with temp_profile_dir():
        uid = 5
        stats_store.add_mistakes([{"wrong": "go", "correct": "went"}], uid)
        check("запись есть", stats_store.count(uid) == 1)
        check("clear вернул True", stats_store.clear(uid) is True)
        check("таблица пустая", stats_store.count(uid) == 0, stats_store.count(uid))


# =========================================================
# 6. record_analysis пишет в ДВА места
# =========================================================
def test_record_analysis_writes_both():
    print("\n[6] record_analysis пишет в JSON и SQLite")
    with temp_profile_dir():
        uid = 6
        analysis = {
            "move_type": "A", "move_status": "P",
            "errors": [{"type": "grammar", "wrong": "you not have",
                        "correct": "you don't have", "rule": "aux_verb", "note": "aux"}],
            "topics": [], "note": "", "ok": True, "source": "model",
        }
        profile_store.record_analysis(analysis, "you not have time", "", uid)
        prog = profile_store.load(uid)
        card = prog["mistakes"]["grammar"][-1]
        check("в JSON есть правило", card.get("rule") == "aux_verb", card)
        check("в базе одна запись", stats_store.count(uid) == 1, stats_store.count(uid))
        row = stats_store.rows(uid)[0]
        check("правило в базе", row.get("rule") == "aux_verb", row)
        check("источник chat", row.get("source") == "chat", row)

        photo = {"move_type": "A", "move_status": "A", "photo": True,
                 "errors": [{"type": "grammar", "wrong": "possible waiting",
                             "correct": "possibly waiting"}],
                 "topics": [], "note": ""}
        profile_store.record_analysis(photo, "they are possible waiting", "", uid)
        row = stats_store.rows(uid)[0]
        check("источник фото", row.get("source") == "photo", row)
        check("правило для фото угадано", row.get("rule") in ("spelling", "word_choice"), row)
        check("в базе уже две записи", stats_store.count(uid) == 2, stats_store.count(uid))


def main():
    test_paths()
    test_add_and_rows()
    test_junk()
    test_migration()
    test_clear()
    test_record_analysis_writes_both()
    print("\n" + ("ВСЁ ПРОЙДЕНО" if not FAILED else "ПРОВАЛЕНО: %d" % len(FAILED)))
    for name in FAILED:
        print("  - " + name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
