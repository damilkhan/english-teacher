# -*- coding: utf-8 -*-
"""Zamer: umeet li model otsenit SMYSL repliki bez spiska etalonov (§77).

Beryom nastoyashchij MEANING_PROMPT i _meaning_verdict iz ui/app.py
(cherez ast, bez importa Tk), zovem model tak zhe, kak prilozhenie:
max_tokens=6, temperature=0.0.

Zapusk: python tools/eval_meaning.py [port] [runs]
Rezultat: logs/_eval_meaning.json i logs/_eval_meaning.md
Tolko ASCII v print() (cp1251 v konsoli), dannye - v fajly.
"""
import sys, os, json, ast, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

import config
import llm_client
import lesson as L

APP = os.path.join(BASE, "ui", "app.py")


def load_from_app():
    """Dostayom iz ui/app.py: MEANING_PROMPT i funkciyu _meaning_verdict."""
    src = open(APP, encoding="utf-8").read()
    tree = ast.parse(src)
    prompt = None
    func_src = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "MEANING_PROMPT":
                    prompt = ast.literal_eval(node.value)
        if isinstance(node, ast.FunctionDef) and node.name == "_meaning_verdict":
            func_src = ast.get_source_segment(src, node)
    if not prompt or not func_src:
        raise SystemExit("MEANING_PROMPT / _meaning_verdict not found in %s" % APP)
    ns = {}
    exec(func_src, ns)
    return prompt, ns["_meaning_verdict"]


# --- 40 par. A = odin smysl (model obyazana skazat SAME)
# ---         B = smysl izmenen (model obyazana skazat DIFFERENT)
SAME = [
    ("How much is it?", "How much does it cost?"),
    ("I have a headache.", "I've got a headache."),
    ("Can I pay by card?", "Is it possible to pay by card?"),
    ("I'd like a coffee, please.", "Can I have a coffee, please?"),
    ("I'm looking for a jacket.", "I need a jacket."),
    ("It's too expensive.", "That's too much money for me."),
    ("Where is the nearest pharmacy?", "Is there a pharmacy near here?"),
    ("Can you help me?", "Could you help me, please?"),
    ("I don't understand.", "I don't get it."),
    ("How do I get to the station?", "What is the way to the station?"),
    ("Do you have this in a bigger size?", "Have you got a bigger size of this?"),
    ("I'll take it.", "I'll buy it."),
    ("My phone is broken.", "My phone doesn't work."),
    ("I have never tried sushi.", "I've never eaten sushi."),
    ("You must show your passport.", "You have to show your passport."),
    ("He is taller than me.", "He is taller than I am."),
    ("I bought new shoes yesterday.", "Yesterday I bought new shoes."),
    ("There's no discount.", "There is not any discount."),
    ("Can I have the check, please?", "Could I have the bill, please?"),
    ("I'm from Astrakhan.", "I come from Astrakhan."),
]

DIFF = [
    ("I have a headache.", "I have a stomachache."),
    ("I'd like a coffee, please.", "I'd like some tea, please."),
    ("Can I pay by card?", "Can I pay in cash?"),
    ("It's too expensive.", "It's very cheap."),
    ("Do you have this in a bigger size?", "Do you have this in a smaller size?"),
    ("I'll take it.", "I won't take it."),
    ("My phone is broken.", "My phone is new."),
    ("I was walking when I saw him.", "He was walking when I saw him."),
    ("You must show your passport.", "You must not show your passport."),
    ("He is taller than me.", "I am taller than him."),
    ("I bought new shoes yesterday.", "I bought new shoes last week."),
    ("Where is the nearest pharmacy?", "Where is the nearest bank?"),
    ("How much is it?", "How many are there?"),
    ("Can you help me?", "Can I help you?"),
    ("I don't understand.", "I understand."),
    ("I'm looking for a jacket.", "I'm looking for a job."),
    ("See you tomorrow.", "I saw you yesterday."),
    ("There's no discount.", "There is a discount."),
    ("How do I get to the station?", "How do I get to the airport?"),
    ("I have never tried sushi.", "I have often tried sushi."),
]

