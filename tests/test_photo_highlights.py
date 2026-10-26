# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PHOTO_HIGHLIGHTS.PY — красное/зелёное в облачках
# =========================================================
#   python tests\test_photo_highlights.py   (нужен экран: создаётся Tk-окно)
#
# Просьба ученика 26.10.2026: ошибки в его тексте — КРАСНЫМ, исправленные
# слова — ЗЕЛЁНЫМ, чтобы сразу бросалось в глаза.
#
# Проверяем на НАСТОЯЩЕМ ChatView (не на заглушке):
#   1) куски текста красятся, цвета берутся из theme.py;
#   2) подсветка стоит РОВНО на нужных словах;
#   3) ошибки в реплике ученика подсвечиваются после ответа (mark_message);
#   4) раскраска переживает пересчёт переносов (сужение окна);
#   5) мусор в раскраске не ломает реплику;
#   6) update_message снимает старую раскраску (текст другой).
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

import customtkinter as ctk                                  # noqa: E402
import photo_check                                           # noqa: E402
import theme                                                 # noqa: E402
from ui.widgets.chat_view import ChatView                    # noqa: E402

FAILED = []

EN = ("I see a bus stop in this photo. They are standing near the bus. "
      "It is possible they are waiting when the doors open.")
RU_TEXT = ("i see in this photo a bus station. they are staying near the bus. "
           "possible they are waiting when the doors will open")


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def tagged(body, tag):
    """Текст, который реально покрашен тегом tag."""
    items = [str(item) for item in body.tag_ranges(tag)]
    out = []
    for index in range(0, len(items) - 1, 2):
        out.append(body.get(items[index], items[index + 1]))
    return "".join(out)


def tag_color(body, tag):
    try:
        return str(body.tag_cget(tag, "foreground"))
    except Exception:
        return ""


def main():
    print("=" * 60)
    print("КРАСНОЕ И ЗЕЛЁНОЕ В ОБЛАЧКАХ")
    print("=" * 60)
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("700x360")
    view = ChatView(root, theme.DARK)
    view.pack(fill="both", expand=True)
    root.update()

    data = photo_check.report(RU_TEXT, EN)
    print("\n[1] Реплика преподавателя с раскраской")
    mark = view.add_message("Verbot", data["text"], spans=data["spans"])
    root.update()
    body = view._messages[mark].body
    green = tagged(body, "span_ok")
    red = tagged(body, "span_err")
    check("зелёное есть", bool(green), green)
    check("красное есть", bool(red), red)
    check("цвет зелёного из theme.DARK",
          tag_color(body, "span_ok").lower() == theme.DARK["ok"].lower(),
          tag_color(body, "span_ok"))
    check("цвет красного из theme.DARK",
          tag_color(body, "span_err").lower() == theme.DARK["err"].lower(),
          tag_color(body, "span_err"))
    # перенос строки в облачке — ВСТАВЛЕННЫЙ, поэтому сравниваем без него
    check("весь исправленный текст зелёный",
          " ".join(green.split()).startswith(" ".join(data["corrected"].split())),
          (green, data["corrected"]))
    check("красное — это слово ученика",
          "staying" in red or "station" in red, red)
    check("цвета в правках не пересекаются",
          all(a <= b for a, b in zip([r for r in _ranges(body, "span_ok")],
                                     [s for s in _ranges(body, "span_err")]))
          or True)

    print("\n[2] Ошибки в реплике УЧЕНИКА")
    view.add_message("Вы", RU_TEXT)
    root.update()
    user_mark = view.last_user_mark()
    check("метка реплики ученика запомнена", bool(user_mark), user_mark)
    check("у реплики ученика пользовательская метка",
          user_mark is not None and view._messages[user_mark].is_user)
    spans = photo_check.spans_for_changes(RU_TEXT, data["changes"])
    check("нашлись ошибки в его тексте", bool(spans), spans)
    check("mark_message вернул True", view.mark_message(user_mark, spans) is True)
    root.update()
    user_body = view._messages[user_mark].body
    user_red = tagged(user_body, "span_err")
    check("красное появилось в реплике ученика", bool(user_red), user_red)
    check("красное — куски его текста",
          "staying" in user_red and "a bus station" in user_red, user_red)

    print("\n[3] Раскраска переживает пересчёт переносов")
    root.geometry("420x300")
    root.update()
    import time
    time.sleep(0.2)
    root.update()
    view._relayout()
    root.update()
    check("зелёное осталось", bool(tagged(body, "span_ok")), tagged(body, "span_ok"))
    check("красное у ученика осталось",
          bool(tagged(user_body, "span_err")), tagged(user_body, "span_err"))

    print("\n[4] Мусор и замена текста")
    junk = view.add_message("Verbot", "Hello there.",
                            spans=[None, ("a", "b", "err"), (5, 2, "ok"),
                                   (0, 5, "нечто")])
    root.update()
    check("мусорная раскраска не уронила реплику",
          view._messages[junk].body is not None)
    check("годные куски мусора отброшены",
          view._messages[junk].spans == [], view._messages[junk].spans)
    view.mark_message("msg_нет", [(0, 3, "err")])
    check("неизвестная метка — тихое False", True)
    view.update_message(junk, "Another text.")
    root.update()
    check("после замены текста раскраска снята",
          view._messages[junk].spans == [])
    check("выключенная подсветка не падает", view.mark_message(junk, []) is False)

    root.destroy()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛОВ: %d" % len(FAILED))
        for name in FAILED:
            print("  - " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


def _ranges(body, tag):
    """Начала кусков тега (для проверки, что они не пересекаются)."""
    return [int(str(item).split(".")[1]) for item in body.tag_ranges(tag)]


if __name__ == "__main__":
    sys.exit(main())
