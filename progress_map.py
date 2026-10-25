# -*- coding: utf-8 -*-
# =========================================================
# PROGRESS_MAP.PY — логика карты прогресса (локации → точки → уроки)
# =========================================================
# Читает knowledge_base/curriculum.json и отвечает на вопросы:
#   * какие локации, точки и уроки есть (структура «учебного плана»);
#   * что ученик уже прошёл (profile["completed_lessons"]), что открыто
#     сейчас и что ещё закрыто.
#
# Иерархия:
#   ЛОКАЦИЯ (Пустыня, A0)
#     └── ТОЧКА  — кружок на карте = «блок» уроков (1.1, 1.2, 1.3 …)
#            └── УРОК — одно занятие (type: speaking / chat)
#
# Прохождение ЛИНЕЙНОЕ: уроки внутри точки и точки внутри локации идут
# строго по порядку. Точка открыта, только если предыдущая пройдена.
#
# Никакого Tk/GUI здесь нет: модуль тестируется напрямую.
# =========================================================

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

_log = logging.getLogger(__name__)

# Возможные состояния точки/урока.
LOCKED = "locked"
UNLOCKED = "unlocked"
COMPLETED = "completed"

# Шкала уровней (lower → higher). По ней «пропускаем» локации, которые
# ученик уже закрыл вступительным тестом (см. skipped_lessons).
_CEFR_ORDER = ("A0", "A1", "A2", "B1", "B2", "C1")