# --- trudnye pary (gruppy C/D): perefrazy so smenoj struktury, sinonimy,
# --- i lovushki s bolshim perekrytiem slov. Gruppa G - spor nye, NE sudim.
HARD_SAME = [
    ("Can I pay by card?", "Do you take cards?"),
    ("I have no money.", "I'm broke."),
    ("It's too expensive.", "That's a rip-off."),
    ("Where is the bathroom?", "Where's the restroom?"),
    ("I don't have any cash.", "I have no cash on me."),
    ("Can you say that again?", "Sorry, could you repeat that?"),
    ("How much does it cost?", "What's the price?"),
    ("I'd like to book a table for two.", "A table for two, please."),
    ("My head hurts.", "I have a headache."),
    ("He is not here.", "He isn't here."),
    ("I live in Astrakhan.", "Astrakhan is my hometown."),
    ("This one is cheaper than that one.", "That one costs more than this one."),
]

HARD_DIFF = [
    ("Can I pay by card?", "Can I pay by phone?"),
    ("I'd like a table for two.", "I'd like a table for four."),
    ("I have been to London.", "I have never been to London."),
    ("She can swim.", "She can't swim."),
    ("Turn left at the corner.", "Turn right at the corner."),
    ("I need a doctor.", "I need a dentist."),
    ("The shop opens at nine.", "The shop closes at nine."),
    ("Is it far from here?", "Is it near here?"),
    ("I'm looking for a pharmacy.", "I found a pharmacy."),
    ("I want to buy it.", "I don't want to buy it."),
    ("The coffee is hot.", "The coffee is cold."),
    ("He works in a bank.", "He worked in a bank."),
]

GREY = [
    ("How much is it?", "How much are they?"),
    ("I want to buy it.", "I wanted to buy it."),
    ("I have seen it.", "I saw it."),
    ("I don't like it.", "I don't really like it."),
]

# --- gruppy E/F: LOMANAYA rech uchenika (kak on realno govorit).
# --- E - smysl vernyj (model dolzhna skazat SAME), F - smysl izmenen.
BROKEN_SAME = [
    ("How much is it?", "How much cost?"),
    ("I have a headache.", "I have headache."),
    ("Can I pay by card?", "Pay card?"),
    ("I'd like a coffee, please.", "I like coffee please."),
    ("It's too expensive.", "It too expensive."),
    ("Where is the pharmacy?", "Where pharmacy?"),
    ("I'm from Astrakhan.", "I from Astrakhan."),
    ("My phone is broken.", "My phone is not work."),
    ("I bought new shoes yesterday.", "I buy new shoes yesterday."),
    ("He is taller than me.", "He more tall than me."),
    ("I was walking when I saw him.", "I walking when I see him."),
    ("There's no discount.", "No discount."),
]

BROKEN_DIFF = [
    ("I have a headache.", "I have stomachache."),
    ("I'll take it.", "I not take it."),
    ("Where is the pharmacy?", "Where is bank?"),
    ("I'd like some tea, please.", "I like coffee please."),
    ("Can I pay by card?", "I pay cash."),
    ("The shop opens at nine.", "Shop close nine."),
];

# Staryj prompt (do §77 on stojal v ui/app.py). Ostavlen dlya sravneniya:
# variant "v1" meriт ego, "app" - to, chto sejchas v prilozhenii.
PROMPT_V1 = (
    "You compare two English sentences said by an A2 learner of American"
    " English. Answer with ONE word: SAME if the student's sentence means the"
    " same as the target, or DIFFERENT if it means something else."
    " Different words, contractions, word order and polite fillers are fine."
    " Ignore small grammar slips. Parts of speech and key words must match."
    " Answer only SAME or DIFFERENT, nothing else.")

PROMPT_V2 = (
    "You compare two English sentences said by an A2 learner of American"
    " English. Answer with ONE word: SAME if the student's sentence means the"
    " same as the target, or DIFFERENT if it means something else.\n"
    "The student speaks with grammar mistakes: a missing am/is/are/do/did, a"
    " missing article, a wrong verb form or tense, a wrong word order, extra or"
    " missing words. These are NOT meaning differences. Answer SAME when the"
    " intended meaning is the same, even if the sentence is grammatically wrong.\n"
    "Answer DIFFERENT only when the meaning really changes: another thing,"
    " another person, another place, another time, the opposite, negation added"
    " or lost, or a different question.\n"
    "Answer only SAME or DIFFERENT, nothing else.")

