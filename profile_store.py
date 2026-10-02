# -*- coding: utf-8 -*-
# =========================================================
# PROFILE_STORE.PY — владелец ПРОГРЕССА обучения (ошибки/успехи/занятия)
# =========================================================
# Вариант B: прогресс привязан к пользователю.
#   profiles/user_N_progress.json — прогресс активного пользователя;
#   student_profile.json          — запасной «общий» путь (legacy), он же
#                                   используется тестами и режимом без входа.
#
# Личностью (name/gender/age/level/goal/avatar) владеет user_manager.py.
# Имя файла прогресса задаётся ТАМ (user_manager.progress_path), чтобы оно
# было в одном месте и delete_user мог заодно подчистить прогресс.
#
# Никакого Tk/GUI тут нет: модуль можно тестировать напрямую.
# =========================================================

import json
import os
from datetime import datetime

import config
import user_manager

PROFILE_FILENAME = "student_profile.json"

# Запасной путь (legacy / тесты). Если активного пользователя нет —
# работаем с ним, чтобы модуль оставался тестируемым без профилей.
PROFILE_PATH = os.path.join(config.BASE_DIR, PROFILE_FILENAME)

# id активного пользователя (устанавливается при входе в приложение).
_active_user_id = None

MISTAKE_INDICATORS = ["mistake", "error", "incorrect", "wrong", "неправильно", "ошибка"]
GRAMMAR_KEYWORDS = ["grammar", "tense", "verb", "noun", "adjective", "past", "future", "present"]
VOCAB_KEYWORDS = ["vocabulary", "word", "spelling", "meaning", "definition"]
PRAISE_INDICATORS = ["good", "excellent", "great", "perfect", "well done", "correct", "правильно", "отлично"]

MAX_ERRORS_PER_TYPE = 20
MAX_STRENGTHS = 20
MAX_WEEK_MISTAKES = 50

EMPTY_PROFILE = {
    "mistakes": {"grammar": [], "vocabulary": [], "pronunciation": []},
    "topics_passed": [],
    "strengths": [],
    "total_lessons": 0,
}


# ---------------------------------------------------------
# Активный пользователь и путь
# ---------------------------------------------------------
def set_active_user(user_id):
    """Задаёт активного пользователя. None → запасной общий профиль."""
    global _active_user_id
    try:
        _active_user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        _active_user_id = None
    return _active_user_id


def get_active_user_id():
    return _active_user_id


def progress_path(user_id=None):
    """Путь к файлу прогресса.

    user_id явно > активный пользователь > запасной PROFILE_PATH.
    """
    uid = _active_user_id if user_id is None else user_id
    if uid is None:
        return PROFILE_PATH
    return user_manager.progress_path(uid)


def default_profile():
    return {
        "student_name": "Student",
        "first_lesson": datetime.now().isoformat(),
        "last_lesson": None,
        "mistakes": {"grammar": [], "vocabulary": [], "pronunciation": []},
        "topics_passed": [],
        "strengths": [],
        "total_lessons": 0,
        "last_week_mistakes": [],
    }


def ensure_profile(user_id=None):
    """Создаёт файл прогресса, если его нет.

    Возвращает (profile, created): created=True, если профиль только что создан
    (тогда GUI показывает приветственное сообщение).
    """
    path = progress_path(user_id)
    if os.path.exists(path):
        return load(user_id), False
    profile = default_profile()
    _write(profile, path)
    return profile, True


def load(user_id=None):
    """Читает прогресс. Битый/отсутствующий файл → безопасная пустышка."""
    try:
        with open(progress_path(user_id), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("профиль не является объектом JSON")
        return data
    except FileNotFoundError:
        return dict(EMPTY_PROFILE)
    except Exception as exc:
        print(f"⚠️ Профиль не прочитан ({exc}) — беру пустой")
        return dict(EMPTY_PROFILE)


def save(profile, user_id=None):
    """Сохраняет прогресс, отмечая конец занятия и +1 к числу занятий."""
    profile["last_lesson"] = datetime.now().isoformat()
    profile["total_lessons"] = profile.get("total_lessons", 0) + 1
    _write(profile, progress_path(user_id))
    return profile


def record_from_dialogue(user_text, jane_response, user_id=None):
    """Разбирает реплику Джейн и записывает ошибки/успехи в прогресс.

    Возвращает список заметок для чата (строки) — сам ничего не рисует,
    поэтому остаётся тестируемым без GUI.
    """
    notes = []
    profile = load(user_id)
    # гарантируем структуру: старые профили могли не иметь ключей
    profile.setdefault("mistakes", {"grammar": [], "vocabulary": [], "pronunciation": []})
    for key in ("grammar", "vocabulary", "pronunciation"):
        profile["mistakes"].setdefault(key, [])
    profile.setdefault("strengths", [])
    profile.setdefault("last_week_mistakes", [])

    low = (jane_response or "").lower()
    now = datetime.now().isoformat()

    if any(ind in low for ind in MISTAKE_INDICATORS):
        mistake_type = "general"
        if any(kw in low for kw in GRAMMAR_KEYWORDS):
            mistake_type = "grammar"
        if any(kw in low for kw in VOCAB_KEYWORDS):
            mistake_type = "vocabulary"
        if mistake_type not in profile["mistakes"]:
            mistake_type = "grammar"

        profile["mistakes"][mistake_type].append({
            "date": now,
            "user_text": user_text[:100],
            "jane_response": jane_response[:200],
            "type": mistake_type,
        })
        for key in profile["mistakes"]:
            profile["mistakes"][key] = profile["mistakes"][key][-MAX_ERRORS_PER_TYPE:]

        profile["last_week_mistakes"].append({"date": now, "type": mistake_type})
        profile["last_week_mistakes"] = profile["last_week_mistakes"][-MAX_WEEK_MISTAKES:]

        notes.append(f"📝 *Записано в профиль: ошибка типа '{mistake_type}'*")

    if any(ind in low for ind in PRAISE_INDICATORS) and len(user_text) > 10:
        profile["strengths"].append({
            "date": now,
            "user_text": user_text[:100],
            "jane_response": jane_response[:100],
        })
        profile["strengths"] = profile["strengths"][-MAX_STRENGTHS:]

    save(profile, user_id)
    return notes


def _write(profile, path=None):
    path = path or progress_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=4, ensure_ascii=False)
