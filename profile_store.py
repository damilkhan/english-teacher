# -*- coding: utf-8 -*-
# =========================================================
# PROFILE_STORE.PY — единственный владелец student_profile.json
# =========================================================
# Раньше этим файлом управляли сразу из gui.py (4 метода:
# init_profile / get_student_profile / save_student_profile /
# update_profile_from_dialogue). Любой второй потребитель означал бы
# третью копию логики. Теперь чтение и запись — только здесь.
#
# Никакого Tk/GUI тут нет: модуль можно тестировать напрямую.
# =========================================================

import json
import os
from datetime import datetime

import config

PROFILE_FILENAME = "student_profile.json"

# Путь к файлу. Вынесен в переменную модуля, чтобы тесты могли подменить
# его на временную папку и не трогать реальный профиль ученика.
PROFILE_PATH = os.path.join(config.BASE_DIR, PROFILE_FILENAME)

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


def ensure_profile():
    """Создаёт файл профиля, если его нет.

    Возвращает (profile, created): created=True, если профиль только что создан
    (тогда GUI показывает приветственное сообщение).
    """
    if os.path.exists(PROFILE_PATH):
        return load(), False
    profile = default_profile()
    _write(profile)
    return profile, True


def load():
    """Читает профиль. Битый/отсутствующий файл → безопасная пустышка."""
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("профиль не является объектом JSON")
        return data
    except FileNotFoundError:
        return dict(EMPTY_PROFILE)
    except Exception as exc:
        print(f"⚠️ Профиль не прочитан ({exc}) — беру пустой")
        return dict(EMPTY_PROFILE)


def save(profile):
    """Сохраняет профиль, отмечая конец занятия и +1 к числу занятий."""
    profile["last_lesson"] = datetime.now().isoformat()
    profile["total_lessons"] = profile.get("total_lessons", 0) + 1
    _write(profile)
    return profile


def record_from_dialogue(user_text, jane_response):
    """Разбирает реплику Джейн и записывает ошибки/успехи в профиль.

    Возвращает список заметок для чата (строки) — сам ничего не рисует,
    поэтому остаётся тестируемым без GUI.
    """
    notes = []
    profile = load()
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

    save(profile)
    return notes


def _write(profile):
    with open(PROFILE_PATH, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=4, ensure_ascii=False)