PROMPT_V3 = (
    "You compare two English sentences said by an A2 learner of American"
    " English. The target is the correct textbook sentence. The student speaks"
    " aloud and makes mistakes.\n"
    "Step 1: guess what the student MEANT, ignoring grammar, missing small"
    " words, wrong tense or word order.\n"
    "Step 2: answer SAME if that meaning matches the target, DIFFERENT if it"
    " does not.\n"
    "A grammar mistake alone is never DIFFERENT. Only a different thing, person,"
    " place, time, opposite meaning or a different question is DIFFERENT.\n"
    "Answer only SAME or DIFFERENT, nothing else.")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    prompt, verdict_of = load_from_app()
    variant = sys.argv[3] if len(sys.argv) > 3 else "app"
    if variant == "v1":
        prompt = PROMPT_V1
    elif variant == "v2":
        prompt = PROMPT_V2
    elif variant == "v3":
        prompt = PROMPT_V3
    url = "http://127.0.0.1:%d/v1/chat/completions" % port
    llm = llm_client.LLMClient(url=url, max_tokens=6, temperature=0.0, stop=[])
    cases = ([("A", a, b) for a, b in SAME] + [("B", a, b) for a, b in DIFF]
             + [("C", a, b) for a, b in HARD_SAME]
             + [("D", a, b) for a, b in HARD_DIFF]
             + [("G", a, b) for a, b in GREY]
             + [("E", a, b) for a, b in BROKEN_SAME]
             + [("F", a, b) for a, b in BROKEN_DIFF])
    print("port=%d runs=%d cases=%d prompt=%s" % (port, runs, len(cases), variant), flush=True)
    # §77: proverka svyazi. Bez neyo upavshij server daval 0 % i vyglyadelo
    # kak "prompt ne rabotaet" (sluchilos 12.11.2026: prilozhenie zakryli,
    # llama-server ostanovilsya, zamer sdelal 246 oshibok podryad).
    ok0, raw0 = llm.complete([{"role": "user", "content": "ping"}],
                             max_tokens=2, temperature=0.0, timeout=20)
    if not ok0:
        raise SystemExit("SERVER NOT READY on port %d: %s" % (port, str(raw0)[:120]))

    rows = []
    for i, (kind, target, student) in enumerate(cases, 1):
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user",
             "content": 'Target: "%s"\nStudent: "%s"' % (target, student)},
        ]
        verdicts, raws, secs = [], [], []
        for _ in range(runs):
            t0 = time.monotonic()
            try:
                ok, raw = llm.complete(messages, max_tokens=6,
                                       temperature=0.0, timeout=20)
            except Exception as exc:
                ok, raw = False, "ERR %s" % exc
            secs.append(time.monotonic() - t0)
            raws.append(str(raw))
            verdicts.append(verdict_of(raw) if ok else None)
        known = [v for v in verdicts if v is not None]
        majority = max(set(known), key=known.count) if known else None
        want = True if kind in ("A", "C", "E") else (None if kind == "G" else False)
        code_ok = L.same_meaning(student, target)
        rows.append({
            "n": i, "kind": kind, "target": target, "student": student,
            "raw": raws, "verdicts": [None if v is None else v for v in verdicts],
            "majority": majority,
            "ok_majority": (None if want is None else majority == want),
            "ok_all": (None if want is None else all(v == want for v in verdicts)),
            "unknown": sum(1 for v in verdicts if v is None),
            "code_same": code_ok,
            "sec": round(sum(secs) / len(secs), 2),
        })
        if i % 5 == 0:
            print("  ... %d/%d" % (i, len(cases)), flush=True)

    save(rows, port, runs, variant)


