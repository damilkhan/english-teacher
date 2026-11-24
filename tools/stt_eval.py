# -*- coding: utf-8 -*-
"""stt_eval.py — замер распознавания на РЕАЛЬНЫХ записях ученика.

Зачем: решения по STT принимались на 3-8 файлах вручную. В logs/stt лежат
40 записей живых уроков — на них можно прогнать несколько вариантов и
сравнить ЧИСЛАМИ, а не «кажется лучше».

  python tools\stt_eval.py                 # все записи, все варианты
  python tools\stt_eval.py --limit 10      # первые 10 файлов (быстро)
  python tools\stt_eval.py --variants cur,beam5

Варианты (--variants):
  cur    small,   beam=1, language=en   (как СЕЙЧАС в приложении)
  beam5  small,   beam=5, language=en   (точнее, чуть медленнее)
  en     small.en (англоязычная модель; если не скачана — пропуск)
  prompt small,   beam=1, en + initial_prompt (контекст урока)
  base   base,    beam=1, language=en   (самый быстрый)
  med    medium,  beam=1, language=en   (ПСЕВДО-ЭТАЛОН, медленно)

Результат — logs/_stt_eval.txt и logs/_stt_eval.json.
Печать только ASCII: консоль Windows в cp1251 падает на кириллице.

ЧЕСТНО О ГРАНИЦАХ: эталон — модель medium, а не человек. Это значит,
что «правильно» здесь = «как слышит большая модель». Спорные файлы
помечаются SPOR, их ученик проверяет на слух (это ЕГО записи).
"""
import argparse
import glob
import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                      # noqa: E402
from scipy.io import wavfile                            # noqa: E402
from faster_whisper import WhisperModel                 # noqa: E402

FOLDER = os.path.join(ROOT, "logs", "stt")
OUT_TXT = os.path.join(ROOT, "logs", "_stt_eval.txt")
OUT_JSON = os.path.join(ROOT, "logs", "_stt_eval.json")

PROMPT = ("English lesson. Hello. Hi. Good morning. Good evening. How are you? I am fine, thanks. My name is. I am from. Nice to meet you. Goodbye. See you tomorrow. What is your name? Which phone did Ann take?")

VARIANTS = {
    # имя: (модель, beam, брать ли initial_prompt)
    "cur":    ("small", 1, False),
    "beam5":  ("small", 5, False),
    "en":     ("small.en", 1, False),
    "prompt": ("small", 1, True),
    "base":   ("base", 1, False),
    "med":    ("medium", 1, False),
    "hot":    ("small", 1, False, "NAMES"),
    "enhot":  ("small.en", 1, False, "NAMES"),
    "names":  ("small", 1, False, "ONLY_NAMES"),
    "enames": ("small.en", 1, False, "ONLY_NAMES"),
    "hfirst":  ("small", 1, False, "H_FIRST"),
    "hlast":   ("small", 1, False, "H_LAST"),
    "h8":      ("small", 1, False, "H_8"),
    "h12":     ("small", 1, False, "H_12"),
    "hslot":   ("small", 1, False, "H_SLOT"),
}

ONLY_NAMES = "Ann, Anna, Tom, Damil"

CONTEXT = "jacket, size, card, receipt, bill, toilet, recommend, shall, can i have, could i have, i would like, please, expensive, cheaper, battery, door"

FIRST20 = (ONLY_NAMES + ", " + CONTEXT).split()
HLAST20 = (CONTEXT + ", " + ONLY_NAMES).split()
FIRST20 = " ".join(FIRST20[:20])
FIRST8 = " ".join((ONLY_NAMES + ", " + CONTEXT).split()[:8])
LESSON = "phone, black, small, battery, expensive, cheaper, take, took, door, apartment"
HS = " ".join((ONLY_NAMES + ", " + LESSON).split()[:14])
FIRST12 = " ".join((ONLY_NAMES + ", " + CONTEXT).split()[:12])
HLAST20 = " ".join(HLAST20[:20])

