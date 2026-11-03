# -*- coding: utf-8 -*-
"""build_dataset.py - датасет для дообучения ИЗ ОПИСАНИЯ МИРА.

Источник правды - data/train/universe_a2.json. Руками ничего не сочиняем:
все примеры собираются кодом из персонажа, предметов и ходов диалога.

Три задачи (по одной строке JSONL = один пример chat-format):
  classify.jsonl  - что сказал ученик  -> {"intent","item","count"}
  react.jsonl     - как ответить       -> одна короткая фраза
  roleplay.jsonl  - держать роль       -> многоходовой диалог

Плюс heldout.jsonl - 200 фраз, отложенных от обучения (мерить честно).
"""
import json, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNI = ROOT / "data" / "train" / "universe_a2.json"
OUTDIR = ROOT / "data" / "train"

random.seed(20261103)   # повторяемость: один и тот же датасет при каждом запуске

# Как ученик A2 реально говорит (в т.ч. как это слышит Whisper).
TPL_ONE = [
    "I'd like {a} {item}", "Can I have {a} {item}", "{Item} please",
    "Just {item}", "I'll have {item}", "Gimme {a} {item}",
    "{item} for me", "I want {a} {item}", "{item}",
]
TPL_MANY = [
    "{Num} {plural}", "I'd like {num} {plural}", "{num} {plural} please",
    "Can I get {num} {plural}", "Gimme {num} {plural}", "{num} more {plural}",
]
TPL_YES = ["yes", "yes please", "sure", "yes that's fine", "ok", "of course"]
TPL_NO = ["no", "no thanks", "no thank you", "nothing thanks", "i'm fine thanks"]
TPL_THANKS = ["thanks", "thank you", "thanks a lot", "thank you very much"]
NOISE = [
    ("{num} {plural}", "{num} {plural}"),   # цифрами
    ("{num} {plural}", "{num} to {plural}"),  # 'to' вместо 'two' - ошибка STT
    ("I'd like", "id like"), ("I would like", "i would like"),
    ("Can I have", "can i have"), ("gimme", "give me"),
]
ART = lambda w: ("an " if w[:1].lower() in "aeiou" else "a ") + w
NUMW = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}

# Held-out: ДРУГИЕ формулировки, которых нет в обучении (честный замер).
TPL_HELD = [
    "could i get {a} {item}", "i feel like {item}", "one {item} for me please",
    "let's go with {item}", "i'm going to have {item}", "{item} would be great",
    "bring me {a} {item}", "do you have {item}",
]

UNKNOWN_WORDS = ["wifi", "the weather", "my name is damir", "where is the bank",
                 "do you sell phones", "how old are you", "is there a pool",
                 "can i pay later", "do you have a discount", "call a taxi"]

def _a(item):
    return ART(item) if item.split()[0].lower() not in ("some",) else item

def variations(items, kind, limit=None):
    """Живые варианты фразы для предмета + искажения STT."""
    out = []
    for key, meta in items.items():
        en = meta.get("en") or key
        plural = meta.get("plural") or (en + "s")
        if kind == "number":
            continue
        out.append(TPL_ONE[0].format(a=_a(en), item=en, Item=en.capitalize()))
        for t in TPL_ONE[1:]:
            out.append(t.format(a=_a(en), item=en, Item=en.capitalize()))
        for n in (2, 3):
            for t in TPL_MANY:
                out.append(t.format(num=NUMW[n], plural=plural, Num=NUMW[n].capitalize()))
    # искажения под STT
    noisy = []
    for s in out:
        noisy.append(s.lower())
        noisy.append(re.sub(r"\b(an|a|the)\b", "", s.lower()).replace("  ", " ").strip())
        noisy.append(s.lower().replace("i would like", "id like"))
        noisy.append(s.lower().replace("'d like", "d like"))
    seen, uniq = set(), []
    for s in out + noisy:
        s = re.sub(r"\s+", " ", s).strip()
        if s and s not in seen:
            seen.add(s); uniq.append(s)
    if limit:
        uniq = uniq[:limit]
    return uniq

