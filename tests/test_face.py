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

    # ---------- 8. Моргание короткое ----------
    print("\n[8] Моргание не затянутое")
    d = cf.FaceAnimator(seed=9)
    d.set_state(cf.SPEAK_STORY)
    dt_b = 1 / 22.0                      # как в приложении
    episodes, start, t_b = [], None, 0.0
    while t_b < 20.0:
        f = d.tick(dt_b, level=60.0, speaking=True)
        closed_layer = f.eyes.startswith("eyes_closed")
        fading = bool(f.eyes_from and f.eyes_mix < 1.0 and
                      (closed_layer or f.eyes_from.startswith("eyes_closed")))
        visible = closed_layer or fading
        if visible and start is None:
            start = t_b
        elif not visible and start is not None:
            episodes.append(t_b - start)
            start = None
        t_b += dt_b
    longest_blink = max(episodes) if episodes else 0.0
    print("   эпизодов: %d, самый долгий %.2f с" % (len(episodes), longest_blink))
    check("моргания были", bool(episodes), len(episodes))
    check("моргание не дольше 0.18 с (с переходами)",
          longest_blink <= 0.18, round(longest_blink, 3))
    check("переход моргания резкий (BLINK_FADE мал)",
          cf.BLINK_FADE <= 0.05, cf.BLINK_FADE)

    # ---------- 9. Конец рассказа ----------
    print("\n[9] Конец рассказа: глаза закрыты ~3 с, потом покой")
    check("состояние story_end есть в таблице", cf.STORY_END in cf.STATES)
    cfg_end = cf.STATES[cf.STORY_END]
    check("в story_end глаза закрыты", cfg_end.eyes.startswith("eyes_closed"),
          cfg_end.eyes)
    check("держит около 3 с", abs(cfg_end.transient - 3.0) < 0.01, cfg_end.transient)
    check("после — возврат в покой", cfg_end.transient_to == cf.IDLE,
          cfg_end.transient_to)

    e = cf.FaceAnimator(seed=4)
    e.set_state(cf.STORY_END)
    held, t_e = 0.0, 0.0
    while e.state == cf.STORY_END and t_e < 6.0:
        e.tick(dt_b, level=0.0, speaking=False)
        held += dt_b
        t_e += dt_b
    check("story_end длится ~3 с", 2.7 <= held <= 3.5, round(held, 2))
    check("после story_end — покой", e.state == cf.IDLE, e.state)
    # ---------- 10. Глаза не выглядят закрытыми во время речи ----------
    print("\n[10] Во время речи глаза ОТКРЫТЫ")
    # Слои eyes_smile (19 px) и eyes_scorn (24 px) — тонкие дуги: на теле они
    # выглядят как ЗАКРЫТЫЕ глаза. В длинной речи их быть не должно, иначе
    # ученик думает, что Джейн зажмурилась надолго.
    speaking_states = (cf.SPEAKING, cf.SPEAK_HAPPY, cf.SPEAK_SAD,
                       cf.SPEAK_SURPRISED, cf.SPEAK_THINKING, cf.SPEAK_STORY)
    squint_in_speech = [name for name in speaking_states
                        if cf.STATES[name].eyes in cf.SQUINT_EYES]
    check("ни одно говорящее состояние не прищуривается", not squint_in_speech,
          squint_in_speech)
    check("радость в речи — открытые глаза",
          cf.STATES[cf.SPEAK_HAPPY].eyes not in cf.SQUINT_EYES,
          cf.STATES[cf.SPEAK_HAPPY].eyes)
    check("реакции-улыбки короткие (<= 1.7 с)",
          cf.STATES[cf.HAPPY].transient <= 1.7 and cf.STATES[cf.SMILE].transient <= 1.7,
          (cf.STATES[cf.HAPPY].transient, cf.STATES[cf.SMILE].transient))

    # ---------- 11. Нет длинных промежуточных кадров ----------
    print("\n[11] Смена глаз без «полузакрытых» промежуточных кадров")
    check("переход короче 0.06 с (иначе 2-3 кадра с прищуром)",
          cf.EYES_FADE <= 0.06, cf.EYES_FADE)
    f_anim = cf.FaceAnimator(seed=3)
    f_anim.set_state(cf.SPEAKING)
    f_anim.set_state(cf.SPEAK_HAPPY)
    blended = 0
    for _ in range(12):
        frame = f_anim.tick(1 / 11.0, level=60.0, speaking=True)
        if frame.eyes_from and 0.0 < frame.eyes_mix < 1.0:
            blended += 1
    check("смешанных кадров не больше одного", blended <= 1, blended)

    # ---------- 12. Радостный текст говорит с открытыми глазами ----------
    print("\n[12] Радостный текст (эмодзи) — глаза открыты")
    import mood as mood_mod
    happy_plan = mood_mod.plan_reply(
        "Hello! 😊 How are you this evening? Planning anything fun? ✨")
    bad = []
    for seg in happy_plan.segments:
        state = cf.state_for_mood(seg.mood, story=happy_plan.story)
        if cf.STATES[state].eyes in cf.SQUINT_EYES:
            bad.append((seg.mood, state, cf.STATES[state].eyes))
    check("ни один кусок не даёт прищура", not bad, bad)
    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
