# -*- coding: utf-8 -*-
"""Тест пакета проверок ответа модели (reply_checks, §74 = шаг 2 плана §72).

Запуск: python tests/test_reply_checks.py
Печатает по-русски, поэтому в консоли cp1251 возможны кракозябры — смотреть
exit code и строки с ❌.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import reply_checks as rc

FAILS = []


def check(title, ok, detail=""):
    if ok:
        print("  ok   %s" % title)
    else:
        print("  ❌   %s  %s" % (title, detail))
        FAILS.append(title)


LESSON = {"asked_tasks": "i bought a hat \u00b7 i pay with a card",
          "task_phase": "ask"}
CTX = rc.build_context(LESSON, "do you need a receipt", "en")


def run(text, **kw):
    return rc.check(text, dict(CTX, **kw))


print("[1] пустой ответ")
check("пустой -> empty", run("") == ["empty"])
check("пробелы -> empty", run("   ") == ["empty"])
check("короткое 'Nice!' чистое", run("Nice!") == [])


print("[2] не по-английски")
check("кириллица -> not_english",
      "not_english" in run("\u041e\u0442\u043b\u0438\u0447\u043d\u043e, \u0414\u0430\u043c\u0438\u043b\u044c! What next?"))
check("ученик говорил по-русски -> не нарушение",
      "not_english" not in run("\u041e\u0442\u043b\u0438\u0447\u043d\u043e!", student_lang="ru"))


print("[3] метка-раздел (живой случай Qwen, замер §73)")
check("'Praising: ...' -> label", "label" in run("Praising: Good job! What color?"))
check("'Feedback: ...' -> label", "label" in run("Feedback: nice try. What next?"))
check("обычная похвала не метка", "label" not in run("Great job! What color?"))


print("[4] два вопроса")
check("два '?' -> two_questions",
      "two_questions" in run("What color is it? Do you like it?"))
check("один вопрос чистый", "two_questions" not in run("What color is it?"))


print("[5] вопрос при закрытом уроке")
check("закрыто + вопрос -> question_when_closed",
      "question_when_closed" in run("Great job! What else?", closed=True))
check("закрыто без вопроса чисто",
      rc.check("Great job, well done!", dict(CTX, closed=True)) == [])


print("[6] повтор вопроса (§71)")
same = "You are welcome, Damil; next, do you need a receipt for your jacket, or not?"
check("тот же вопрос -> same_question", "same_question" in run(same))
check("новый вопрос чистый",
      "same_question" not in run("Blue is great! What do you wear in winter?"))


print("[7] повтор задания (§70)")
check("'try saying I bought a hat' -> repeat_task",
      "repeat_task" in run('Good! Now try saying, "I bought a hat".'))
check("новое задание чистое",
      "repeat_task" not in run("Nice! Tell me about your blue jacket."))


print("[8] обрубок")
check("длинный без точки -> truncated", "truncated" in run("Hello there my friend"))
check("с точкой чисто", "truncated" not in run("Hello there my friend."))


print("[9] поправка для повторного запроса")
note = rc.note(["same_question", "repeat_task"])
check("в поправке оба правила",
      "Do NOT ask" in note and "DIFFERENT small task" in note)
check("поправка пустая без нарушений", rc.note([]) == "")
check("имена по-русски", rc.names(["empty"]) == ["пустой ответ"])


print("[10] контекст из словаря урока")
closed = rc.build_context({"lesson_closing": True}, "", "en")
check("lesson_closing -> closed", closed["closed"] is True)
done = rc.build_context({"task_phase": "done"}, "", "en")
check("phase=done -> closed", done["closed"] is True)
tasks = rc.build_context(LESSON, "", "en")
check("asked_tasks разобраны", tasks["asked_tasks"] == ["i bought a hat",
                                                        "i pay with a card"])


print()
if FAILS:
    print("ПРОВАЛОВ: %d -> %s" % (len(FAILS), "; ".join(FAILS)))
    sys.exit(1)
print("ВСЁ ХОРОШО")