def asst(system, user, reply):
    return {"messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user},
                         {"role": "assistant", "content": reply}]}

def main():
    doc = json.load(open(UNI, encoding="utf-8"))
    universal = doc.get("intents_universal") or []
    classify, react, roleplay, heldout = [], [], [], []
    OUTDIR.mkdir(parents=True, exist_ok=True)

    for sid, w in doc["worlds"].items():
        persona = w["persona"]
        world_sys = ("%s\nRules: %d words max, natural spoken American English. "
                     "You do NOT know: %s. If asked about something outside your world, "
                     "say: \"%s\" and stay in character."
                     % (persona["en"], persona.get("max_words", 12),
                        ", ".join(persona.get("ignorant") or ["anything off-topic"]),
                        persona.get("off_world", "I'm not sure about that.")))
        ents = w["entities"]
        names = list(ents.keys())

        for turn in w["turns"]:
            ask = turn["ask"]
            ent = turn.get("entity") or ""
            # ---------- classify: предмет назван ----------
            if ent and ents[ent].get("items"):
                items = ents[ent]["items"]
                sys_c = ("You classify a spoken reply in an English roleplay (level A2).\n"
                         "Assistant asked: \"%s\" (entity: %s).\nKnown items: %s\n"
                         "Reply with JSON only: {\"intent\",\"item\",\"count\"}.\n"
                         "Allowed intent: %s. Unknown or off-topic -> intent=other, do NOT guess."
                         % (ask, ent, ", ".join(sorted({m.get("en") or k for k, m in items.items()})),
                            ", ".join(universal)))
                for said in variations(items, ents[ent].get("kind", "item")):
                    m = re.search(r"\b(two|three|2|3|one|1)\b", said.lower())
                    cnt = 0
                    if m:
                        cnt = {"two": 2, "2": 2, "three": 3, "3": 3, "one": 1, "1": 1}[m.group(1)]
                    hit = None
                    for key, meta in items.items():
                        en = (meta.get("en") or key).lower()
                        if re.search(r"\b%s\b" % re.escape(en.split()[0]), said.lower()):
                            hit = en
                    if not hit:
                        continue
                    ans = json.dumps({"intent": "item", "item": hit, "count": cnt},
                                     ensure_ascii=False)
                    classify.append(asst(sys_c, "Student said: \"%s\"" % said, ans))
                    # ---------- react ----------
                    if random.random() < 0.45:
                        if cnt > 1:
                            pl = items.get(hit, {}).get("plural") or hit + "s"
                            reply = "%s %s, coming up." % (NUMW.get(cnt, cnt).capitalize(), pl)
                        else:
                            reply = "%s, coming right up." % hit.capitalize()
                        react.append(asst(world_sys,
                                          "The guest answers \"%s\" with: \"%s\". React in one short sentence."
                                          % (ask, said), reply))
            # ---------- classify: да / нет / благодарность ----------
            uni_map = {"yes": TPL_YES, "no": TPL_NO, "thanks": TPL_THANKS}
            for code in (turn.get("intents") or []):
                meta = w["intents"].get(code) or {}
                said_src = meta.get("said") or code.replace("_", " ")
                for said in {said_src, said_src.lower(), said_src.replace("'", "")}:
                    sys_u = ("You classify a spoken reply in an English roleplay (level A2).\n"
                             "Assistant asked: \"%s\".\nReply with JSON only: {\"intent\",\"item\",\"count\"}.\n"
                             "Allowed intent: %s." % (ask, ", ".join(universal)))
                    classify.append(asst(sys_u, "Student said: \"%s\"" % said,
                                         json.dumps({"intent": "other", "item": said_src, "count": 0},
                                                    ensure_ascii=False)))
                    if meta.get("reply"):
                        react.append(asst(world_sys,
                                          "The guest answers \"%s\" with: \"%s\". React in one short sentence."
                                          % (ask, said), meta["reply"]))
            # ---------- универсальные: да / нет / не понял ----------
            # НЕ для вопросов-чисел: «How many people?» -> «yes» бессмысленно.
            kind_now = (ents.get(ent, {}) or {}).get("kind", "")
            univ_ok = kind_now not in ("number",)
            for code, tpls in (uni_map.items() if univ_ok else []):
                for said in tpls:
                    sys_u = ("You classify a spoken reply in an English roleplay (level A2).\n"
                             "Assistant asked: \"%s\".\nReply with JSON only: {\"intent\",\"item\",\"count\"}.\n"
                             "Allowed intent: %s." % (ask, ", ".join(universal)))
                    classify.append(asst(sys_u, "Student said: \"%s\"" % said,
                                         json.dumps({"intent": code, "item": "", "count": 0},
                                                    ensure_ascii=False)))
            # ---------- отрицательные: вне мира ----------
            for said in UNKNOWN_WORDS:
                sys_n = ("You classify a spoken reply in an English roleplay (level A2).\n"
                         "Assistant asked: \"%s\".\nReply with JSON only: {\"intent\",\"item\",\"count\"}.\n"
                         "Allowed intent: %s. NEVER guess an item that was not named." % (ask, ", ".join(universal)))
                classify.append(asst(sys_n, "Student said: \"%s\"" % said,
                                     json.dumps({"intent": "other", "item": "", "count": 0},
                                                ensure_ascii=False)))

        # ---------- roleplay: 3-4 хода подряд ----------
        turns = w["turns"]
        for _ in range(min(60, len(turns) * 3)):
            k = random.randint(3, min(5, len(turns)))
            start = random.randint(0, max(0, len(turns) - k))
            msgs = [{"role": "system", "content": world_sys}]
            for t in turns[start:start + k]:
                ent = t.get("entity") or ""
                if ent and ents.get(ent, {}).get("items"):
                    key = random.choice(list(ents[ent]["items"].keys()))
                    meta = ents[ent]["items"][key]
                    en = meta.get("en") or key
                    said = random.choice(TPL_ONE).format(a=_a(en), item=en, Item=en.capitalize())
                    reply = "%s, coming right up." % en.capitalize()
                else:
                    said = random.choice(TPL_YES + TPL_NO)
                    reply = w["persona"].get("off_world", "Okay.") if random.random() < .3 else "Of course."
                msgs.append({"role": "assistant", "content": t["ask"]})
                msgs.append({"role": "user", "content": said})
                msgs.append({"role": "assistant", "content": reply})
            msgs.append({"role": "assistant", "content": turns[min(start + k, len(turns) - 1)]["ask"]})
            roleplay.append({"messages": msgs})

    # ---------- heldout: 200 фраз, которых НЕТ в обучении ----------
    taken = {json.loads(l)["messages"][1]["content"] for l in
             (json.dumps(x, ensure_ascii=False) for x in classify)}
    pool = []
    for sid, w in doc["worlds"].items():
        for turn in w["turns"]:
            ent = turn.get("entity") or ""
            if ent and w["entities"].get(ent, {}).get("items"):
                for key, meta in w["entities"][ent]["items"].items():
                    en = meta.get("en") or key
                    pool.append((turn["ask"], en,
                                 random.choice(TPL_HELD).format(a=_a(en), item=en, Item=en.capitalize())))
    random.shuffle(pool)
    for ask, en, said in pool:
        line = "Student said: \"%s\"" % said
        if line in taken:
            continue
        heldout.append({"ask": ask, "item": en, "said": said})
        if len(heldout) >= 200:
            break

    def dedupe(rows):
        seen, out = set(), []
        for r in rows:
            k = json.dumps(r, ensure_ascii=False, sort_keys=True)
            if k in seen:
                continue
            seen.add(k); out.append(r)
        return out

    classify = dedupe(classify)
    react = dedupe(react)

    def dump(name, rows):
        p = OUTDIR / name
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return p

    print("classify", len(classify))
    print("react", len(react))
    print("roleplay", len(roleplay))
    print("heldout", len(heldout))
    dump("classify.jsonl", classify)
    dump("react.jsonl", react)
    dump("roleplay.jsonl", roleplay)
    dump("heldout.jsonl", heldout)

if __name__ == "__main__":
    main()
