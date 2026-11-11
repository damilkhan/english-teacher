# -*- coding: utf-8 -*-
"""Zamer modeli na odnih i teh zhe zhivyh replikah (shag 1, §72).

Zapuskaetsya: python tools/eval_chat.py <port> <tag>
Rezultat: logs/_eval_<tag>.json i logs/_eval_<tag>.md (tablica po tipam narushenij).
Tolko ASCII v print() (cp1251 v konsoli), dannye - v fajly.
"""
import sys, os, json, re, time, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

import config
import lesson as L
import prompt_builder as pb
import profile_store
import user_manager
import llm_client
import reply_checks as rc
from progress_map import ProgressMap

CASES = os.path.join(BASE, "logs", "_eval_cases.json")
STOP = ["<|thought|>", "<end_of_turn>"]
CYR = re.compile(u"[\u0430-\u044f\u0410-\u042f\u0451\u0401]")
TASK_MARKS = ("tell me", "say ", "ask me", "make ", "use ", "give me", "imagine",
              "describe", "try ", "repeat", "complete", "answer", "what ", "where ",
              "why ", "how ", "when ", "who ", "do you", "can you", "could you",
              "please ")


def question_of(text):
    """Vopros iz repliki - kak v ChatController._question_of."""
    value = str(text or "")
    if "?" not in value:
        return ""
    parts = []
    for piece in value.split("?"):
        if not piece.strip():
            continue
        tail = piece
        for mark in (".", ";", ":"):
            if mark in tail:
                tail = tail.rsplit(mark, 1)[-1]
        tail = tail.strip().strip('"').strip("'").strip()
        if tail:
            parts.append(tail)
    return " ".join(parts)[-200:]


def task_sentences(text):
    """Predlozheniya, pohozhie na ZADANIE dlya uchenika."""
    out = []
    for raw in re.split(r"(?<=[.!?])\s+", str(text or "")):
        low = raw.strip().lower()
        if len(low) < 8:
            continue
        if any(low.startswith(m) or (" " + m) in low for m in TASK_MARKS):
            out.append(raw.strip())
    return out


def build_llm(port):
    url = "http://127.0.0.1:%d/v1/chat/completions" % int(port)
    return llm_client.LLMClient(url=url, max_tokens=config.LLM_CHAT_MAX_TOKENS,
                                temperature=0.5, stop=STOP)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "8080"
    tag = sys.argv[2] if len(sys.argv) > 2 else "gemma"
    # probe: put k dopolnitelnogo pravila (tolko v pamyati, fajly ne trogaem)
    extra = ""
    if len(sys.argv) > 3 and sys.argv[3] != "-":
        extra = open(sys.argv[3], encoding="utf-8").read().strip()
    data = json.load(open(CASES, encoding="utf-8"))
    pm = ProgressMap()
    user = user_manager.get_user(1) or {}
    profile = profile_store.load(1)
    student = {"name": user.get("name"), "name_latin": user.get("name_latin"),
               "gender": user.get("gender")}
    teacher = user_manager.teacher_name(user)
    level = user.get("level")
    llm = build_llm(port)
    print("port=%s tag=%s level=%s teacher=%s" % (port, tag, level, teacher), flush=True)

    rows = []
    for ep in data["episodes"]:
        lid = ep["id"]
        les = pm.get_lesson(lid) or {}
        point_id = pm.point_of_lesson(lid)
        point = (pm.get_point(point_id) or {}) if point_id else {}
        block_title = str(point.get("block_title") or "").strip()
        title = str(les.get("title") or lid)
        topic = " - ".join(x for x in (block_title, title) if x) or title
        session = L.LessonSession(lid, point_id=point_id,
                                  lesson_type=les.get("type"), title=title,
                                  topic=topic, block_number=point.get("number"),
                                  block_title=block_title,
                                  reply_target=les.get("replies"),
                                  code=les.get("code") or "")
        payload = {"title": title, "type": les.get("type"), "topic": topic,
                   "task": L.opening_task(les.get("type")),
                   "exam": L.is_check_lesson(les.get("type")),
                   "lesson_id": lid}
        history, asked_q, issued = [], [], []
        last_q = ""
        for idx, item in enumerate(ep["items"]):
            said = item["said"]
            if item.get("credit_before"):
                session.credit_task(said)
            lp = dict(payload)
            lp.update(session.task_prompt())
            if session.finished or not session.is_active:
                lp["lesson_closing"] = True
            closed = bool(lp.get("lesson_closing"))
            parts = pb.build_prompt_parts(
                "lesson", profile, "en", level=level, student=student,
                context="", plan="", lesson=lp, now=datetime.datetime.now(),
                variety=True, english_only=bool(getattr(config, "ENGLISH_ONLY", False)),
                american=bool(getattr(config, "AMERICAN_ENGLISH", True)),
                words=None, teacher=teacher, hesitation=True, word_forms=True,
                logic=True)
            stable = parts["stable"] + (("\n\n" + extra) if extra else "")
            msgs = pb.build_messages(stable, history, said,
                                     tail=parts["dynamic"])
            t0 = time.perf_counter()
            ok, raw = llm.complete(msgs, max_tokens=config.LLM_CHAT_MAX_TOKENS,
                                   temperature=0.5, stop=STOP)
            sec = time.perf_counter() - t0
            reply = pb.clean_response(raw) if ok else ""
            raw_reply = reply
            raw_flags = {}
            ctx = rc.build_context(lp, last_q, "en")
            problems = rc.check(reply, ctx) if ok else []
            retried = False
            if problems:
                retried = True
                tail2 = parts["dynamic"] + rc.note(problems)
                msgs2 = pb.build_messages(stable, history, said, tail=tail2)
                t1 = time.perf_counter()
                ok2, raw2 = llm.complete(msgs2, max_tokens=config.LLM_CHAT_MAX_TOKENS,
                                         temperature=0.5, stop=STOP)
                sec += time.perf_counter() - t1
                again = pb.clean_response(raw2) if ok2 else ""
                if again and not rc.check(again, ctx):
                    reply = again
            q = question_of(reply)
            flags = {}
            flags["two_questions"] = reply.count("?") >= 2
            flags["same_question"] = bool(q) and any(
                L.same_task(q, prev) or L._flat(q) == L._flat(prev)
                for prev in asked_q if prev)
            new_tasks = task_sentences(reply)
            flags["repeat_task"] = any(
                L.same_task(t, old) for t in new_tasks for old in issued)
            flags["question_when_closed"] = bool(reply.count("?")) and closed
            flags["not_english"] = bool(CYR.search(reply))
            flags["truncated"] = (not reply) or (
                reply.strip()[-1] not in u'.!?"\u2026)' if reply.strip() else True)
            kws = [k.lower() for k in ep.get("keywords") or []]
            flags["off_topic"] = bool(reply) and bool(kws) and not any(
                k in reply.lower() for k in kws)
            rows.append({"episode": lid, "idx": idx + 1, "said": said,
                         "ok": ok, "sec": round(sec, 2), "reply": reply,
                         "task": "%d/%d" % (session.task_index, session.tasks_total),
                         "phase": session.task_phase, "closed": closed,
                         "raw_reply": raw_reply, "problems": problems,
                         "retried": retried,
                         "stable_chars": len(stable),
                         "flags": flags})
            print("%s #%d %.2fs %s" % (lid, idx + 1, sec,
                  ",".join(k for k, v in flags.items() if v) or "-"), flush=True)
            if q:
                asked_q.append(q)
                last_q = q
            issued.extend(new_tasks)
            history.append("Student: " + said)
            history.append("Assistant: " + reply)
            if item.get("credit") and not item.get("credit_before"):
                session.credit_task(said)
        # konec epizoda
    save(rows, tag, port)


