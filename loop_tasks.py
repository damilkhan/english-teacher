"""Материал для урока-петли (§80): фразы ПО ПРАВИЛУ, а не по уроку.

Решение ученика 15.11.2026: 4-й урок блока — не экзамен, а работа над
ошибками. Правила берутся из пробелов ученика (loop_progress.session_rules),
а фразы — из трёх мест, все написаны человеком (решение 67):

  1) `data/tasks_a2.json`  — русские фразы уроков (поле `rule`);
  2) `data/cards_a2.json`  — карточки-выборы со ссылкой на `phrase_pairs_a2.json`
     (неправильная пара «было → стало» с готовыми фразами);
  3) `data/loop_a2.json`   — фразы, написанные СПЕЦИАЛЬНО для петли.

Почему отдельный модуль: правило (word_choice) и его материал живут в разных
файлах, а уроку нужен один список пунктов. Здесь только сборка данных, без
окна, без модели и без базы — проверяется без Tk.
"""

import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

TASKS_PATH = os.path.join(DATA, "tasks_a2.json")
CARDS_PATH = os.path.join(DATA, "cards_a2.json")
PAIRS_PATH = os.path.join(DATA, "phrase_pairs_a2.json")
LOOP_PATH = os.path.join(DATA, "loop_a2.json")

# Сколько пунктов на ОДНО правило берём в одну сессию. Меньше — петля будет
# проходить порог случайно, больше — урок не кончится за разумное время.
PER_RULE = 3

_cache = {}


def _read(path):
    """Прочитать JSON с кэшем по mtime: правишь файл — видно сразу."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print("⚠️ Материал петли не прочитался (%s): %s"
              % (os.path.basename(path), exc))
        return {}
    _cache[path] = (mtime, data)
    return data


def _item(ru, en, why, rule, source):
    return {"ru": str(ru or "").strip(), "en": str(en or "").strip(),
            "why": str(why or "").strip(), "rule": str(rule or "").strip(),
            "source": str(source or "")}


def _from_tasks():
    """Фразы уроков: один словарь {правило: [пункты]}."""
    out = {}
    raw = _read(TASKS_PATH)
    tasks = raw.get("tasks") if isinstance(raw, dict) else {}
    for lesson_id, rows in (tasks or {}).items():
        for row in (rows or ()):
            if not isinstance(row, dict):
                continue
            item = _item(row.get("ru"), row.get("en"), row.get("why"),
                         row.get("rule"), "tasks_a2.json")
            if item["ru"] and item["en"] and item["rule"]:
                item["lesson"] = str(lesson_id)
                out.setdefault(item["rule"], []).append(item)
    return out


def _from_library():
    """Фразы библиотеки пар: {правило Аналитика: [пункты]}.

    Правило берём с КАРТОЧКИ (`cards_a2.json`): она связывает библиотечную
    пару (`a2.lay_lie`) с правилом Аналитика (`word_choice`). Пару без
    карточки не берём — иначе в пробелы попало бы «a2.lay_lie», а правило
    петли считает закрытый список (§80).
    """
    out = {}
    cards = _read(CARDS_PATH)
    cards = cards.get("cards") if isinstance(cards, dict) else {}
    pairs = _read(PAIRS_PATH)
    pairs = pairs.get("rules") if isinstance(pairs, dict) else {}
    for card_id, card in (cards or {}).items():
        if not isinstance(card, dict):
            continue
        if str(card.get("kind") or "") != "choice":
            continue
        rule = str(card.get("rule") or "").strip()
        library = (pairs or {}).get(card_id) or {}
        for phrase in (library.get("phrases") or ()):
            if not isinstance(phrase, dict):
                continue
            item = _item(phrase.get("ru"), phrase.get("en"),
                         phrase.get("why"), rule, "phrase_pairs_a2.json")
            if item["ru"] and item["en"]:
                out.setdefault(rule, []).append(item)
    return out


def _from_loop_file():
    """Фразы, написанные специально для петли: {правило: [пункты]}."""
    out = {}
    raw = _read(LOOP_PATH)
    rules = raw.get("rules") if isinstance(raw, dict) else {}
    for rule, rows in (rules or {}).items():
        for row in (rows or ()):
            if not isinstance(row, dict):
                continue
            item = _item(row.get("ru"), row.get("en"), row.get("why"),
                         rule, "loop_a2.json")
            if item["ru"] and item["en"]:
                out.setdefault(str(rule), []).append(item)
    return out


def by_rule():
    """{правило: [пункты]} — весь материал петли."""
    out = {}
    for part in (_from_tasks(), _from_library(), _from_loop_file()):
        for rule, items in part.items():
            bucket = out.setdefault(rule, [])
            seen = {(it["ru"], it["en"]) for it in bucket}
            for item in items:
                if (item["ru"], item["en"]) not in seen:
                    bucket.append(item)
                    seen.add((item["ru"], item["en"]))
    return out


def items_for(rule):
    """Все пункты одного правила (пустой список — материала нет)."""
    return list(by_rule().get(str(rule or ""), []))


def has_material(rule):
    """Есть ли чем отрабатывать это правило в петле."""
    return bool(items_for(rule))


def plan(rules, per_rule=PER_RULE):
    """План сессии: пункты по правилам, ПЕРЕМЕШАННЫЕ между правилами.

    Перемешиваем не для красоты: если идти правилами подряд, ученик три раза
    подряд делает одно и то же и подсказывает себе ответ. Порядок при этом
    устойчивый (не random), иначе проверять и повторять урок нельзя.

    Правило без материала просто пропускается — но это видно в логе и в
    отчёте, выдумывать фразы код не станет.
    """
    buckets = []
    for rule in (rules or ()):
        items = items_for(rule)[:max(1, int(per_rule or PER_RULE))]
        if items:
            buckets.append((str(rule), items))
    if not buckets:
        return []
    out = []
    step = 0
    while True:
        added = False
        for rule, items in buckets:
            if step < len(items):
                out.append(items[step])
                added = True
        if not added:
            break
        step += 1
    return out


def missing(rules):
    """Правила, для которых материала нет (показать ученику честно)."""
    return [str(r) for r in (rules or ()) if not has_material(r)]
