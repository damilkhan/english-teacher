# =========================================================
# TESTS/TEST_LOCKED_LESSONS.PY — закрытое НЕЛЬЗЯ начать
# =========================================================
#   python tests/test_locked_lessons.py
#
# ЗАЧЕМ (жалоба ученика 25.10.2026): уроки запускались и из красных
# жетонов, и внутри закрытого блока. Правильных замков три, и все три
# отсутствовали:
#   1) клик по красному жетону — окно блока не открывается;
#   2) в окне блока закрытый урок — серая кнопка «закрыто» (без Tk
#      проверяем данные: states доходят до окна);
#   3) start_lesson отказывает закрытому уроку (защита в глубине).
# Окно не создаём: проверяем методы на «пустышке».
# =========================================================

import inspect
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import progress_map as pm_mod                                      # noqa: E402
from progress_map import ProgressMap, UNLOCKED, LOCKED             # noqa: E402
from ui.app import (EnglishTeacherApp, BLOCK_LOCKED_NOTE,          # noqa: E402
                    LESSON_LOCKED_NOTE)
from ui.panels.block_panel import (BlockPanel, STATE_LOCKED,       # noqa: E402
                                   LOCKED_TEXT)

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def blank_app(profile=None):
    """Пустышка приложения: только то, что нужно методам замков."""
    app = types.SimpleNamespace()
    app.progress_map = ProgressMap()
    app._active_profile = lambda: dict(profile or {})
    app.messages = []
    app.add_message = lambda who, what: app.messages.append(what)
    app.teacher_name = "Вербот"
    app.palette = {}
    app.window = None
    # методы самого приложения, которые зовут друг друга
    app._block_is_locked = (lambda pid, prof=None:
                            EnglishTeacherApp._block_is_locked(app, pid, prof))
    app._lesson_is_locked = (lambda lid:
                             EnglishTeacherApp._lesson_is_locked(app, lid))
    app._block_lesson_states = (lambda point, prof=None:
                                EnglishTeacherApp._block_lesson_states(
                                    app, point, prof))
    app._lesson_data = (lambda lid, pid=None:
                        EnglishTeacherApp._lesson_data(app, lid, pid))
    # 🧪 тестовый режим «сразу конец урока»: файла-флага в тестах нет
    app._test_tail_flag = lambda: False
    return app


def two_blocks():
    """(карта, id первого блока, id второго блока) — или None."""
    pm = ProgressMap()
    points = pm.points_of(pm.location_ids()[0])
    if len(points) < 2:
        return None
    return pm, str(points[0]["id"]), str(points[1]["id"])


# =========================================================
# 1. Карта: закрытые блоки и уроки существуют
# =========================================================
def test_map_states():
    print("\n[1] Карта: первый блок открыт, второй закрыт")
    found = two_blocks()
    check("в локации есть минимум два блока", found is not None, found)
    if found is None:
        return
    pm, p1, p2 = found
    check("первый блок открыт",
          pm.get_point_state(p1, {}) == UNLOCKED, pm.get_point_state(p1, {}))
    check("второй блок закрыт",
          pm.get_point_state(p2, {}) == LOCKED, pm.get_point_state(p2, {}))
    lessons2 = pm.lessons_of(p2)
    check("во втором блоке есть уроки", bool(lessons2), lessons2)
    if lessons2:
        lid = str(lessons2[-1].get("id"))
        check("урок закрытого блока закрыт",
              pm.get_lesson_state(lid, {}) == LOCKED,
              pm.get_lesson_state(lid, {}))


