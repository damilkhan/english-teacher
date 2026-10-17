# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_REACTIONS.PY — реакция «справился после неудач»
# =========================================================
#   python tests\test_reactions.py   (окно НЕ создаётся)
#
# Проверяем:
#   1) до порога реакции нет;
#   2) после 3 неудач и верного ответа — «удивление → улыбка»;
#   3) серия неудач сбрасывается после похвалы;
#   4) ok=None (непонятный ответ) не ломает счёт;
#   5) разбор Аналитика → верно/неверно/непонятно;
#   6) длины шагов реакции (1.5 с удивление) и лица из character_face;
#   7) сценарий действительно проигрывается аниматором.
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import reactions as R                                     # noqa: E402
import character_face as cf                                # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("=" * 60)
    print("Проверка реакций робота (reactions.py)")
    print("=" * 60)

    # ---------- 1. До порога ----------
    print("\n[1] Пока неудач мало — реакции нет")
    t = R.ReactionTracker()
    check("одна неудача — тишина", t.record(False) is None)
    check("две неудачи — тишина", t.record(False) is None)
    check("серия = 2", t.streak == 2, t.streak)
    check("не в полосе неудач (нужно 3)", t.struggling is False)

    # ---------- 2. Три неудачи и успех ----------
    print("\n[2] Три неудачи → верный ответ → реакция")
    t = R.ReactionTracker()
    for _ in range(3):
        t.record(False)
    check("серия = 3", t.streak == 3)
    check("в полосе неудач", t.struggling is True)
    reaction = t.record(True)
    check("реакция сработала", bool(reaction), reaction)
    check("это похвала за старание",
          reaction.name == R.PRAISE_AFTER_STRUGGLE, reaction.name)

    # ---------- 3. Состав реакции ----------
    print("\n[3] Сценарий: удивление 1.5 с → улыбка")
    steps = dict(reaction.steps)
    check("первый шаг — удивление", list(steps)[0] == "surprised", list(steps))
    check("удивление ровно 1.5 с", abs(steps.get("surprised", 0) - 1.5) < 1e-9,
          steps.get("surprised"))
    check("второй шаг — улыбка", list(steps)[1] == "smile", list(steps))
    check("улыбка держится дольше 2 с", steps.get("smile", 0) >= 2.0,
          steps.get("smile"))
    check("состояния есть в таблице лица",
          all(s in cf.STATES for s in steps), list(steps))

    # ---------- 4. Сброс серии ----------
    print("\n[4] После похвалы счёт начинается заново")
    check("серия сброшена", t.streak == 0, t.streak)
    check("вторая реакция подряд не срабатывает", t.record(True) is None)
    check("счётчик похвал = 1", t.celebrated == 1, t.celebrated)
    for _ in range(3):
        t.record(False)
    check("после новой серии реакция снова есть", bool(t.record(True)))
    check("всего похвал 2", t.celebrated == 2, t.celebrated)

    # ---------- 5. Непонятный ответ ----------
    print("\n[5] Непонятный ответ (None) не ломает счёт")
    t = R.ReactionTracker()
    t.record(False)
    t.record(None)
    check("серия не изменилась", t.streak == 1, t.streak)
    t.record(False)
    t.record(False)
    check("дошли до трёх", t.streak == 3)
    check("None не сбрасывает серию", t.record(None) is None and t.streak == 3)

    # ---------- 6. Разбор Аналитика ----------
    print("\n[6] Разбор Аналитика → верно/неверно")
    check("ошибки → неверно",
          R.answer_is_correct({"ok": True, "move_status": "P",
                               "errors": [{"wrong": "go", "correct": "went"}]}) is False)
    check("доработать без ошибок → неверно",
          R.answer_is_correct({"ok": True, "move_status": "P", "errors": []}) is False)
    check("принято без ошибок → верно",
          R.answer_is_correct({"ok": True, "move_status": "A", "errors": []}) is True)
    check("нет разбора → непонятно", R.answer_is_correct(None) is None)
    check("сбой разбора (ok=False) → непонятно",
          R.answer_is_correct({"ok": False}) is None)

    # ---------- 7. Сценарий в аниматоре ----------
    print("\n[7] Сценарий проигрывается лицом")
    anim = cf.FaceAnimator(seed=1)
    anim.set_state("speaking")
    anim.play_sequence(reaction.steps)
    check("сценарий запущен", anim.in_sequence is True)
    check("сначала удивление", anim.state == "surprised", anim.state)
    t_sec = 0.0
    dt = 1 / 18
    seen = []
    surprise_sec = 0.0          # сколько ДЛИЛОСЬ удивление
    while anim.in_sequence and t_sec < 10:
        was_surprised = anim.state == "surprised"
        anim.tick(dt, level=0.0, speaking=False)
        if was_surprised:
            surprise_sec += dt
        if not seen or seen[-1] != anim.state:
            seen.append(anim.state)
        t_sec += dt
    check("после 1.5 с — улыбка", "smile" in seen, seen)
    check("в конце вернулся в исходное (speaking)", anim.state == "speaking", anim.state)
    check("удивление длилось ~1.5 с", 1.3 <= surprise_sec <= 1.7, round(surprise_sec, 2))
    check("вся реакция ~3.9 с", 3.5 <= t_sec <= 4.3, round(t_sec, 2))

    # ---------- 8. Безопасность ----------
    print("\n[8] Безопасные значения")
    check("порог 0 → 1", R.ReactionTracker(misses_before=0).misses_before == 1)
    check("порог строкой", R.ReactionTracker(misses_before="2").misses_before == 2)
    check("мусорный порог → 3", R.ReactionTracker(misses_before="abc").misses_before == 3)
    anim2 = cf.FaceAnimator(seed=2)
    anim2.play_sequence([])
    check("пустой сценарий не запускается", anim2.in_sequence is False)
    anim2.play_sequence([("нет-такого", 1.0)])
    check("неизвестное состояние игнорируется", anim2.in_sequence is False)
    tracker = R.ReactionTracker()
    tracker.reset()
    check("reset обнуляет всё",
          (tracker.streak, tracker.total_misses, tracker.celebrated) == (0, 0, 0))

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
