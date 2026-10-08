# -*- coding: utf-8 -*-
# =========================================================
# USER_MANAGER.PY — многопользовательская система ( личности )
# =========================================================
# Этот модуль владеет ТОЛЬКО личностью пользователя:
#   profiles/user_N.json         — имя, пол, возраст, уровень, цель, аватар
#   profiles/last_user.txt       — id последнего активного профиля
#
# Прогресс обучения (ошибки, strengths, число занятий) сюда НЕ входит —
# им владеет profile_store.py и хранит его в profiles/user_N_progress.json.
# Путь к файлу прогресса задаётся здесь (progress_path), чтобы имя файла
# было в одном месте: profile_store импортирует эту функцию.
#
# Никакого Tk/GUI тут нет: модуль тестируется напрямую.
# =========================================================

import json
import os
from datetime import datetime

import config

# Лимит профилей. Больше 8 — нельзя (проверяется и в UI, и здесь).
MAX_USERS = 8

PROFILES_DIR = os.path.join(config.BASE_DIR, "profiles")
LAST_USER_FILE = os.path.join(PROFILES_DIR, "last_user.txt")

# Допустимые значения полей (в нижнем регистре — как храним).
GENDERS = ("male", "female", "other")
GENDER_LABELS = {"male": "Мужской", "female": "Женский", "other": "Другое"}

LEVELS = ("A1", "A2", "B1", "B2", "C1")

# Имена-заглушки: профиль с таким именем (или пустым) считается НЕПОЛНЫМ —
# его создала программа, а не ученик. Такой профиль обязан пройти форму,
# иначе Джейн не знает, как обращаться к ученику (см. is_complete).
PLACEHOLDER_NAMES = {"", "ученик", "ученица", "student"}

# Уровень ставит ТОЛЬКО вводный тест (level_test). Пока тест не пройден,
# уровня нет — поэтому в профиле он хранится как None, а в интерфейсе
# показывается «не определён».
LEVEL_UNKNOWN_TEXT = "не определён"


def level_label(level):
    """Человекочитаемый уровень: 'B1' или «не определён», если теста ещё не было."""
    return level if level in LEVELS else LEVEL_UNKNOWN_TEXT

# Аватары-эмодзи, предлагаемые в форме (пользователь может вписать свой).
AVATARS = ["🦊", "🐼", "🐯", "🐨", "🐸", "🦁", "🐧", "🦉",
           "🐙", "🦄", "🐳", "🐝", "🌟", "🚀", "🎧", "📚"]


# ---------------------------------------------------------
# Пути и служебное
# ---------------------------------------------------------
def _ensure_dir():
    os.makedirs(PROFILES_DIR, exist_ok=True)


def identity_path(user_id):
    """profiles/user_N.json — личность пользователя."""
    return os.path.join(PROFILES_DIR, "user_%d.json" % int(user_id))


def progress_path(user_id):
    """profiles/user_N_progress.json — прогресс обучения (владеет profile_store)."""
    return os.path.join(PROFILES_DIR, "user_%d_progress.json" % int(user_id))


def _used_ids():
    """Множество занятых id по факту наличия файлов user_N.json."""
    _ensure_dir()
    ids = set()
    for name in os.listdir(PROFILES_DIR):
        if name.startswith("user_") and name.endswith(".json") \
                and not name.endswith("_progress.json"):
            try:
                ids.add(int(name[len("user_"):-len(".json")]))
            except ValueError:
                continue
    return ids


def _normalize(profile, user_id):
    """Приводит профиль к единому виду (заполняет пропуски, чистит поля)."""
    profile = dict(profile or {})
    profile["id"] = int(user_id)
    profile["name"] = str(profile.get("name") or "Ученик").strip()

    gender = str(profile.get("gender") or "other").lower()
    profile["gender"] = gender if gender in GENDERS else "other"

    profile["age"] = _to_age(profile.get("age"))

    # None (или мусор) = «уровень не определён»: так профиль выглядит до теста,
    # а уровень приходит из get_result() (level_test). Дефолт A1 НЕ подставляем —
    # иначе можно решить, что ученик уже проверен.
    level = str(profile.get("level") or "").strip().upper()
    profile["level"] = level if level in LEVELS else None

    profile["goal"] = str(profile.get("goal") or "").strip()
    profile["avatar"] = str(profile.get("avatar") or AVATARS[0]).strip() or AVATARS[0]

    # Заполнен ли профиль формой (имя/пол заданы человеком). Старые профили
    # поля не имеют → False, значит потребуют формы при следующем запуске.
    profile["complete"] = bool(profile.get("complete", False))

    profile.setdefault("created", datetime.now().isoformat())
    return profile


def _to_age(value):
    """Возраст → int (0..120) или None, если не задан/мусор."""
    if value in (None, "", "—"):
        return None
    try:
        age = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return age if 0 <= age <= 120 else None


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (FileNotFoundError, ValueError, OSError):
        return None


