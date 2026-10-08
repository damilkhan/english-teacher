# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PROFILE_GATE.PY — обязательность профиля
# =========================================================
#   python tests\test_profile_gate.py
#
# Проверяем:
#   1) is_complete: пустой/заглушечный/неполный профиль → False;
#   2) create_user: complete=True по умолчанию, complete=False → заготовка;
#   3) заглушечное имя неполно даже с флагом complete;
#   4) update_user(complete=True) «дозаполняет» профиль;
#   5) миграция: старый профиль без поля complete → НЕПОЛНЫЙ;
#   6) флаг complete переживает запись/чтение файла.
# =========================================================

import json
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

import user_manager  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class temp_profiles:
    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_gate_")
        self.real = (user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE)
        user_manager.PROFILES_DIR = self.dir
        user_manager.LAST_USER_FILE = os.path.join(self.dir, "last_user.txt")
        return self.dir

    def __exit__(self, *exc):
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE = self.real


# =========================================================
# 1. is_complete
# =========================================================
def test_is_complete():
    print("\n[1] is_complete")
    check("None → False", user_manager.is_complete(None) is False)
    check("{} → False", user_manager.is_complete({}) is False)
    check("пустое имя → False", user_manager.is_complete({"name": "", "complete": True}) is False)
    check("заглушка «Ученик» → False",
          user_manager.is_complete({"name": "Ученик", "complete": True}) is False)
    check("заглушка «Student» (регистр) → False",
          user_manager.is_complete({"name": "  student ", "complete": True}) is False)
    check("имя без флага complete → False",
          user_manager.is_complete({"name": "Дамиль"}) is False)
    check("имя + complete=True → True",
          user_manager.is_complete({"name": "Дамиль", "complete": True}) is True)


# =========================================================
# 2-3. create_user
# =========================================================
def test_create_user():
    print("\n[2] create_user и флаг complete")
    with temp_profiles():
        full = user_manager.create_user("Аня", "female", 14, "A2", "цель", "🦊")
        check("create_user по умолчанию полный", user_manager.is_complete(full) is True, full)

        draft = user_manager.create_user("Ученик", "other", None, None, "", "🙂", complete=False)
        check("complete=False → заготовка неполна",
              user_manager.is_complete(draft) is False, draft)
        check("у заготовки complete=False в файле",
              user_manager.get_user(draft["id"]).get("complete") is False)

        odd = user_manager.create_user("Имя", "other", None, None, "", "🙂", complete=False)
        check("complete=False + реальное имя → всё равно неполный",
              user_manager.is_complete(odd) is False)


# =========================================================
# 4. update_user дозаполняет
# =========================================================
def test_update_marks_complete():
    print("\n[4] update_user(complete=True)")
    with temp_profiles():
        uid = user_manager.create_user("Ученик", "male", 30, None, "", "🙂", complete=False)["id"]
        check("до правки неполный", user_manager.is_complete(user_manager.get_user(uid)) is False)
        user_manager.update_user(uid, {"name": "Дамиль", "gender": "male", "complete": True})
        check("после правки полный", user_manager.is_complete(user_manager.get_user(uid)) is True)


# =========================================================
# 5. Миграция: старый профиль без поля complete
# =========================================================
def test_migration():
    print("\n[5] Миграция старого профиля")
    with temp_profiles():
        path = user_manager.identity_path(3)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"name": "Оля", "gender": "female", "age": 20,
                       "level": "B1", "goal": "x", "avatar": "🙂"}, fh, ensure_ascii=False)
        user = user_manager.get_user(3)
        check("старый профиль читается", user is not None and user["name"] == "Оля")
        check("без поля complete → НЕПОЛНЫЙ (потребует формы)",
              user_manager.is_complete(user) is False)


def main():
    print("=" * 60)
    print("Проверка обязательности профиля (user_manager)")
    print("=" * 60)

    test_is_complete()
    test_create_user()
    test_update_marks_complete()
    test_migration()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
