"""Материал урока A2: мини-сцена, вопросы по ней, фразы (17.11.2026).

Зачем: в живом уроке city/4.1 (16.11.2026) модель НЕ знала, о чём говорить —
в промпт уходило только название блока («Comparing Things»), и она выдумывала
вопросы («какое самое большое здание рядом»). Теперь материал лежит в
data/lessons_a2.json: короткая сцена (4-6 реплик), 2-3 вопроса ТОЛЬКО по
сцене и фразы, которые ученик должен уметь сказать сам.

Тексты пишет человек, модель их НЕ сочиняет (решение 67). Урока нет в файле —
поведение прежнее, байт-в-байт (smoke_test).

Фразы идут в формате data/tasks_a2.json (ru / en / rule / why), поэтому
их читает translate_task — приложение само сверяет ответ с эталоном.
"""

import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
LESSONS_PATH = os.path.join(ROOT, "data", "lessons_a2.json")

_cache = {"mtime": None, "lessons": {}}


def load(force=False):
    """{id урока: материал}. Кэш по mtime: правишь файл — видно сразу."""
    try:
        mtime = os.path.getmtime(LESSONS_PATH)
    except OSError:
        return {}
    if not force and _cache["mtime"] == mtime:
        return _cache["lessons"]
    try:
        with open(LESSONS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print("\u26a0\ufe0f Материал уроков не прочитался: %s" % exc)
        return {}
    raw = data.get("lessons") if isinstance(data, dict) else {}
    out = {}
    for lesson_id, item in (raw or {}).items():
        if not isinstance(item, dict):
            continue
        scene = []
        for line in (item.get("scene") or ()):
            if not isinstance(line, dict):
                continue
            en = str(line.get("en") or "").strip()
            if en:
                scene.append({"who": str(line.get("who") or "").strip(),
                              "en": en})
        ask = [str(q).strip() for q in (item.get("ask") or ()) if str(q).strip()]
        phrases = []
        for row in (item.get("phrases") or ()):
            if not isinstance(row, dict):
                continue
            ru = str(row.get("ru") or "").strip()
            en = str(row.get("en") or "").strip()
            if ru and en:
                phrases.append({"ru": ru, "en": en,
                                "rule": str(row.get("rule") or "").strip().lower(),
                                "why": str(row.get("why") or "").strip()})
        if not scene and not ask:
            continue        # без сцены и вопросов урок идёт как раньше
        out[str(lesson_id)] = {
            "topic": str(item.get("topic") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "words": [str(w).strip() for w in (item.get("words") or ())
                      if str(w).strip()],
            "scene": scene,
            "ask": ask,
            "phrases": phrases,
            "picture": str(item.get("picture") or "").strip(),
        }
    _cache["mtime"] = mtime
    _cache["lessons"] = out
    return out


def get(lesson_id):
    """Материал урока или None (урок идёт как раньше)."""
    return load().get(str(lesson_id or ""))


def has(lesson_id):
    """Есть ли у урока готовая сцена (иначе промпт прежний)."""
    return get(lesson_id) is not None


def scene_lines(lesson_id):
    """Реплики сцены [{"who","en"}] — для промпта и для чата."""
    return list((get(lesson_id) or {}).get("scene") or [])


def ask(lesson_id):
    """Вопросы ТОЛЬКО по сцене."""
    return list((get(lesson_id) or {}).get("ask") or [])


def phrases(lesson_id):
    """Фразы урока в формате tasks_a2.json (ru / en / rule / why)."""
    return list((get(lesson_id) or {}).get("phrases") or [])


def picture(lesson_id):
    """Ключ фото по теме урока (пусто — фото берётся случайное)."""
    return str((get(lesson_id) or {}).get("picture") or "")


def scene_text(lesson_id):
    """Сцена одной строкой для чата: \"Ann: ...  /  Jack: ...\"."""
    rows = []
    for line in scene_lines(lesson_id):
        who = line.get("who") or ""
        rows.append(("%s: %s" % (who, line.get("en"))) if who else line.get("en"))
    return "\n".join(rows)


def tasks_count(lesson_id):
    """Сколько заданий в уроке: вопросы по сцене + фразы на перевод."""
    return len(ask(lesson_id)) + len(phrases(lesson_id))


def covered_lessons():
    """Для каких уроков материал уже написан (проверка полноты)."""
    return sorted(load().keys())
