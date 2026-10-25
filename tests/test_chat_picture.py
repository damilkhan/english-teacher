# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_CHAT_PICTURE.PY — фото в облачке преподавателя
# =========================================================
#   python tests\test_chat_picture.py
#
# Проверяем на живом (скрытом) окне ChatView:
#   1) add_message(..., picture=путь) показывает фото в облачке;
#   2) фото не шире PICTURE_MAX_PX и не шире облачка;
#   3) ссылка на PhotoImage живёт в реплике (иначе Tk покажет пусто);
#   4) без фото / с битым путём ничего не ломается, текст остаётся;
#   5) текст реплики и get_text() не меняются.
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

import customtkinter as ctk          # noqa: E402
import theme                         # noqa: E402
import picture_task                  # noqa: E402
from ui.widgets import chat_view     # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("=" * 60)
    print("ФОТО В ЧАТЕ (ChatView)")
    print("=" * 60)

    task = picture_task.describe_task("A2")
    path = task["path"]

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("700x340")
    root.withdraw()                       # окно не мелькает на экране
    view = chat_view.ChatView(root, theme.DARK)
    view.pack(fill="both", expand=True)
    root.update()

    print("\n[1] Реплика с фото")
    mark = view.add_message("Verbot", "Describe this photo, please.", picture=path)
    root.update()
    msg = view._messages.get(mark)
    check("метка реплики вернулась", bool(mark), mark)
    check("путь к фото запомнен", msg is not None and msg.picture == path,
          getattr(msg, "picture", None))
    check("PhotoImage создан", msg is not None and msg.photo is not None)
    check("подпись с фото создана",
          msg is not None and msg.picture_lbl is not None)
    check("текст реплики не тронут",
          msg is not None and msg.text == "Describe this photo, please.",
          getattr(msg, "text", None))

    print("\n[2] Размеры")
    limit = min(chat_view.PICTURE_MAX_PX, view._bubble_max_px())
    width = msg.photo.width() if msg.photo is not None else 0
    height = msg.photo.height() if msg.photo is not None else 0
    check("ширина ≤ предела (%.0f px)" % limit, 0 < width <= limit, width)
    check("фото не сплющено (высота больше 100)", height > 100, height)
    check("пропорции сохранены (отклонение ≤ 1 px)",
          abs(height - width * 769.0 / 1024.0) <= 1.5,
          "%dx%d" % (width, height))

    print("\n[3] Фото не попало в текст")
    text = view.get_text()
    check("get_text содержит текст реплики", "Describe this photo" in text)
    check("get_text не вырос на имя файла", ".jpg" not in text, text[-80:])

    print("\n[4] Без фото и с битым путём")
    plain = view.add_message("Verbot", "No picture here.")
    root.update()
    check("без фото подписи нет",
          view._messages[plain].picture_lbl is None)
    broken = view.add_message("Verbot", "Broken path.",
                              picture=os.path.join(ROOT, "assets", "нет.jpg"))
    root.update()
    check("битый путь не ломает реплику",
          view._messages[broken].photo is None)
    check("текст реплики с битым путём на месте",
          view._messages[broken].text == "Broken path.")
    check("реплика всё равно в чате", broken in view._order)

    print("\n[5] Реплика ученика с фото (на всякий случай)")
    user_mark = view.add_message("Вы", "My description.", picture=path)
    root.update()
    check("у реплики ученика нет метки", user_mark is None)
    last = view._messages[view._order[-1]]
    check("фото у ученика тоже показывается", last.photo is not None)

    try:
        root.destroy()
    except Exception:
        pass

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛОВ: %d" % len(FAILED))
        for name in FAILED:
            print("  - " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