# =========================================================
# 2. Замки на стороне приложения
# =========================================================
def test_app_guards():
    print("\n[2] app: _block_is_locked / _lesson_is_locked")
    found = two_blocks()
    if found is None:
        check("нужно минимум два блока", False)
        return
    pm, p1, p2 = found
    app = blank_app({})
    check("открытый блок — не закрыт",
          EnglishTeacherApp._block_is_locked(app, p1) is False, True)
    check("красный блок — закрыт",
          EnglishTeacherApp._block_is_locked(app, p2) is True, False)
    lessons1 = pm.lessons_of(p1)
    if lessons1:
        first_lesson = str(lessons1[0].get("id"))
        check("первый урок локации открыт",
              EnglishTeacherApp._lesson_is_locked(app, first_lesson) is False,
              True)
    lessons2 = pm.lessons_of(p2)
    if lessons2:
        far = str(lessons2[-1].get("id"))
        check("урок красного блока закрыт",
              EnglishTeacherApp._lesson_is_locked(app, far) is True, False)
    check("неизвестный урок — не падаем",
          isinstance(EnglishTeacherApp._lesson_is_locked(app, "нет/такого"), bool),
          True)


# =========================================================
# 3. Состояния уроков уходят в окно блока
# =========================================================
def test_states_to_panel():
    print("\n[3] app: _block_lesson_states и окно блока принимает их")
    found = two_blocks()
    if found is None:
        check("нужно минимум два блока", False)
        return
    pm, _p1, p2 = found
    app = blank_app({})
    point = pm.get_point(p2)
    states = EnglishTeacherApp._block_lesson_states(app, point)
    ids = [str(l.get("id")) for l in pm.lessons_of(p2)]
    check("состояние есть у каждого урока", set(ids) <= set(states), states)
    check("все уроки красного блока закрыты",
          all(states.get(i) == pm_mod.LOCKED for i in ids), states)
    sig = inspect.signature(BlockPanel.ask)
    check("BlockPanel.ask принимает exams", "exams" in sig.parameters, sig)
    check("BlockPanel.ask принимает states", "states" in sig.parameters, sig)
    check("новые параметры — по умолчанию пустые",
          sig.parameters["exams"].default is None
          and sig.parameters["states"].default is None, sig)
    check("подпись закрытого урока", LOCKED_TEXT == "закрыто", LOCKED_TEXT)
    check("имя состояния совпадает с картой", STATE_LOCKED == LOCKED,
          STATE_LOCKED)


# =========================================================
# 4. Клик по красному жетону: окно не открывается
# =========================================================
def test_click_locked():
    print("\n[4] on_point_click по красному жетону — окно НЕ открывается")
    found = two_blocks()
    if found is None:
        check("нужно минимум два блока", False)
        return
    _pm, _p1, p2 = found
    app = blank_app({})
    calls = []
    orig = BlockPanel.ask
    BlockPanel.ask = classmethod(lambda cls, *a, **k: calls.append(a) or None)
    try:
        EnglishTeacherApp.on_point_click(app, p2)
    finally:
        BlockPanel.ask = orig
    check("окно блока не открывалось", calls == [], calls)
    check("ученику сказано, почему",
          app.messages and app.messages[-1] == BLOCK_LOCKED_NOTE,
          app.messages[-1:])


# =========================================================
# 5. start_lesson отказывает закрытому уроку
# =========================================================
def test_start_locked():
    print("\n[5] start_lesson: закрытый урок не начинается")
    found = two_blocks()
    if found is None:
        check("нужно минимум два блока", False)
        return
    pm, _p1, p2 = found
    lessons2 = pm.lessons_of(p2)
    if not lessons2:
        check("в блоке есть уроки", False)
        return
    lid = str(lessons2[-1].get("id"))
    app = blank_app({})
    app.profile_ready = True
    app.lesson = types.SimpleNamespace(is_active=False)
    begun = []
    app._begin_lesson = lambda data, **k: begun.append(data) or data
    app._microphone_ready = lambda: (True, "")
    result = EnglishTeacherApp.start_lesson(app, lid, p2)
    check("урок НЕ начался", begun == [], begun)
    check("вернули None", result is None, result)
    check("ученику сказано, почему",
          app.messages and app.messages[-1] == LESSON_LOCKED_NOTE,
          app.messages[-1:])


def main():
    test_map_states()
    test_app_guards()
    test_states_to_panel()
    test_click_locked()
    test_start_locked()
    print("\n" + ("ИТОГ: все проверки пройдены" if not FAILED
                  else "ИТОГ: провалов %d — %s" % (len(FAILED), ", ".join(FAILED))))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
