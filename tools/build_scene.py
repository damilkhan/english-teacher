# -*- coding: utf-8 -*-
"""build_scene.py - собрать рабочие файлы приложения ИЗ вселенной (одно место правды).

  universe_a2.json  ->  reactions_a2.json  (+ scenes_a2.json, если хватает данных)

Режим по умолчанию: пишет в logs/_reactions_generated.json и СРАВНИВАЕТ с
data/reactions_a2.json (замок: ничего не потеряно). Ключ --write перезаписывает
рабочий файл. Печать только ASCII: отчет пишется в logs/_scene_build.txt.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNI = ROOT / "data" / "train" / "universe_a2.json"
REACT = ROOT / "data" / "reactions_a2.json"
SCENES = ROOT / "data" / "scenes_a2.json"
GEN = ROOT / "logs" / "_reactions_generated.json"
REPORT = ROOT / "logs" / "_scene_build.txt"

ORDER = ("ask", "items", "echo_one", "echo", "yes", "no", "thanks", "have",
         "recommend", "price", "bill", "complaint", "dontknow", "fallback",
         "plurals", "numbers", "words", "chips")
EMPTY = (None, "", {}, [])


def build_reactions(doc):
    slots = {}
    order = []
    for sid, w in (doc.get("worlds") or {}).items():
        for name, bits in (w.get("slots") or {}).items():
            s = {}
            for k in ORDER:
                if k in bits and bits[k] not in EMPTY:
                    s[k] = bits[k]
            for k, v in bits.items():          # ничего не теряем: незнакомые поля тоже
                if k not in s and v not in EMPTY:
                    s[k] = v
            slots[name] = s
            order.append(name)
    lib = doc.get("library") or {}
    return {"level": doc.get("level") or "a2",
            "note": lib.get("note", ""),
            "words": lib.get("words") or {},
            "numbers": lib.get("numbers") or {},
            "universal": lib.get("universal") or {},
            "slots": slots}


def build_scenes(doc):
    """Вселенная -> scenes_a2.json (шаги, вопросы со slot, карточка роли)."""
    scenes = []
    for sid, w in (doc.get("worlds") or {}).items():
        card = dict(w.get("card") or {})
        title = {"n": None, "title": ""}
        steps = []
        by_n = {}
        for st in w.get("steps") or []:
            if st.get("n") is None:
                continue
            by_n[st["n"]] = {"n": st["n"], "title": st.get("title") or "", "questions": []}
            steps.append(by_n[st["n"]])
        for turn in w.get("turns") or []:
            st = by_n.get(turn.get("step"))
            if st is None:
                continue
            q = {"en": turn.get("ask") or "", "hint": turn.get("ru") or ""}
            if turn.get("slot"):
                q["slot"] = turn["slot"]
            st["questions"].append(q)
        scenes.append({"id": sid,
                       "title": w.get("title") or "",
                       "title_ru": w.get("title_ru") or "",
                       "lesson": w.get("lesson") or "",
                       "point": w.get("point") or "",
                       "card": card,
                       "steps": steps})
    return {"version": 1, "level": "A2", "scenes": scenes}   # как в рабочем файле


def diff_scenes(old, new):
    out = []
    for k in ("version", "level"):
        if old.get(k) != new.get(k):
            out.append("TOP %s differs" % k)
    oi = {s["id"]: s for s in old.get("scenes") or []}
    ni = {s["id"]: s for s in new.get("scenes") or []}
    for sid in sorted(set(oi) | set(ni)):
        if sid not in ni:
            out.append("MISSING scene %s" % sid)
            continue
        if sid not in oi:
            out.append("EXTRA scene %s" % sid)
            continue
        a, b = oi[sid], ni[sid]
        for k in ("title", "title_ru", "lesson", "point", "card"):
            if a.get(k) != b.get(k):
                out.append("scene %s field %s: old=%r new=%r" % (sid, k, a.get(k), b.get(k)))
        if len(a.get("steps") or []) != len(b.get("steps") or []):
            out.append("scene %s steps old=%d new=%d" % (sid, len(a.get("steps") or []),
                                                         len(b.get("steps") or [])))
        for sa, sb in zip(a.get("steps") or [], b.get("steps") or []):
            if sa != sb:
                out.append("scene %s step %s differs" % (sid, sa.get("n")))
    return out


def diff(old, new):
    """Список расхождений: по слотам и по общим разделам."""
    out = []
    for k in ("level", "note", "words", "numbers", "universal"):
        if old.get(k) != new.get(k):
            out.append("TOP %s differs" % k)
    os_, ns = old.get("slots") or {}, new.get("slots") or {}
    for name in sorted(set(os_) | set(ns)):
        if name not in ns:
            out.append("MISSING slot %s" % name)
            continue
        if name not in os_:
            out.append("EXTRA slot %s" % name)
            continue
        a, b = os_[name], ns[name]
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                out.append("slot %s field %s: old=%r new=%r" % (name, k, a.get(k), b.get(k)))
    return out


def main(argv):
    doc = json.load(open(UNI, encoding="utf-8"))
    gen = build_reactions(doc)
    old = json.load(open(REACT, encoding="utf-8"))
    diffs = diff(old, gen)
    gen_sc = build_scenes(doc)
    old_sc = json.load(open(SCENES, encoding="utf-8"))
    diffs_sc = diff_scenes(old_sc, gen_sc)
    lines = ["universe version=%s worlds=%d" % (doc.get("version"), len(doc.get("worlds") or {})),
             "slots old=%d new=%d" % (len(old.get("slots") or {}), len(gen["slots"])),
             "words=%d numbers=%d universal=%d" % (len(gen["words"]), len(gen["numbers"]),
                                                   len(gen["universal"])),
             "diff count=%d" % len(diffs),
             "scenes old=%d new=%d" % (len(old_sc.get("scenes") or []), len(gen_sc["scenes"])),
             "SCENE DIFF count=%d" % len(diffs_sc)]
    lines += diffs[:60]
    lines += diffs_sc[:60]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "logs" / "_scenes_generated.json").write_text(
        json.dumps(gen_sc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    GEN.write_text(json.dumps(gen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("reactions diff=%d, scenes diff=%d -> %s" % (len(diffs), len(diffs_sc), REPORT.name))
    if "--write" in argv:
        if diffs_sc:
            print("REFUSED: scenes differ, fix data first (see %s)" % REPORT.name)
            return 2
        for path, obj in ((REACT, gen), (SCENES, gen_sc)):
            path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
        print("written: %s, %s" % (REACT.name, SCENES.name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
