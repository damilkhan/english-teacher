# -*- coding: utf-8 -*-
# =========================================================
# TEST_SCENE_DRILL.PY — дрилл по прошлой ошибке ПЕРЕД сценой
# =========================================================
#   python tests\test_scene_drill.py        (окно не нужно)
#
# Живое занятие 09.11.2026 (сцена a2.shop): дрилл по прошлой ошибке НЕ
# запустился, потому что жил только в ветке «урок ведёт модель». На всём пути
# сцен он был мёртв (решение 106: дрилл проверяет только целевую правку).
#
# Ещё жалоба ученика: он членораздельно повторял «I'm looking for a jacket»,
# а записывалось «i'm looking at jacket». Вопрос сцены известен заранее —
# слова его слота отдаются распознаванию как подсказка.
#
# Проверяем:
#   1) подсказки слота собираются (и пусты для незнакомого слота);
#   2) дрилл перед сценой задаётся, принимает верный ответ и не мешает сцене;
#   3) промах не молчит, попытки кончаются показом эталона;
#   4) после дрилла сцена всё равно начинается.
# =========================================================

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                                             # noqa: E402
import gaps                                               # noqa: E402
import scene_reactions                                    # noqa: E402
from ui import app as app_mod                             # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeSession:
    """Сессия сцены: всё, что нужно методам приложения."""

    def __init__(self):
        self.is_scene = True
        self.is_active = True
        self.scene_id = "a2.shop"
        self.scene_step = 1
        self.scene_q = 0


class FakeApp:
    """Заглушка приложения: чат, речь и урок без Tk."""

    def __init__(self, session, pair):
        self.messages = []
        self.said = []
        self.scenes_asked = []
        self.current_user = {"id": None}
        self.teacher_name = "Вербот"
        self._scene_drill = None
        self.lesson = types.SimpleNamespace(current=lambda: session)
        self._pair = pair
        self._real_top_pair = gaps.top_pair

    # --- методы, которые использует проверяемое приложение ---
    def add_message(self, who, text):
        self.messages.append(text)
        return text

    def _say(self, text, **_kw):
        self.said.append(text)
        return True

    def _wait_for_speech(self, action, step_ms=200):
        action()                    # в тесте речь «доиграла» сразу

    def _scene_ask(self, session):
        self.scenes_asked.append(session.scene_id)
        return True

    def _say_then_scene(self, session, english):
        # как в приложении: эталон вслух, потом первый вопрос сцены
        self._say(english)
        self._scene_ask(session)


def build(pair=None):
    session = FakeSession()
    fake = FakeApp(session, pair)
    gaps.top_pair = lambda *a, **k: pair
    return session, fake


def start_drill(fake, session):
    return app_mod.EnglishTeacherApp._start_scene_drill(fake, session)


def reply(fake, text):
    return app_mod.EnglishTeacherApp._scene_drill_reply(fake, text)


def main():
    print("=" * 60)
    print("Дрилл перед сценой и подсказки распознаванию")
    print("=" * 60)

    print("\n[1] Подсказки распознаванию по слоту сцены")
    words = scene_reactions.slot_hotwords("shop_item")
    check("слот магазина дал слова", len(words) >= 5, words)
    check("есть «just looking» (фраза, которую строит ученик)",
          any("just looking" == w.lower() for w in words), words)
    check("есть предмет «jacket»", any("jacket" == w.lower() for w in words), words)
    check("незнакомый слот → пусто", scene_reactions.slot_hotwords("nope") == [])
    check("без слота пусто", scene_reactions.slot_hotwords("") == [])

    print("\n[2] Дрилл задаётся перед сценой")
    pair = {"wrong": "i'm looking a jacket",
            "correct": "I'm looking for a jacket",
            "label": "порядок слов", "rule": "word_order", "count": 3}
    session, fake = build(pair)
    started = start_drill(fake, session)
    check("дрилл начался", started is True, started)
    check("в чате есть задание", any("Say it correctly" in m for m in fake.messages),
          fake.messages)
    check("названо, что сказал ученик",
          any("i'm looking a jacket" in m for m in fake.messages), fake.messages)
    check("сцена ещё НЕ началась", fake.scenes_asked == [], fake.scenes_asked)

    print("\n[3] Верный ответ принимается, сцена начинается")
    taken = reply(fake, "i'm looking for a jacket")
    check("реплику забрал дрилл", taken is True, taken)
    check("дрилл закрыт", fake._scene_drill is None, fake._scene_drill)
    check("эталон сказан вслух",
          any("I'm looking for a jacket" in s for s in fake.said), fake.said)
    check("сцена началась после дрилла", fake.scenes_asked == ["a2.shop"],
          fake.scenes_asked)

    print("\n[4] Промах не молчит, попытки кончаются эталоном")
    session, fake = build(pair)
    start_drill(fake, session)
    first = reply(fake, "i am looking jacket")
    check("промах забран дриллом (в модель не ушёл)", first is True, first)
    check("ученику сказано, как надо",
          any("Not quite" in m for m in fake.messages), fake.messages)
    check("сцена ещё не началась", fake.scenes_asked == [], fake.scenes_asked)
    second = reply(fake, "i want a bag please")
    check("вторая попытка тоже забрана", second is True, second)
    check("после попыток показан эталон",
          any("Correct:" in m for m in fake.messages), fake.messages)
    check("и сцена всё равно началась", fake.scenes_asked == ["a2.shop"],
          fake.scenes_asked)

    print("\n[5] Нет пары — нет дрилла, сцену не задерживаем")
    session, fake = build(None)
    check("дрилла нет", start_drill(fake, session) is False)
    check("в чат ничего лишнего", fake.messages == [], fake.messages)

    print("\n[6] Обычный урок дрилл перед сценой не трогает")
    session, fake = build(pair)
    session.is_scene = False
    check("для не-сцены метод молчит", start_drill(fake, session) is False)

    print("\n[7] Флаг config выключает дрилл")
    saved = getattr(config, "LESSON_MISTAKE_DRILL", True)
    config.LESSON_MISTAKE_DRILL = False
    try:
        session, fake = build(pair)
        check("дрилл выключен флагом", start_drill(fake, session) is False)
    finally:
        config.LESSON_MISTAKE_DRILL = saved

    gaps.top_pair = FakeApp._real_top_pair if hasattr(FakeApp, "_real_top_pair") else gaps.top_pair

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
