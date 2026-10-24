# =========================================================
# TESTS/TEST_EXAM_PROFILE.PY — балл экзамена в профиле
# =========================================================
#   python tests\test_exam_profile.py
#
# ЗАЧЕМ. Решение ученика: «в профиль идёт ЛУЧШИЙ балл, пересдачи без
# ограничений». Это правило живёт в profile_store.record_exam, и если оно
# сломается, ученик потеряет сданный экзамен после неудачной пересдачи.
#
# Файлы профиля в тесте НЕ трогаем: подменяем load/_write заплатками.
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import profile_store                                             # noqa: E402

FAILED = []


class FakeStore:
    """Профиль в памяти вместо файла на диске."""

    def __init__(self):
        self.profile = {"exams": {}}
        self.writes = 0

    def install(self):
        self._load, self._write, self._path = (
            profile_store.load, profile_store._write, profile_store.progress_path)
        profile_store.load = lambda user_id=None: self.profile
        profile_store._write = self._fake_write
        profile_store.progress_path = lambda user_id=None: "<память>"
        return self

    def _fake_write(self, profile, path=None):
        self.writes += 1
        self.profile = profile
        return True

    def remove(self):
        profile_store.load = self._load
        profile_store._write = self._write
        profile_store.progress_path = self._path


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("[1] record_exam: балл, сдача и число попыток")
    store = FakeStore().install()
    try:
        entry = profile_store.record_exam("desert/1.4", 4.0, False)
        check("первая попытка записана", entry["score"] == 4.0, entry)
        check("не сдал → passed False", entry["passed"] is False, entry)
        check("попыток 1", entry["attempts"] == 1, entry)
        check("профиль записан на диск один раз", store.writes == 1, store.writes)

        entry = profile_store.record_exam("desert/1.4", 8.0, True)
        check("лучший балл вырос до 8.0", entry["score"] == 8.0, entry)
        check("сдал → passed True", entry["passed"] is True, entry)
        check("попыток 2", entry["attempts"] == 2, entry)

        entry = profile_store.record_exam("desert/1.4", 3.0, False)
        check("плохая пересдача НЕ роняет балл", entry["score"] == 8.0, entry)
        check("и не отменяет сдачу", entry["passed"] is True, entry)
        check("попыток 3", entry["attempts"] == 3, entry)

        entry = profile_store.record_exam("desert/1.4", 9.5, True)
        check("новая лучшая — 9.5", entry["score"] == 9.5, entry)

        check("другой экзамен живёт отдельно",
              profile_store.record_exam("forest/1.4", 2.0, False)["score"] == 2.0)
        check("первый не затронут",
              profile_store.exam_result("desert/1.4")["score"] == 9.5,
              profile_store.exam_result("desert/1.4"))

        print("\n[2] Устойчивость к мусору")
        check("пустой id — пустая запись", profile_store.record_exam("", 5, True) == {})
        check("несохранённый экзамен — {}",
              profile_store.exam_result("нет/такого") == {})
        junk = profile_store.record_exam("desert/9.9", "не число", False)
        check("мусор в балле → 0.0", junk["score"] == 0.0, junk)
        store.profile["exams"] = "испорчено"
        fixed = profile_store.record_exam("desert/2.4", 6.0, True)
        check("испорченное поле exams чинится",
              isinstance(store.profile["exams"], dict) and fixed["score"] == 6.0,
              store.profile.get("exams"))
    finally:
        store.remove()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
