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

import copy
import json
import os
from datetime import datetime

import config
import user_manager
import vocabulary

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
MAX_LEVEL_TESTS = 20          # сколько последних тестов уровня храним в истории
MAX_WEAK_TOPICS = 5           # сколько «слабых тем» выносим в промпт
ANALYSIS_LOG_LIMIT = 30       # сколько последних разборов Аналитика храним

EMPTY_PROFILE = {
    "mistakes": {"grammar": [], "vocabulary": [], "pronunciation": []},
    "topics_passed": [],
    "strengths": [],
    "total_lessons": 0,
    "level_tests": [],
    "weak_topics": [],
    "completed_lessons": [],   # id пройденных уроков карты (progress_map)
}


def _empty_profile():
    """Глубокая копия пустышки.

    ВАЖНО: dict(EMPTY_PROFILE) — ПОВЕРХНОСТНАЯ копия: вложенные списки
    mistakes/strengths общие для всех вызовов, и запись в них «протекала»
    между учениками. Поэтому возвращаем глубокую копию.
    """
    return copy.deepcopy(EMPTY_PROFILE)


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
        "level_tests": [],       # итоги тестов уровня + разбор ответов
        "weak_topics": [],       # темы, где ученик чаще ошибался (для промпта)
        "analysis_log": [],      # разборы реплик Аналитиком (roles/analyst)
        "completed_lessons": [],  # id пройденных уроков карты (progress_map)
        "vocabulary": [],        # карточки слов для повторения (vocabulary.py)
        "vocab_last_session": None,   # дата последнего захода повторения слов
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
        # мягкая миграция: у профилей, созданных до карты прогресса, ключа нет
        data.setdefault("completed_lessons", [])
        # ...и до системы повторения слов — тоже
        if not isinstance(data.get("vocabulary"), list):
            data["vocabulary"] = []
        return data
    except FileNotFoundError:
        return _empty_profile()
    except Exception as exc:
        print(f"⚠️ Профиль не прочитан ({exc}) — беру пустой")
        return _empty_profile()


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


def record_analysis(analysis, user_text, jane_response="", user_id=None):
    """Записывает СТРУКТУРИРОВАННЫЙ разбор реплики (роль-Аналитик).

    В отличие от record_from_dialogue (эвристика по ключевым словам в ответе
    Джейн), здесь ошибки/темы берутся из готового JSON Аналитика. Возвращает
    список заметок для чата (строки) — сам ничего не рисует.

    analysis: словарь roles.analyst (move_type/move_status/errors/topics/note).
    """
    notes = []
    profile = load(user_id)
    profile.setdefault("mistakes", {"grammar": [], "vocabulary": [], "pronunciation": []})
    for key in ("grammar", "vocabulary", "pronunciation"):
        profile["mistakes"].setdefault(key, [])
    profile.setdefault("strengths", [])
    profile.setdefault("topics_passed", [])
    profile.setdefault("analysis_log", [])

    if not isinstance(analysis, dict):
        analysis = {}

    now = datetime.now().isoformat()
    move_type = str(analysis.get("move_type") or "O")
    move_status = str(analysis.get("move_status") or "N")
    errors = analysis.get("errors") or []

    recorded = 0
    for err in errors:
        if not isinstance(err, dict):
            continue
        etype = str(err.get("type") or "grammar").lower()
        if etype == "spelling":
            # в прогрессе нет отдельной «орфографии» — кладём к лексике
            etype = "vocabulary"
        if etype not in ("grammar", "vocabulary", "pronunciation"):
            etype = "grammar"
        profile["mistakes"][etype].append({
            "date": now,
            "user_text": (user_text or "")[:100],
            "jane_response": (jane_response or "")[:200],
            "type": etype,
            "wrong": str(err.get("wrong") or "")[:80],
            "correct": str(err.get("correct") or "")[:80],
            "note": str(err.get("note") or "")[:80],
        })
        profile["mistakes"][etype] = profile["mistakes"][etype][-MAX_ERRORS_PER_TYPE:]
        recorded += 1

    # похвала: попытка ответа принята и ошибок нет
    if move_type == "A" and move_status == "A" and not errors and len(str(user_text or "")) > 10:
        profile["strengths"].append({
            "date": now,
            "user_text": (user_text or "")[:100],
            "jane_response": (jane_response or "")[:100],
        })
        profile["strengths"] = profile["strengths"][-MAX_STRENGTHS:]

    for topic in (analysis.get("topics") or []):
        name = str(topic or "").strip()
        if name and name not in profile["topics_passed"]:
            profile["topics_passed"].append(name[:40])
    profile["topics_passed"] = profile["topics_passed"][-20:]

    profile["analysis_log"].append({
        "date": now,
        "move_type": move_type,
        "move_status": move_status,
        "errors": recorded,
        "note": str(analysis.get("note") or "")[:120],
    })
    profile["analysis_log"] = profile["analysis_log"][-ANALYSIS_LOG_LIMIT:]

    save(profile, user_id)          # отмечает конец занятия (+1), как и раньше

    if recorded:
        notes.append("📝 *Разбор: %s/%s · ошибок %d*" % (move_type, move_status, recorded))
    return notes