def save(rows, port, runs, variant="v1"):
    scored = [r for r in rows if r["kind"] != "G"]
    n = len(scored)
    ok = sum(1 for r in scored if r["ok_majority"])
    ok_all = sum(1 for r in scored if r["ok_all"])
    unk = sum(r["unknown"] for r in scored)
    secs = sum(r["sec"] for r in scored) / n
    a = [r for r in scored if r["kind"] in ("A", "C", "E")]   # odin smysl
    b = [r for r in scored if r["kind"] in ("B", "D", "F")]   # smysl izmenen
    greys = [r for r in rows if r["kind"] == "G"]
    a_ok = sum(1 for r in a if r["ok_majority"])
    b_ok = sum(1 for r in b if r["ok_majority"])
    hard_a = [r for r in scored if r["kind"] == "C"]
    hard_b = [r for r in scored if r["kind"] == "D"]
    wrong_a = [r for r in a if not r["ok_majority"]]   # skazala DIFFERENT
    wrong_b = [r for r in b if not r["ok_majority"]]   # skazala SAME (opasno!)
    out = {"port": port, "runs": runs, "prompt": variant, "n": n,
           "accuracy_majority": round(100.0 * ok / n, 1),
           "accuracy_all_runs": round(100.0 * ok_all / n, 1),
           "same_cases_ok": "%d/%d" % (a_ok, len(a)),
           "hard_same_ok": "%d/%d" % (sum(1 for r in hard_a if r["ok_majority"]), len(hard_a)),
           "broken_same_ok": "%d/%d" % (
               sum(1 for r in scored if r["kind"] == "E" and r["ok_majority"]),
               sum(1 for r in scored if r["kind"] == "E")),
           "broken_diff_ok": "%d/%d" % (
               sum(1 for r in scored if r["kind"] == "F" and r["ok_majority"]),
               sum(1 for r in scored if r["kind"] == "F")),
           "hard_diff_ok": "%d/%d" % (sum(1 for r in hard_b if r["ok_majority"]), len(hard_b)),
           "diff_cases_ok": "%d/%d" % (b_ok, len(b)),
           "false_different": len(wrong_a), "false_same": len(wrong_b),
           "unknown_answers": unk, "avg_sec": round(secs, 2), "rows": rows}
    with open(os.path.join(BASE, "logs", "_eval_meaning.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    lines = ["# Zamer smysla: %d par, %d progonov, port %d, prompt %s" % (n, runs, port, variant), "",
             "| pokazatel | znachenie |", "|---|---|",
             "| tochnost (golosovanie) | **%.1f %%** |" % out["accuracy_majority"],
             "| tochnost (vse progons sovpali) | %.1f %% |" % out["accuracy_all_runs"],
             "| vernye perefrazy (SAME) | %s |" % out["same_cases_ok"],
             "| trudnye: perefrazy (C) | %s |" % out["hard_same_ok"],
             "| trudnye: izmenen smysl (D) | %s |" % out["hard_diff_ok"],
             "| LOMANAYA rech, smysl vernyj (E) | %s |" % out["broken_same_ok"],
             "| lomanaya rech, smysl izmenen (F) | %s |" % out["broken_diff_ok"],
             "| izmenennyj smysl (DIFFERENT) | %s |" % out["diff_cases_ok"],
             "| LOZHNOE DIFFERENT (obidno) | %d |" % out["false_different"],
             "| LOZHNOE SAME (opasno) | %d |" % out["false_same"],
             "| neponyatnyh otvetov | %d |" % out["unknown_answers"],
             "| spor nye, ne sudyu (G) | %s |" % ", ".join(
                 "%s->%s" % (g["student"][:18],
                             "S" if g["majority"] else ("D" if g["majority"] is False else "?"))
                 for g in greys),
             "| srednee vremya | %.2f s |" % out["avg_sec"], "",
             "| # | tip | target | uchenik | otvet | golosov | kod | ok |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        vs = ",".join("?" if v is None else ("S" if v else "D") for v in r["verdicts"])
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %s |" % (
            r["n"], r["kind"], r["target"].replace("|", "/"),
            r["student"].replace("|", "/"),
            r["raw"][0].strip().replace("|", "/")[:20], vs,
            "same" if r["code_same"] else "-",
            "OK" if r["ok_majority"] else "XX"))
    with open(os.path.join(BASE, "logs", "_eval_meaning.md"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    print("DONE n=%d acc=%.1f%% all_runs=%.1f%% falseSAME=%d falseDIFF=%d avg=%.2fs" % (
        n, out["accuracy_majority"], out["accuracy_all_runs"],
        out["false_same"], out["false_different"], out["avg_sec"]), flush=True)


if __name__ == "__main__":
    main()
