"""Уроки-«выявление пробелов» (§82): русская фраза → ученик переводит.

Решение ученика 15.11.2026: уроки до работы над ошибками — это не «ответь
официанту, чтобы получить 1/5», а перевод РУССКОЙ фразы. Ученик строит
английскую фразу сам, приложение сверяет её с ОДНИМ эталоном, промах
попадает в пробелы по правилу `rule` и потом отрабатывается в петле (§80).

Почему эталон ОДИН: замер §77 (tools/eval_meaning.py, 86 пар) — смысл
оценивает модель, 96,3 % и ноль ложных «то же самое». Списки вариантов
ответа не нужны.

Здесь только МАТЕРИАЛ и сверка. Модель зовёт окно (ui/app.py), причём ТОЛЬКО
при промахе: сначала бесплатный `lesson.same_meaning`.
"""

import json
import os

import lesson_material

ROOT = os.path.dirname(os.path.abspath(__file__))
TASKS_PATH = os.path.join(ROOT, "data", "tasks_a2.json")

_cache = {"mtime": None, "tasks": {}}

OK = "ok"          # смысл совпал по коду — модель не нужна
MAYBE = "maybe"    # похоже, но код не уверен: решает модель (см. §77)
NO = "no"          # пусто или по-русски — ответа нет


def load(force=False):
    """{id урока: [фразы]}. Кэш по mtime: правишь файл — видно сразу."""
    try:
        mtime = os.path.getmtime(TASKS_PATH)
    except OSError:
        return {}
    if not force and _cache["mtime"] == mtime:
        return _cache["tasks"]
    try:
        with open(TASKS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print("⚠️ Фразы уроков не прочитались: %s" % exc)
        return {}
    raw = data.get("tasks") if isinstance(data, dict) else {}
    out = {}
    for lesson_id, items in (raw or {}).items():
        rows = []
        for item in (items or ()):
            if not isinstance(item, dict):
                continue
            ru = str(item.get("ru") or "").strip()
            en = str(item.get("en") or "").strip()
            if not ru or not en:
                continue
            rows.append({"ru": ru, "en": en,
                         "rule": str(item.get("rule") or "").strip().lower(),
                         "why": str(item.get("why") or "").strip()})
        if rows:
            out[str(lesson_id)] = rows
    _cache["mtime"] = mtime
    _cache["tasks"] = out
    return out


def has(lesson_id):
    """Есть ли фразы для этого урока (иначе урок идёт как раньше)."""
    return bool(phrases_for(lesson_id))


def phrases_for(lesson_id):
    """Все фразы урока (пустой список — урока нет в файле).

    17.11.2026: фразы могут лежать и в data/lessons_a2.json — там они стоят
    рядом со сценой урока (урок идёт двумя частями: разговор по сцене, потом
    перевод этих фраз). Формат строки тот же, поэтому разницы для кода нет.
    """
    key = str(lesson_id or "")
    rows = list(load().get(key, []))
    if rows:
        return rows
    return lesson_material.phrases(key)


def pick(lesson_id, index=0):
    """Фраза по номеру задания. Номер больше списка — берём снова с начала.

    Повтор по кругу — вынужденная мера: фраз на урок пока шесть. Новые фразы
    дописываются в data/tasks_a2.json, кода это не касается.
    """
    items = phrases_for(lesson_id)
    if not items:
        return None
    try:
        number = int(index)
    except (TypeError, ValueError):
        number = 0
    return items[number % len(items)]


def covered_lessons():
    """Для каких уроков фразы уже написаны (проверка полноты)."""
    return sorted(load().keys())


def _has_cyrillic(text):
    return any("\u0430" <= ch <= "\u044f" or "\u0410" <= ch <= "\u042f"
               or ch in "\u0451\u0401" for ch in str(text or ""))


def check(said, reference):
    """Ответ на перевод: OK / MAYBE / NO. Модель здесь НЕ зовётся.

    OK    — все значимые слова эталона есть в ответе (lesson.same_meaning);
    NO    — пусто или по-русски: это не ответ, а просьба помочь (ученику
            покажем подсказку, урок не двигаем);
    MAYBE — остальное: возможно, верный пересказ, решает модель (0,17 с).
    """
    text = str(said or "").strip()
    want = str(reference or "").strip()
    if not text or not want:
        return NO
    if _has_cyrillic(text) and not any(ch.isascii() and ch.isalpha() for ch in text):
        return NO
    try:
        import lesson as lesson_mod
    except Exception:
        return MAYBE
    try:
        if lesson_mod.same_meaning(text, want):
            return OK
    except Exception:
        return MAYBE
    return MAYBE
