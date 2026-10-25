# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON_SUMMARY_UI.PY — итог урока подключён к окну
# =========================================================
#   python tests\test_lesson_summary_ui.py
#
# ЗАЧЕМ. lesson_summary.py сам по себе ничего не показывает: его надо
# ВЫЗВАТЬ в ui/app._on_lesson_finished. Этот тест проверяет склейку:
#   * импорт lesson_summary в app.py есть;
#   * обычная ветка зовёт summary_text + praise_text;
#   * итог идёт в чат, похвала ещё и в голос (self._say);
#   * русский итог в голос НЕ отправляется (иначе английский голос
#     прочитает его мусором);
#   * ветки ЭКЗАМЕНА не получили обычный итог (у них свой не меняем).
#
# Проверка читает исходник, а не поднимает Tk-окно: поведение самого текста
# уже проверено в tests/test_lesson_summary.py. Дополнительно гоняем
# настоящий LessonSession, чтобы имена полей (reply_target) не разошлись.
# =========================================================

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import lesson                                                    # noqa: E402
import lesson_summary                                            # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


APP = os.path.join(ROOT, "ui", "app.py")
with open(APP, "r", encoding="utf-8") as fh:
    SOURCE = fh.read()


def method_body(name):
    """Тело метода по имени (до следующего def на том же отступе)."""
    start = SOURCE.find("def %s(" % name)
    if start < 0:
        return ""
    rest = SOURCE[start:]
    match = re.search(r"\n    def ", rest[1:])
    if match:
        return rest[:match.start() + 1]
    return rest


print("[1] Модуль подключён к окну")

check("в app.py есть import lesson_summary",
      re.search(r"^import lesson_summary$", SOURCE, re.M) is not None)

body = method_body("_on_lesson_finished")
check("метод _on_lesson_finished найден", body.strip() != "")

print("[2] Обычная ветка показывает итог")

check("зовёт lesson_summary.summary_text", "lesson_summary.summary_text(" in body,
      body.count("summary_text"))
check("передаёт название закрытого блока", "block_title=" in body,
      "block_title=")
check("итог уходит в чат", "add_message(self.teacher_name, text)" in body)
check("зовёт lesson_summary.praise_text", "lesson_summary.praise_text(" in body)
check("похвала видна в чате", "add_message(self.teacher_name, praise)" in body)
check("похвала озвучивается", "self._say(praise)" in body)
check("русский итог в голос НЕ уходит", "self._say(text)" not in body)

print("[3] Порядок: сначала итог, потом озвучка, потом закрытие урока")

pos_text = body.find("add_message(self.teacher_name, text)")
pos_praise = body.find("self._say(praise)")
pos_end = body.find("self._end_lesson()", pos_text if pos_text > 0 else 0)
check("итог раньше похвалы", 0 <= pos_text < pos_praise, (pos_text, pos_praise))
check("похвала раньше закрытия урока", 0 <= pos_praise < pos_end,
      (pos_praise, pos_end))

print("[4] Экзамен не получил обычный итог (у него свой)")

head = body.split("lesson_summary.summary_text(")[0] if body else ""
check("до обычной ветки нет summary_text", "lesson_summary.summary_text(" not in head,
      head.count("summary_text"))
check("итог экзамена на месте", "self.exam_summary_text(exam_result)" in body)
check("слово ЭКЗАМЕН в тексте сохранилось",
      "ЭКЗАМЕН" in method_body("exam_summary_text"))

print("[5] Настоящая сессия занятия даёт те же числа")

session = lesson.LessonSession("city/1.1", block_title="В городе", reply_target=12)
session.register_reply()
session.register_reply()
session.use_hint()
session.add_mistakes(2)

text = lesson_summary.summary_text(session, block_title=session.block_title)
check("id урока из сессии", "Урок city/1.1 пройден" in text, text)
check("цель реплик из reply_target", "Реплик: 2 из 12" in text, text)
check("подсказка посчитана", "Подсказок: 1" in text, text)
check("ошибки посчитаны", "Ошибок: 2" in text, text)
check("блок из сессии", "Блок «В городе» пройден целиком" in text, text)

praise = lesson_summary.praise_text(session)
check("похвала по настоящей сессии", "2 replies" in praise and "2 mistakes" in praise,
      praise)

print()
if FAILED:
    print("❌ ПРОВАЛОВ: %d" % len(FAILED))
    for name in FAILED:
        print("   • " + name)
    sys.exit(1)
print("✅ Итог урока подключён к окну.")