class ProgressMap:
    """Логика карты прогресса: локации, точки (блоки) и уроки.

    Если curriculum.json отсутствует или повреждён, объект работает в
    безопасном режиме «нет данных»: методы возвращают пустые значения,
    состояния — "locked", прогресс — (0, 0). Исключений наружу не летит.
    """

    FILENAME = "curriculum.json"

    def __init__(self, base_path: str = "knowledge_base") -> None:
        base = Path(base_path)
        if not base.is_absolute():
            # по умолчанию ищем файл рядом с этим модулем (корень проекта)
            base = Path(__file__).resolve().parent / base
        self.base_path: Path = base
        self.path: Path = base / self.FILENAME

        self._locations: Dict[str, Dict[str, Any]] = {}
        self._location_order: List[str] = []
        self._points: Dict[str, Dict[str, Any]] = {}
        self._point_location: Dict[str, str] = {}
        self._location_points: Dict[str, List[str]] = {}
        # уроки локации по порядку — нужны для «локация пройдена» без
        # обращения к состояниям блоков (иначе зацикливание)
        self._location_lessons: Dict[str, List[str]] = {}
        self._point_lessons: Dict[str, List[str]] = {}
        self._lesson_point: Dict[str, str] = {}
        self._lesson_order: List[str] = []
        self._point_numbers: Dict[str, int] = {}

        self._load()

    # =====================================================
    # Загрузка
    # =====================================================
    def _load(self) -> None:
        """Прочитать curriculum.json и разложить точки/уроки в словари.

        Любая проблема (нет файла, битый JSON) → WARNING и «пустая карта».
        """
        # сброс на случай повторной загрузки (reload)
        self._locations, self._location_order = {}, []
        self._points, self._point_location, self._location_points = {}, {}, {}
        self._point_lessons, self._lesson_point, self._lesson_order = {}, {}, []
        self._point_numbers = {}

        if not self.path.is_file():
            _log.warning("Карта: %s не найден — работаю без данных", self.path)
            return

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _log.warning("Карта: не удалось прочитать %s (%s)", self.path, exc)
            return

        if not isinstance(raw, dict):
            _log.warning("Карта: корень файла не объект JSON — игнорирую")
            return

        locations = raw.get("locations")
        if not isinstance(locations, list):
            _log.warning("Карта: нет списка 'locations' — игнорирую")
            return

        for loc in locations:
            if not isinstance(loc, dict):
                continue
            loc_id = str(loc.get("id") or "").strip()
            if not loc_id or loc_id in self._locations:
                continue
            self._locations[loc_id] = loc
            self._location_order.append(loc_id)
            self._load_points(loc_id, loc)

        _log.info("Карта: локаций %d, точек %d, уроков %d",
                  len(self._location_order), len(self._points), len(self._lesson_order))

    def _load_points(self, loc_id: str, loc: Dict[str, Any]) -> None:
        """Разложить точки локации по порядку `number` и собрать уроки."""
        points = loc.get("points")
        if not isinstance(points, list):
            # на случай старого формата ("blocks") — не падаем, просто пусто
            self._location_points[loc_id] = []
            return

        prepared: List[Tuple[int, int, Dict[str, Any]]] = []
        for idx, point in enumerate(points):
            if not isinstance(point, dict):
                continue
            number = _as_int(point.get("number"))
            prepared.append((number if number is not None else 10 ** 6, idx, point))

        # порядок — по полю `number`; при равенстве/отсутствии — как в файле
        prepared.sort(key=lambda item: (item[0], item[1]))

        ids: List[str] = []
        for order_no, _idx, point in prepared:
            point_id = str(point.get("id") or "").strip()
            if not point_id or point_id in self._points:
                continue
            self._points[point_id] = point
            self._point_location[point_id] = loc_id
            self._point_numbers[point_id] = order_no if order_no != 10 ** 6 else len(ids) + 1
            lesson_ids = [self._register_lesson(lesson, point_id)
                          for lesson in self._iter_lessons(point)]
            lesson_ids = [lid for lid in lesson_ids if lid]
            self._point_lessons[point_id] = lesson_ids
            self._lesson_order.extend(lesson_ids)
            ids.append(point_id)

        self._location_points[loc_id] = ids
        # уроки ЭТОЙ локации — просто все уроки её блоков по порядку
        self._location_lessons[loc_id] = [lid for pid in ids
                                          for lid in self._point_lessons[pid]]

    def _register_lesson(self, lesson: Dict[str, Any], point_id: str) -> str:
        """Запомнить урок (id → его точка). Повтор id игнорируем."""
        lesson_id = str(lesson.get("id") or "").strip()
        if not lesson_id or lesson_id in self._lesson_point:
            return ""
        self._lesson_point[lesson_id] = point_id
        return lesson_id

    @classmethod
    def _iter_lessons(cls, point: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Уроки точки по порядку, включая вложенные `sublessons` (рекурсия)."""
        for lesson in point.get("lessons") or []:
            if not isinstance(lesson, dict):
                continue
            yield lesson
            subs = lesson.get("sublessons")
            if isinstance(subs, list):
                yield from cls._iter_lessons({"lessons": subs})

    def reload(self) -> None:
        """Перечитать файл (например, если он был отредактирован)."""
        self._load()

    # =====================================================
    # Доступ к данным
    # =====================================================
    def location_ids(self) -> List[str]:
        """id локаций по порядку (как в файле)."""
        return list(self._location_order)

    def get_location(self, location_id: str) -> Dict[str, Any]:
        """Локация по id. Неизвестный id → пустой словарь."""
        return self._locations.get(str(location_id or ""), {})

    def points_of(self, location_id: str) -> List[Dict[str, Any]]:
        """Точки локации по порядку прохождения. Нет данных → []."""
        ids = self._location_points.get(str(location_id or ""), [])
        return [self._points[pid] for pid in ids if pid in self._points]

    def get_point(self, point_id: str) -> Dict[str, Any]:
        """Точка (блок) по id. Неизвестный id → пустой словарь."""
        return self._points.get(str(point_id or ""), {})

    def lessons_of(self, point_id: str) -> List[Dict[str, Any]]:
        """Уроки точки по порядку (включая вложенные). Нет данных → []."""
        ids = self._point_lessons.get(str(point_id or ""), [])
        out = []
        for lid in ids:
            found = self._find_lesson(lid)
            if found:
                out.append(found)
        return out

    def get_lesson(self, lesson_id: str) -> Dict[str, Any]:
        """Урок по id. Неизвестный id → пустой словарь."""
        return self._find_lesson(str(lesson_id or "")) or {}

    def _find_lesson(self, lesson_id: str) -> Optional[Dict[str, Any]]:
        """Найти словарь урока в его точке (уроки уникальны в пределах локации)."""
        point_id = self._lesson_point.get(lesson_id)
        if not point_id:
            return None
        for lesson in self._iter_lessons(self._points.get(point_id, {})):
            if str(lesson.get("id") or "") == lesson_id:
                return lesson
        return None

    # =====================================================
    # Состояния (пройдено / открыто / закрыто)
    # =====================================================
    # ---------- уровень ученика: что считаем пройденным ----------
    # РЕШЕНИЕ УЧЕНИКА 25.10.2026 (вариант В). Вступительный тест уже показал,
    # что темы ниже его уровня он закрыл, поэтому такие локации считаем
    # ПРОЙДЕННЫМИ: карта зелёная, автозапуск урока их не выбирает. Пройти их
    # вручную всё равно можно в любой момент — в окне блока кнопка «Начать»
    # не спрашивает состояние (ui/panels/block_panel.py).
    @staticmethod
    def level_rank(level: Any) -> int:
        """Место уровня в шкале A0..C1. Неизвестный/пустой → -1."""
        name = str(level or "").strip().upper()
        return _CEFR_ORDER.index(name) if name in _CEFR_ORDER else -1

    def skipped_lessons(self, profile: Optional[Dict[str, Any]]) -> Set[str]:
        """Уроки локаций, чей уровень НИЖЕ уровня ученика.

        Пустой ответ, если уровня нет (обратная совместимость: карта как
        раньше начинается с первых уроков) или он самый низкий (A0).
        """
        if not isinstance(profile, dict):
            return set()
        rank = self.level_rank(profile.get("level"))
        if rank <= 0:
            return set()
        out: Set[str] = set()
        for loc_id in self._location_order:
            loc = self._locations.get(loc_id) or {}
            if 0 <= self.level_rank(loc.get("level")) < rank:
                out.update(self._location_lessons.get(loc_id, []))
        return out

    def done_lessons(self, profile: Optional[Dict[str, Any]]) -> Set[str]:
        """Пройденное по факту = записанное в профиле + пропущенное по уровню."""
        done = set(self.completed_lessons(profile))
        done.update(self.skipped_lessons(profile))
        return done

    @staticmethod
    def completed_lessons(profile: Optional[Dict[str, Any]]) -> Set[str]:
        """Множество пройденных уроков из профиля. Аккуратно к битым данным."""
        if not isinstance(profile, dict):
            return set()
        done = profile.get("completed_lessons")
        if not isinstance(done, (list, tuple, set)):
            return set()
        return {str(x) for x in done if str(x).strip()}

    def get_lesson_state(self, lesson_id: str, profile: Optional[Dict[str, Any]]) -> str:
        """Состояние урока: "completed" | "unlocked" | "locked".

        Первый урок (в порядке прохождения) всегда открыт; следующий —
        только после предыдущего. Неизвестный урок → "locked".
        """
        lesson_id = str(lesson_id or "")
        if lesson_id in self.done_lessons(profile):
            return COMPLETED
        if lesson_id not in self._lesson_point:
            return LOCKED
        # локация закрыта — в ней закрыто всё, даже первый урок
        loc_id = self._point_location.get(self._lesson_point.get(lesson_id))
        if loc_id and not self.is_location_unlocked(loc_id, profile):
            return LOCKED
        idx = self._lesson_order.index(lesson_id)
        if idx == 0:
            return UNLOCKED
        previous = self._lesson_order[idx - 1]
        if previous in self.done_lessons(profile):
            return UNLOCKED
        return LOCKED

    def get_point_state(self, point_id: str, profile: Optional[Dict[str, Any]]) -> str:
        """Состояние точки (блока): "completed" | "unlocked" | "locked".

        * completed — все уроки точки пройдены (и уроки вообще есть);
        * unlocked — первая точка локации или предыдущая уже completed;
        * locked — иначе. Неизвестная точка → "locked".
        """
        point_id = str(point_id or "")
        if point_id not in self._points:
            return LOCKED
        done = self.done_lessons(profile)
        lessons = self._point_lessons.get(point_id, [])
        if lessons and all(lid in done for lid in lessons):
            return COMPLETED

        loc_id = self._point_location.get(point_id)
        # локация закрыта — все её блоки закрыты (иначе на карте чужого
        # мира горел зелёный «открытый» жетон, см. get_location_state)
        if loc_id and not self.is_location_unlocked(loc_id, profile):
            return LOCKED
        order = self._location_points.get(loc_id, [])
        if point_id not in order:
            return LOCKED
        idx = order.index(point_id)
        if idx == 0:
            return UNLOCKED
        previous = order[idx - 1]
        return UNLOCKED if self.get_point_state(previous, profile) == COMPLETED else LOCKED

    def is_location_completed(self, location_id: str,
                               profile: Optional[Dict[str, Any]]) -> bool:
        """Все уроки локации пройдены (и уроки вообще есть).

        Считаем по УРОКАМ, а не по блокам: состояние блока само зависит от
        состояния локации (get_point_state), и через блоки получилось бы
        зацикливание «локация → блок → локация».
        """
        lessons = self._location_lessons.get(str(location_id or ""), [])
        if not lessons:
            return False
        done = self.done_lessons(profile)
        return all(lid in done for lid in lessons)

    def get_location_state(self, location_id: str,
                           profile: Optional[Dict[str, Any]]) -> str:
        """Состояние ЛОКАЦИИ: "completed" | "unlocked" | "locked".

        Локации идут по порядку (как в файле плана), прохождение линейное:
          * completed — все блоки локации пройдены;
          * unlocked — первая локация или предыдущая уже completed;
          * locked — иначе.

        Раньше проверялось только внутри локации, и первая точка ВТОРОЙ
        локации показывалась открытой, хотя до неё ещё не дошли (видно на
        карте: зелёный пульсирующий жетон в закрытом мире).
        """
        location_id = str(location_id or "")
        if location_id not in self._locations:
            return LOCKED
        if self.is_location_completed(location_id, profile):
            return COMPLETED
        order = self._location_order
        if location_id not in order:
            return LOCKED
        idx = order.index(location_id)
        if idx == 0:
            return UNLOCKED
        previous = order[idx - 1]
        return (UNLOCKED if self.is_location_completed(previous, profile)
                else LOCKED)

    def is_location_unlocked(self, location_id: str,
                             profile: Optional[Dict[str, Any]]) -> bool:
        """В эту локацию уже можно заходить?"""
        return self.get_location_state(location_id, profile) != LOCKED

    def first_open_location(self, profile: Optional[Dict[str, Any]]) -> str:
        """Первая НЕ пройденная до конца открытая локация (для карты).

        Так карта сама показывает то место, где ученик сейчас, а не всегда
        первую локацию. Всё пройдено → последняя. Пустой план → "".
        """
        for location_id in self._location_order:
            if not self.is_location_completed(location_id, profile):
                return location_id
        return self._location_order[-1] if self._location_order else ""

    def next_lesson(self, profile: Optional[Dict[str, Any]]) -> Optional[str]:
        """id ПЕРВОГО непройденного урока по порядку карты.

        По этому уроку Джейн сама начинает занятие, когда ученик поздоровался
        (решение §14.5). Порядок линейный, как в `_lesson_order`: уроки внутри
        точки, точки по полю `number`. Все уроки пройдены → None; пустая карта →
        None. Битый профиль не мешает: берём то, что удалось прочитать.
        """
        done = self.done_lessons(profile)
        for lesson_id in self._lesson_order:
            if lesson_id not in done:
                return lesson_id
        return None

    def get_point_progress(self, point_id: str,
                           profile: Optional[Dict[str, Any]]) -> Tuple[int, int]:
        """(пройдено уроков, всего уроков) внутри точки."""
        lessons = self._point_lessons.get(str(point_id or ""), [])
        if not lessons:
            return (0, 0)
        done = self.done_lessons(profile)
        return (sum(1 for lid in lessons if lid in done), len(lessons))

    def get_location_progress(self, location_id: str,
                              profile: Optional[Dict[str, Any]]) -> Tuple[int, int]:
        """(пройдено точек, всего точек) в локации. Нет данных → (0, 0)."""
        order = self._location_points.get(str(location_id or ""), [])
        if not order:
            return (0, 0)
        done = sum(1 for pid in order
                   if self.get_point_state(pid, profile) == COMPLETED)
        return (done, len(order))


def _as_int(value: Any) -> Optional[int]:
    """Привести значение к int, если это возможно. Иначе None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