NAMES = [("same_question", "povtor voprosa"), ("repeat_task", "povtor zadaniya"),
         ("off_topic", "ushel s temy (myagko)"), ("two_questions", "dva voprosa"),
         ("question_when_closed", "vopros pri zakrytom uroke"),
         ("not_english", "ne po-anglijski"), ("truncated", "obrubok bez znaka")]


def save(rows, tag, port):
    n = len(rows)
    bad = [r for r in rows if not r["ok"]]
    secs = [r["sec"] for r in rows if r["ok"]]
    counts = {k: sum(1 for r in rows if r["flags"][k]) for k, _ in NAMES}
    per100 = {k: round(100.0 * v / n, 1) if n else 0 for k, v in counts.items()}
    total = sum(counts.values())
    out = {"tag": tag, "port": port, "n": n, "errors": len(bad),
           "avg_sec": round(sum(secs) / len(secs), 2) if secs else 0,
           "max_sec": round(max(secs), 2) if secs else 0,
           "violations": counts, "per100": per100,
           "total_violations": total,
           "per100_total": round(100.0 * total / n, 1) if n else 0,
           "rows": rows}
    with open(os.path.join(BASE, "logs", "_eval_%s.json" % tag), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    lines = ["# Zamer: %s (port %s)" % (tag, port), "",
             "replik: %d, oshibok servera: %d, srednee %.2f s (max %.2f s)" % (
                 n, len(bad), out["avg_sec"], out["max_sec"]), "",
             "| tip narusheniya | sht | na 100 |", "|---|---|---|"]
    for k, title in NAMES:
        lines.append("| %s | %d | %.1f |" % (title, counts[k], per100[k]))
    lines.append("| **vsego** | **%d** | **%.1f** |" % (total, out["per100_total"]))
    lines += ["", "| epizod | # | uchenik | otvet modeli | flagi |",
              "|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %d | %s | %s | %s |" % (
            r["episode"], r["idx"], r["said"].replace("|", "/"),
            r["reply"].replace("|", "/").replace("\n", " "),
            ", ".join(k for k, v in r["flags"].items() if v) or "-"))
    with open(os.path.join(BASE, "logs", "_eval_%s.md" % tag), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    print("DONE n=%d viol=%d per100=%.1f avg=%.2fs" % (
        n, total, out["per100_total"], out["avg_sec"]), flush=True)


if __name__ == "__main__":
    main()
