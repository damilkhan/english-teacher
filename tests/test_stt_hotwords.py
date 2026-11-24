# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_STT_HOTWORDS.PY — подсказка распознаванию: коротко и имена первыми
# =========================================================
#   python tests\test_stt_hotwords.py   (модель Whisper НЕ нужна)
#
# ЗАМЕР 24.11.2026, tools/stt_eval.py, 40 живых записей ученика. Фраза
# «Ann took the black phone» (city/4.3), 15 записей:
#
#   подсказка                 имя Ann   вся фраза
#   нет (как было в живом)      0/15      10/15
#   только имена (4 слова)     15/15      15/15
#   имена + слова урока        13/15      14/15
#   имена + чужие слова (8)     8/15      15/15
#   имена + чужие слова (20)   12/15      15/15
#   чужие слова, имена В КОНЦЕ  0/15      15/15   <- имена в конце бесполезны
#
# Выводы, которые проверяем здесь:
#   1) подсказка РЕЖЕТСЯ до STT_HOTWORDS_MAX слов (длинная размывается);
#   2) режется с КОНЦА, порядок не меняется: имена идут первыми;
#   3) 0 — не резать (прежнее поведение возвращается одной настройкой).
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

import config                                   # noqa: E402
import stt_engine                               # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    eng = stt_engine.STTEngine()
    limit = getattr(config, "STT_HOTWORDS_MAX", None)
    print("[1] Настройка есть и осмысленна")
    check("config.STT_HOTWORDS_MAX существует", limit is not None, limit)
    check("предел 4..64 (имена помещаются, мусор не лезет)", 4 <= int(limit) <= 64, limit)

    print("\n[2] Подсказка режется С КОНЦА, имена остаются первыми")
    names = "Ann, Anna, Tom, Damil"
    tail = ", ".join(["jacket", "size", "card", "receipt", "bill", "toilet",
                      "recommend", "shall", "could i have", "i would like",
                      "please", "expensive", "cheaper", "battery", "door",
                      "apartment", "table", "window", "morning"])
    full = names + ", " + tail
    cut = eng._limit_hotwords(full)
    check("стало не длиннее предела", len(cut.split()) <= int(limit), cut)
    check("имена остались на месте", cut.startswith("Ann, Anna, Tom, Damil"), cut)
    check("хвост отрезан (последнее слово из tail не попало)",
          "shall" not in cut.split(), cut)

    print("\n[3] Короткая подсказка не трогается")
    check("4 слова остаются как есть",
          eng._limit_hotwords(names) == names, eng._limit_hotwords(names))
    check("пустая подсказка — пустая строка",
          eng._limit_hotwords("") == "", repr(eng._limit_hotwords("")))
    check("None не роняет", eng._limit_hotwords(None) == "",
          repr(eng._limit_hotwords(None)))

    print("\n[4] Выключатель: 0 = не резать (прежнее поведение)")
    saved = config.STT_HOTWORDS_MAX
    try:
        config.STT_HOTWORDS_MAX = 0
        check("при 0 подсказка целиком", eng._limit_hotwords(full) == full)
    finally:
        config.STT_HOTWORDS_MAX = saved

    print("\n[5] Провайдер подсказки тоже режется (путь из окна)")
    got = {}

    def provider():
        return full

    eng2 = stt_engine.STTEngine(hotwords_provider=provider)
    res = eng2._resolve_hotwords()
    got["len"] = len(res.split())
    check("подсказка из провайдера не длиннее предела", got["len"] <= int(limit), res)
    check("имена первыми", res.startswith("Ann"), res)

    print("\n[6] Пустой провайдер не ломает")
    eng3 = stt_engine.STTEngine(hotwords_provider=lambda: "")
    check("пусто — просто пусто", eng3._resolve_hotwords() == "",
          repr(eng3._resolve_hotwords()))

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
