# -*- coding: utf-8 -*-
"""build_universe.py — собрать ЕДИНОЕ описание мира из старых данных.

Зачем: сейчас мир рассыпан по 30 слотам с разной формой, и часть смысла
подменена готовыми фразами ("i'm ready" -> "Great. Let's start."). Из такого
датасет не собрать. Здесь мир сводится к ОДНОЙ форме:

  persona  - кто говорит, что знает, чего НЕ знает, как ведёт себя вне мира
  entities - предметы мира (с переводом, ценой, множественным числом)
  intents  - смыслы, специфичные для сцены (смысл по-русски + шаблон ответа)
  turns    - ходы диалога (вопрос + что ожидается в ответ)

Из него потом генерируется и текущий движок, и датасет. Модуль чистый.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REACT = ROOT / "data" / "reactions_a2.json"
SCENES = ROOT / "data" / "scenes_a2.json"
OUT = ROOT / "data" / "train" / "universe_a2.json"

# Смыслы, общие для всех сцен (не зависят от места диалога).
UNIVERSAL = ["item", "number", "yes", "no", "thanks", "bill", "toilet",
             "recommend", "have", "price", "complaint", "dontknow", "repeat", "other"]

# Служебные поля слота, которые НЕ являются смыслами.
SKIP_WORDS = {"fallback"}

def slug(s):
    s = re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")
    return s or "x"

def guarded():
    """Не затирать вселенную, в которую уже правят руками."""
    if OUT.exists() and "--force" not in sys.argv:
        try:
            doc = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            doc = {}
        if int(doc.get("version") or 1) >= 2:
            print("STOP: %s already version %s (hand-edited)." % (OUT.name, doc.get("version")))
            print("Use --force only if you really want to rebuild it from old files.")
            return None
    return build()


def build():
    lib = json.load(open(REACT, encoding="utf-8"))
    sc = json.load(open(SCENES, encoding="utf-8"))
    slots = lib.get("slots") or {}
    words = lib.get("words") or {}

    # какие слоты упоминаются в сценах (карта slot -> сцена)
    slot_scene = {}
    for scene in sc.get("scenes") or []:
        for step in scene.get("steps") or []:
            for q in step.get("questions") or []:
                s = q.get("slot")
                if s:
                    slot_scene.setdefault(s, scene.get("id"))

    # Русские названия предметов — из чипов конструктора (ru/en рядом).
    RU_ITEM = {}
    for sname, conf in slots.items():
        for grp in (conf.get("chips") or {}).values():
            for row in grp or []:
                ru = str((row or {}).get("ru") or "").strip()
                en = str((row or {}).get("en") or "").strip().lower()
                if ru and en:
                    RU_ITEM.setdefault(en, ru)
                    if not re.search(r"[A-Za-z]", ru):
                        RU_ITEM.setdefault(en.split()[0], ru)

    # Смыслы КАЖДОГО слота отдельно (иначе ходы получали чужие).
    SLOT_INTENTS = {}
    worlds = {}
    for scene in sc.get("scenes") or []:
        sid = scene.get("id")
        w = {
            "title": scene.get("title"),
            "title_ru": scene.get("title_ru"),
            "lesson": scene.get("lesson"),
            "point": scene.get("point"),
            "persona": {
                "ru": (scene.get("card") or {}).get("ru", ""),
                "en": (scene.get("card") or {}).get("en", ""),
                "knows": [],          # заполняется ниже по entity
                "ignorant": [],
                "off_world": "I'm not sure about that. Let me check.",
                "max_words": 12,
            },
            "card": scene.get("card") or {},
            "steps": [],
            "entities": {},
            "intents": {},
            "turns": [],
        }
        worlds[sid] = w

    # entities + intents из слотов
    for sname, conf in slots.items():
        sid = slot_scene.get(sname)
        if sid not in worlds:
            continue
        w = worlds[sid]
        items = conf.get("items") or {}
        ent = {"ru": "", "kind": "item", "items": {}}
        if conf.get("numbers"):
            ent["kind"] = "number"
        if sname in ("shop_size", "shop_pay", "payment"):
            ent["kind"] = "choice"
        plurals = conf.get("plurals") or {}
        for key, val in (items or {}).items():
            ent["items"][str(key)] = {"en": str(val),
                                      "plural": str(plurals.get(key, "")),
                                      "ru": RU_ITEM.get(str(val).lower(), "")}
        if ent["items"] or ent["kind"] != "item":
            w["entities"][sname] = ent
            w["persona"]["knows"].append(sname)

        # слова слота -> смыслы ЭТОГО слота (смысл по-русски + шаблон)
        own = conf.get("words") or {}
        mine = []
        for key, reply in own.items():
            code = slug(key)
            if code in w["intents"]:
                mine.append(code)
                continue
            w["intents"][code] = {"said": str(key), "reply": str(reply),
                                  "slot": sname}
            mine.append(code)
        SLOT_INTENTS[sname] = mine

    # turns из вопросов сцен
    for scene in sc.get("scenes") or []:
        sid = scene.get("id")
        w = worlds.get(sid)
        if not w:
            continue
        n = 0
        for step in scene.get("steps") or []:
            for q in step.get("questions") or []:
                n += 1
                s = str(q.get("slot") or "")
                turn = {"id": "t%d" % n, "step": step.get("n"), "slot": s,
                        "ask": str(q.get("en") or ""), "ru": str(q.get("hint") or "")}
                if s in w["entities"]:
                    turn["entity"] = s
                else:
                    turn["entity"] = ""
                    turn["intents"] = SLOT_INTENTS.get(s, [])
                w["turns"].append(turn)
        w["steps"] = [{"n": st.get("n"), "title": st.get("title") or ""}
                      for st in (scene.get("steps") or [])]

    # --- Полный перенос: без этого из вселенной не собрать reactions обратно ---
    KEEP = ("ask", "numbers", "echo_one", "echo", "yes", "no", "fallback", "chips",
            "words", "have", "recommend", "price", "dontknow", "thanks", "bill",
            "complaint", "items", "plurals")
    for sname, conf in slots.items():
        sid = slot_scene.get(sname)
        if sid not in worlds:
            continue
        bits = {k: conf[k] for k in KEEP if k in conf}
        if bits:
            worlds[sid].setdefault("slots", {})[sname] = bits
    library = {"note": lib.get("note", ""), "words": words,
               "numbers": lib.get("numbers") or [],
               "universal": lib.get("universal") or {}}

    doc = {"version": 2, "level": lib.get("level") or "a2",
           "intents_universal": UNIVERSAL, "library": library, "worlds": worlds}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(doc, open(OUT, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    return doc

if __name__ == "__main__":
    d = guarded()
    if d is None:
        sys.exit(1)
    for sid, w in d["worlds"].items():
        it = sum(len(e.get("items") or {}) for e in w["entities"].values())
        print("%-16s turns=%2d entities=%2d items=%3d intents=%d"
              % (sid, len(w["turns"]), len(w["entities"]), it, len(w["intents"])))
    print("OK", OUT)
