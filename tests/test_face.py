# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_FACE.PY — анимация лица робота (характер, взгляд, моргание)
# =========================================================
#   python tests\test_face.py   (окно НЕ создаётся)
#
# Проверяем «живость» и, главное, ОТСУТСТВИЕ ЗАЛИПАНИЙ:
#   1) блуждание взгляда: глаза возвращаются, а не остаются вбок;
#   2) жёсткий предел удержания взгляда (GAZE_MAX_HOLD);
#   3) начатое моргание всегда доигрывается (даже при смене эмоции);
#   4) смена эмоции сбрасывает «временные» состояния;
#   5) в рассказе лицо живо: есть и моргания, и взгляды;
#   6) таблица эмоций: у всех состояний есть глаза и рты из файлов.
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

import character_face as cf                                # noqa: E402

FAILED = []
SIDE_EYES = ("eyes_left", "eyes_right", "eyes_upstairs", "eyes_down")


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def run(anim, seconds, dt=1 / 30.0, level=60.0, speaking=True):
    """Прокрутить анимацию и вернуть список (время, глаза, состояние)."""
    frames = []
    t = 0.0
    steps = int(seconds / dt)
    for _ in range(steps):
        frame = anim.tick(dt, level=level, speaking=speaking)
        frames.append((t, frame.eyes, frame.state))
        t += dt
    return frames


def side_runs(frames):
    """Длительности подряд идущих «взглядов в сторону»."""
    runs, cur = [], 0.0
    step = frames[0][0] + 1e-9 if frames else 0.033
    for i, (_t, eyes, _s) in enumerate(frames):
        if eyes in SIDE_EYES:
            cur += (frames[1][0] - frames[0][0]) if len(frames) > 1 else 0.033
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0.0
    if cur > 0:
        runs.append(cur)
    return runs


def main():
    print("=" * 60)
    print("Проверка анимации лица (character_face)")
    print("=" * 60)

    dt = 1 / 30.0

    # ---------- 1. Взгляд возвращается ----------
    print("\n[1] Взгляд уходит в сторону и ВОЗВРАЩАЕТСЯ")
    anim = cf.FaceAnimator(seed=5)
    anim.set_state(cf.SPEAK_STORY)
    frames = run(anim, 20)
    eyes_seen = {e for _t, e, _s in frames}
    check("взгляд гуляет (были направления)", bool(eyes_seen & set(SIDE_EYES)),
          sorted(eyes_seen))
    # после любого взгляда глаза ОБЯЗАНЫ вернуться (не «залипнуть» вбок):
    # прокручиваем ещё пару секунд и проверяем, что центр наступил
    tail = run(anim, 3.0)
    back_center = any(e not in SIDE_EYES for _t, e, _s in tail)
    check("после взгляда глаза возвращаются в центр", back_center,
          [e for _t, e, _s in tail][:8])
    check("последний взгляд не длиннее предела",
          anim._gaze_time <= cf.GAZE_MAX_HOLD, round(anim._gaze_time, 2))

    # ---------- 2. Жёсткий предел ----------
    print("\n[2] Взгляд не держится дольше предела")
    runs = side_runs(frames)
    longest = max(runs) if runs else 0.0
    check("есть хотя бы один взгляд", bool(runs), len(runs))
    check("самый долгий взгляд не дольше %.1f с" % (cf.GAZE_MAX_HOLD + 0.1),
          longest <= cf.GAZE_MAX_HOLD + 0.1, round(longest, 2))
    print("   взглядов за 20 с: %d, самый долгий %.2f с" % (len(runs), longest))

    # ---------- 3. Моргание доигрывается ----------
    print("\n[3] Начатое моргание доигрывается при смене эмоции")
    a = cf.FaceAnimator(seed=1)
    a.set_state(cf.SPEAK_STORY)
    # докручиваем до начала моргания
    for _ in range(int(20 / dt)):
        a.tick(dt, level=60.0, speaking=True)
        if a._blink_left > 0.0:
            break
    started = a._blink_left > 0.0
    check("моргание началось", started, a._blink_left)
    a.set_state(cf.SPEAK_SAD)             # эмоция без моргания «в процессе»
    check("смена эмоции сбросила счётчик моргания",
          a._blink_left == 0.0, a._blink_left)
    check("глаза не остались закрытыми", a._eyes not in ("eyes_closed", "eyes_closed_shut"),
          a._eyes)

    # ---------- 4. Сброс состояний ----------
    print("\n[4] Смена эмоции сбрасывает временные состояния")
    b = cf.FaceAnimator(seed=2)
    b.set_state(cf.SPEAK_STORY)
    run(b, 6)                              # пусть накопятся взгляды/моргания
    b.set_state(cf.IDLE)
    check("взгляд сброшен", b._gaze_eyes == "" and b._gaze_left <= 0.0,
          (b._gaze_eyes, b._gaze_left))
    check("кивки сброшены", b._nod_queue == 0 and b._nod_left == 0.0)
    check("моргание сброшено", b._blink_left == 0.0, b._blink_left)

    # ---------- 5. Живость в рассказе ----------
    print("\n[5] Во время рассказа лицо живое")
    c = cf.FaceAnimator(seed=3)
    c.set_state(cf.SPEAK_STORY)
    frames2 = run(c, 25)
    blinks = sum(1 for i in range(1, len(frames2))
                 if frames2[i][1].startswith("eyes_closed")
                 and not frames2[i - 1][1].startswith("eyes_closed"))
    gazes = sum(1 for i in range(1, len(frames2))
                if frames2[i][1] in SIDE_EYES and frames2[i - 1][1] not in SIDE_EYES)
    print("   за 25 с: морганий %d, взглядов %d" % (blinks, gazes))
    check("моргает не реже раза в 10 с", blinks >= 2, blinks)
    check("смотрит по сторонам не реже раза в 10 с", gazes >= 2, gazes)
    check("ничего не залипло в конце",
          c._eyes not in SIDE_EYES and not c._eyes.startswith("eyes_closed"), c._eyes)

    # ---------- 6. Таблица эмоций ----------
    print("\n[6] Состояния ссылаются на существующие слои")
    layers = cf.layer_names(os.path.join(ROOT, "assets", "character"))
    available = set(n[:-4] for n in layers["eyes"] + layers["mouth"])
    check("слои найдены", len(available) > 15, len(available))
    missing = []
    for name, cfg in cf.STATES.items():
        for field_name in ("eyes", "mouth_closed", "mouth_half", "mouth_open",
                           "static_mouth"):
            value = getattr(cfg, field_name)
            if value and value not in available:
                missing.append("%s.%s=%s" % (name, field_name, value))
        for value in cfg.mouth_cycle:
            if value not in available:
                missing.append("%s.cycle=%s" % (name, value))
    check("все слои состояний существуют", not missing, missing[:5])

    # ---------- 7. Настроение → состояние ----------
    print("\n[7] Настроение текста → лицо")
    check("радость → говорящее радостное",
          cf.state_for_mood("happy") == cf.SPEAK_HAPPY)
    check("грусть → говорящее грустное",
          cf.state_for_mood("sad") == cf.SPEAK_SAD)
    check("нейтрально в рассказе → режим рассказа",
          cf.state_for_mood("neutral", story=True) == cf.SPEAK_STORY)
    check("грустное состояние умеет гулять взглядом",
          cf.STATES[cf.SPEAK_SAD].gaze is True)
    check("рассказ умеет гулять взглядом",
          cf.STATES[cf.SPEAK_STORY].gaze is True)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
