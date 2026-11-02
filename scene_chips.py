# -*- coding: utf-8 -*-
"""scene_chips.py — конструктор предложения на РУССКОМ (решение 101).

Ученик собирает русское предложение из чипов, В ГОЛОВЕ переводит его и
произносит по-английски в микрофон. Английского на экране нет НИКОГДА:
у чипа есть поле `en`, но оно нужно только движку реакций (если STT
расслышал криво) — в окно оно не попадает.

Чипы лежат в данных: data/reactions_a2.json -> slots.<slot>.chips.
Группы: start / count / item / end / short (start слева, end справа,
short — готовый короткий ответ целиком). Набор чипов зависит от слота
ТЕКУЩЕГО вопроса: контекст диалога, а не один набор на всю сцену.

Модуль чистый: ни Tk, ни модели, ни сети (образец scenes.py).
"""

from __future__ import annotations

import re
from typing import Dict, List

import scene_reactions

# Порядок показа групп и их подписи (подписи видит ученик).
GROUPS = [
    ("start", "начало"),
    ("count", "сколько"),
    ("item", "что"),
    ("end", "конец"),
    ("short", "короткий ответ"),
]

# В набранном предложении группы идут по СМЫСЛУ, а не по порядку кликов:
# «Я бы хотел» + «два» + «пиво», даже если нажимали пиво первым.
ORDER = ["start", "count", "item", "end", "short"]

_LATIN = re.compile(r"[A-Za-z]")


def chips(slot: str) -> Dict[str, List[dict]]:
    """Все группы чипов слота: {группа: [{ru, en}, ...]} (пустые — [])."""
    conf = (scene_reactions.library().get("slots") or {}).get(slot) or {}
    raw = conf.get("chips") or {}
    out: Dict[str, List[dict]] = {}
    for key, _title in GROUPS:
        rows = []
        for row in raw.get(key) or []:
            ru = str((row or {}).get("ru") or "").strip()
            if not ru:
                continue
            rows.append({"ru": ru, "en": str((row or {}).get("en") or "").strip()})
        out[key] = rows
    return out


def has(slot: str) -> bool:
    """Есть ли у слота чипы (нет — панель не показываем)."""
    return any(chips(slot).values())


def groups(slot: str) -> List[dict]:
    """Группы по порядку показа: [{key, title, items}] — только непустые."""
    table = chips(slot)
    return [{"key": key, "title": title, "items": table[key]}
            for key, title in GROUPS if table[key]]


def all_chips(slot: str) -> List[dict]:
    """Плоский список чипов слота (для проверок и раскладки)."""
    out = []
    for key, _title in GROUPS:
        for row in chips(slot)[key]:
            out.append({"group": key, "ru": row["ru"], "en": row["en"]})
    return out


def compose(picked) -> Dict[str, str]:
    """Собрать предложение из нажатых чипов.

    picked — список чипов ({'group','ru','en'}); порядок кликов НЕ важен:
    группы выстраиваются по смыслу (ORDER). Возвращает {'ru','en'}.
    """
    rows = [row for row in (picked or []) if str((row or {}).get("ru") or "")]
    rows.sort(key=lambda row: ORDER.index(row.get("group"))
              if row.get("group") in ORDER else len(ORDER))
    ru = " ".join(str(row["ru"]).strip() for row in rows).strip()
    en = " ".join(str(row.get("en") or "").strip() for row in rows).strip()
    return {"ru": ru, "en": en}


def latin_in(text: str) -> str:
    """Латинские буквы в русской подписи (их быть не должно) или ''."""
    found = _LATIN.search(str(text or ""))
    return found.group(0) if found else ""


def slots_with_chips() -> List[str]:
    """Слоты, у которых есть чипы (по данным)."""
    slots = scene_reactions.library().get("slots") or {}
    return [name for name in slots if has(name)]