def record_lesson_completed(lesson_id, user_id=None):
    """Отметить урок карты пройденным (карта прогресса, progress_map).

    ВАЖНО: урок — это НЕ «занятие», поэтому счётчик total_lessons не
    увеличиваем: пишем напрямую через _write, а не через save().
    Возвращает True, если урок добавлен впервые (иначе False).
    """
    lesson_id = str(lesson_id or "").strip()
    if not lesson_id:
        return False
    profile = load(user_id)
    done = profile.get("completed_lessons")
    if not isinstance(done, list):
        done = []
    profile["completed_lessons"] = done
    if lesson_id in done:
        return False
    done.append(lesson_id)
    _write(profile, progress_path(user_id))
    return True


def vocabulary_cards(user_id=None):
    """Карточки слов для повторения активного ученика (список словарей)."""
    profile = load(user_id)
    cards = profile.get("vocabulary")
    if not isinstance(cards, list):
        return []
    return [card for card in cards if isinstance(card, dict)]


def add_vocabulary(word, meanings, user_id=None):
    """Запомнить значения РУССКОГО слова (перевод из экспресс-переводчика).

    Повторный перевод того же слова дубликатов не даёт, а уже выученное
    слово не трогается: карточка просто не создаётся заново.
    ВАЖНО: пишем через _write, а не через save() — перевод слова НЕ занятие,
    счётчик total_lessons расти не должен.

    Возвращает список НОВЫХ карточек (их может быть 0).
    """
    profile = load(user_id)
    cards = profile.get("vocabulary")
    if not isinstance(cards, list):
        cards = []
    added = vocabulary.add_meanings(cards, word, meanings,
                                    limit=getattr(config, "VOCAB_MAX_CARDS", 500))
    if not added:
        return []
    profile["vocabulary"] = cards
    _write(profile, progress_path(user_id))
    return added


def update_vocabulary_card(word, en, success, user_id=None):
    """Отметить ответ по карточке: успех (GOOD) или промах.

    Возвращает карточку после правки (или None, если такой нет).
    Пишем через _write — это не новое занятие.
    """
    profile = load(user_id)
    cards = profile.get("vocabulary")
    if not isinstance(cards, list):
        return None
    card = vocabulary.find_card(cards, word, en)
    if card is None:
        return None
    if success:
        vocabulary.register_success(card)
    else:
        vocabulary.register_miss(card)
    profile["vocabulary"] = cards
    _write(profile, progress_path(user_id))
    return card


def vocab_last_session(user_id=None):
    """Когда последний раз был заход повторения слов («ГГГГ-ММ-ДД» или "")."""
    profile = load(user_id)
    return str(profile.get("vocab_last_session") or "").strip()


def mark_vocab_session(day=None, user_id=None):
    """Отметить, что заход повторения сегодня был.

    Нужно, чтобы Джейн вытаскивала окно не чаще раза в день (проверка —
    vocabulary.session_today). Пишем через _write: повторение слов — это
    НЕ занятие, счётчик total_lessons расти не должен.
    Возвращает записанную дату.
    """
    text = str(day or "").strip() or datetime.now().strftime("%Y-%m-%d")
    profile = load(user_id)
    profile["vocab_last_session"] = text
    _write(profile, progress_path(user_id))
    return text


def record_level_test(result, answers, user_id=None):
    """Пишет итог теста уровня и разбор ответов в прогресс ученика.

    Уровень как «краткий итог» живёт в profiles/user_N.json (user_manager),
    а детальная история — ЗДЕСЬ, в profiles/user_N_progress.json: так её
    видит prompt_builder и может опираться на «слабые темы».

    result:  словарь из level_test.get_result();
    answers: список [{"date","topic","level","correct","question"}].
    Возвращает список слабых тем (для справки/тестов).
    """
    profile = load(user_id)
    profile.setdefault("level_tests", [])
    if isinstance(result, dict):
        profile["level_tests"].append({
            "date": result.get("date"),
            "level": result.get("level"),
            "difficulty": result.get("difficulty"),
            "correct": result.get("correct"),
            "total": result.get("total"),
            "breakdown": result.get("breakdown", {}),
            "answers": [dict(a) for a in (answers or []) if isinstance(a, dict)],
        })
        profile["level_tests"] = profile["level_tests"][-MAX_LEVEL_TESTS:]
    profile["weak_topics"] = _weak_topics(profile["level_tests"])
    _write(profile, progress_path(user_id))
    return profile["weak_topics"]


def _weak_topics(level_tests):
    """Слабые темы по всей истории тестов: где доля ошибок выше — выше в списке."""
    stats = {}
    for test in (level_tests or []):
        for ans in (test.get("answers") or []):
            topic = str(ans.get("topic") or "").strip()
            if not topic:
                continue
            cell = stats.setdefault(topic, {"topic": topic, "correct": 0, "total": 0})
            cell["total"] += 1
            if ans.get("correct"):
                cell["correct"] += 1
    weak = [c for c in stats.values() if c["correct"] < c["total"]]
    # сначала темы с наибольшим числом ошибок, при равенстве — где больше вопросов
    weak.sort(key=lambda c: (c["correct"] - c["total"], -c["total"]))
    return weak[:MAX_WEAK_TOPICS]


def _write(profile, path=None):
    path = path or progress_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=4, ensure_ascii=False)