NAMES = ("Ann, Anna, Tom, Damil, phone, black phone, small phone, "
         "battery, expensive, cheaper, door, apartment")

_models = {}


def model_for(size):
    if size in _models:
        return _models[size]
    print("  loading %s ..." % size)
    t0 = time.time()
    m = WhisperModel(size, device="cpu", compute_type="int8")
    print("  loaded %s in %.1f s" % (size, time.time() - t0))
    _models[size] = m
    return m


def load_wav(path):
    rate, data = wavfile.read(path)
    if data.ndim > 1:
        data = data[:, 0]
    return rate, data.astype(np.float32) / 32768.0


def run(path, size, beam, use_prompt, hotwords=""):
    rate, audio = load_wav(path)
    opts = dict(language="en", beam_size=beam, without_timestamps=True,
                condition_on_previous_text=False)
    if use_prompt:
        opts["initial_prompt"] = PROMPT
    if hotwords:
        opts["hotwords"] = hotwords
    t0 = time.time()
    segments, info = model_for(size).transcribe(audio, **opts)
    text = " ".join(s.text for s in segments).strip().lower()
    return text, time.time() - t0, float(getattr(info, "duration", 0.0) or 0.0)


def norm_words(text):
    out = []
    for w in str(text or "").lower().split():
        w = "".join(ch for ch in w if ch.isalnum() or ch == "'")
        if w:
            out.append(w)
    return out


def wer(ref, hyp):
    r, h = norm_words(ref), norm_words(hyp)
    if not r:
        return None
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, start=1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, start=1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (0 if rw == hw else 1))
        prev = cur
    return prev[len(h)] / float(len(r))


def looks_bad(text, dur):
    """Явный брак, который видно БЕЗ эталона."""
    words = norm_words(text)
    if not words:
        return True
    if len(set(words)) == 1 and len(words) >= 3:
        return True                    # цикл: "ok ok ok"
    latin = sum(1 for ch in str(text) if ch.isascii())
    if len(str(text)) and latin / float(len(str(text))) < 0.9:
        return True                    # не латиница: польский/немецкий
    if dur > 0.5 and len(words) > dur * 6:
        return True                    # больше 6 слов в секунду - галлюцинация
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--variants", default="cur,beam5,prompt,en,med")
    ap.add_argument("--only", default="")
    ap.add_argument("--from-json", action="store_true",
                    help="только отчёт по уже посчитанному _stt_eval.json")
    args = ap.parse_args()

    if args.from_json:
        with io.open(OUT_JSON, encoding="utf-8") as fh:
            rows = json.load(fh)
        names = [v.strip() for v in args.variants.split(",") if v.strip()]
        names = [n for n in names if any(n in (r.get("out") or {}) for r in rows)]
        write_report(rows, names)
        print("report rebuilt from %s" % os.path.basename(OUT_JSON))
        return 0

    files = sorted(glob.glob(os.path.join(FOLDER, "*.wav")))
    if args.only:
        names = [x.strip() for x in args.only.split(",") if x.strip()]
        files = [f for f in files if os.path.basename(f)[:15] in names]
    if args.limit:
        files = files[-args.limit:]
    names = [v.strip() for v in args.variants.split(",") if v.strip()]
    names = [n for n in names if n in VARIANTS]
    print("files: %d, variants: %s" % (len(files), ",".join(names)))

    rows = []
    for n, path in enumerate(files, start=1):
        base = os.path.basename(path)[:-4]
        row = {"file": base, "out": {}}
        for v in names:
            spec = VARIANTS[v]
            size, beam, use_prompt = spec[0], spec[1], spec[2]
            hot = ""
            if len(spec) > 3:
                hot = {"NAMES": NAMES, "ONLY_NAMES": ONLY_NAMES,
                       "H_FIRST": FIRST20, "H_LAST": HLAST20,
                       "H_8": FIRST8, "H_12": FIRST12, "H_SLOT": HS}.get(spec[3], "")
            try:
                text, secs, dur = run(path, size, beam, use_prompt, hot)
            except Exception as exc:            # noqa: BLE001
                row["out"][v] = {"text": "", "secs": 0.0, "dur": 0.0,
                                 "err": str(exc)[:120]}
                continue
            row["out"][v] = {"text": text, "secs": round(secs, 2),
                             "dur": round(dur, 2),
                             "bad": looks_bad(text, dur)}
        rows.append(row)
        print("[%2d/%2d] %s" % (n, len(files), base))
        for v in names:
            d = row["out"].get(v) or {}
            flag = "BAD" if d.get("bad") else "   "
            if d.get("err"):
                flag = "ERR"
            print("      %-7s %s %5.2fs  %s" % (v, flag, d.get("secs", 0),
                                             (d.get("text") or d.get("err") or "")[:70]))
        with io.open(OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)

    write_report(rows, names)
    print("saved %s" % os.path.basename(OUT_TXT))
    return 0