def _write(path, profile):
    _ensure_dir()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=4, ensure_ascii=False)


# ---------------------------------------------------------
# Публичный интерфейс (как в задании)
# ---------------------------------------------------------
def list_users():
    """Список профилей, отсортированный по id. Битые файлы пропускаются."""
    users = []
    for user_id in sorted(_used_ids()):
        profile = get_user(user_id)
        if profile is not None:
            users.append(profile)
    return users


def count():
    """Сколько профилей сейчас существует."""
    return len(_used_ids())


def slots_left():
    return max(0, MAX_USERS - count())


def is_full():
    return count() >= MAX_USERS


def get_user(user_id):
    """Загружает профиль по id. Нет/битый файл → None."""
    if user_id is None:
        return None
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None
    data = _read(identity_path(user_id))
    if data is None:
        return None
    return _normalize(data, user_id)


def save_user(user_id, data):
    """Сохраняет профиль целиком. True при успехе."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return False
    profile = _normalize(data, user_id)
    if "created" not in (data or {}):
        # при обновлении не затираем дату создания, если её не передали
        old = _read(identity_path(user_id)) or {}
        profile["created"] = old.get("created", profile["created"])
    try:
        _write(identity_path(user_id), profile)
        return True
    except OSError as exc:
        print(f"⚠️ Не удалось сохранить профиль #{user_id}: {exc}")
        return False


def create_user(name, gender="other", age=None, level=None, goal="", avatar=AVATARS[0],
                complete=True):
    """Создаёт новый профиль в первом свободном слоте 1..MAX_USERS.

    Возвращает профиль или None, если лимит исчерпан / имя пустое.
    Уровень по умолчанию НЕ задан (None): его выставит вводный тест.
    complete=False — профиль-заготовка (без формы): общение запрещено,
    пока его не заполнят.
    """
    if not str(name or "").strip():
        return None
    if is_full():
        return None

    used = _used_ids()
    user_id = next((i for i in range(1, MAX_USERS + 1) if i not in used), None)
    if user_id is None:
        return None

    profile = _normalize(
        {"name": name, "gender": gender, "age": age, "level": level,
         "goal": goal, "avatar": avatar, "complete": complete,
         "created": datetime.now().isoformat()},
        user_id,
    )
    if not save_user(user_id, profile):
        return None
    set_last_user(user_id)          # новый профиль сразу становится активным
    return profile


def update_user(user_id, data):
    """Частичное редактирование: переданные поля заменяют старые."""
    profile = get_user(user_id)
    if profile is None:
        return False
    merged = dict(profile)
    merged.update(data or {})
    return save_user(user_id, merged)


def is_complete(user):
    """Заполнен ли профиль настолько, чтобы начинать общение с Джейн.

    Полным считается профиль, где задано непустое (не заглушечное) имя И стоит
    флаг complete (его ставит форма). Профиль-заготовка («Ученик») и старые
    профили без флага — НЕПОЛНЫЕ: имя/пол неизвестны, Джейн ошибалась в роде.
    """
    if not isinstance(user, dict):
        return False
    name = str(user.get("name") or "").strip().lower()
    if not name or name in PLACEHOLDER_NAMES:
        return False
    return bool(user.get("complete"))


def delete_user(user_id):
    """Удаляет профиль и его прогресс. True при успехе."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return False

    removed = False
    for path in (identity_path(user_id), progress_path(user_id)):
        if os.path.exists(path):
            try:
                os.remove(path)
                removed = True
            except OSError as exc:
                print(f"⚠️ Не удалось удалить {path}: {exc}")

    # если удалили активного — выбираем другой профиль (или сбрасываем)
    if get_last_user_id() == user_id:
        remaining = sorted(_used_ids())
        if remaining:
            set_last_user(remaining[0])
        else:
            try:
                os.remove(LAST_USER_FILE)
            except OSError:
                pass
    return removed


# ---------------------------------------------------------
# Активный пользователь
# ---------------------------------------------------------
def set_last_user(user_id):
    """Запоминает id последнего активного профиля."""
    _ensure_dir()
    try:
        with open(LAST_USER_FILE, "w", encoding="utf-8") as fh:
            fh.write(str(int(user_id)))
    except (TypeError, ValueError, OSError) as exc:
        print(f"⚠️ Не удалось записать last_user: {exc}")


def get_last_user_id():
    """id последнего активного профиля или None."""
    try:
        with open(LAST_USER_FILE, "r", encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def get_last_user():
    """Профиль последнего активного пользователя (или первый доступный)."""
    user_id = get_last_user_id()
    if user_id is not None:
        profile = get_user(user_id)
        if profile is not None:
            return profile
    users = list_users()
    if users:
        set_last_user(users[0]["id"])
        return users[0]
    return None