def write_report(rows, names):
    ref = "med" if "med" in names else names[0]
    lines = []
    lines.append("STT EVAL — %d files, reference=%s (pseudo-ground-truth)"
                 % (len(rows), ref))
    lines.append("")
    head = "%-10s" % "variant" + "".join("%8s" % h for h in
                                        ("WER", "bad", "empty", "s/file", "same"))
    lines.append(head)
    lines.append("-" * len(head))
    for v in names:
        wers, bad, empty, secs, same = [], 0, 0, [], 0
        for row in rows:
            d = row["out"].get(v) or {}
            t = d.get("text") or ""
            if d.get("err"):
                continue
            if not norm_words(t):
                empty += 1
            if d.get("bad"):
                bad += 1
            secs.append(d.get("secs") or 0)
            other = row["out"].get(ref) or {}
            ot = other.get("text") or ""
            if ot and t:
                w = wer(ot, t)
                if w is not None:
                    wers.append(w)
                    if w == 0:
                        same += 1
        n = max(1, len(secs))
        lines.append("%-10s%8.3f%8d%8d%8.2f%8d" % (v,
                     (sum(wers) / len(wers)) if wers else -1,
                     bad, empty, sum(secs) / n, same))
    lines.append("")
    lines.append("WER считается ПРОТИВ варианта %s (не против человека)." % ref)
    lines.append("Записи, где варианты расходятся, — ниже; их слушает ученик.")
    lines.append("")
    lines.append("РАСХОЖДЕНИЯ:")
    for row in rows:
        texts = {}
        for v in names:
            d = row["out"].get(v) or {}
            if not d.get("err"):
                texts[v] = d.get("text") or ""
        uniq = set(tuple(norm_words(t)) for t in texts.values())
        if len(uniq) > 1:
            lines.append("  %s" % row["file"])
            for v in names:
                if v in texts:
                    lines.append("    %-7s %s" % (v, texts[v][:90]))
    lines.append("")
    lines.append("PODLEZHASCHEE in took-the-black (live lesson city/4.3: student said")
    lines.append("  Ann took a black phone, every model heard and/n):")
    for row in rows:
        hit = False
        for v in names:
            d = row["out"].get(v) or {}
            t = " ".join(norm_words(d.get("text") or ""))
            if "took the black" in t or "took the back" in t:
                if not hit:
                    lines.append("  %s" % row["file"])
                    hit = True
                lines.append("    %-7s %s" % (v, t[:70]))
    lines.append("")
    lines.append("ВНИМАНИЕ К МЕТРИКЕ: эталон med САМ теряет имя Ann («n took»),")
    lines.append("поэтому вариант, который имя ВЕРНУЛ, получает штраф по WER.")
    lines.append("Смотреть надо на таблицу ниже, а не только на WER.")
    with io.open(OUT_TXT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
