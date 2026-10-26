# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_DICT_BUTTON.PY — кнопка «💡 Перевести» в ОБЫЧНОМ уроке
# =========================================================
#   python tests\test_dict_button.py
#
# Живая жалоба 26.10.2026: урок шёл в режиме «текст» (поле НЕ заблокировано),
# ученик набрал русское слово «примерн» и увидел кнопку «Отправить». Нажатие
# на неё переводило слово, но по подписи этого не понять — ученик не нажал
# вовсе. Проверяем:
#   1) обычный режим + кириллица → «💡 Перевести», кнопка живая;
#   2) обычный режим + английский → «Отправить»;
#   3) подпись пересчитывается на КАЖДОЕ нажатие клавиши;
#   4) экзамен (замок без словаря) + кириллица → по-прежнему «Голосом»;
#   5) урок голосом (замок со словарём) + кириллица → перевод работает;
#   6) гейт «нет профиля» важнее кириллицы.

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

import customtkinter as ctk                                     # noqa: E402
import theme                                                    # noqa: E402
from ui.widgets.input_bar import (InputBar, LOCK_BUTTON_TEXT,   # noqa: E402
                                  SEND_TEXT, TRANSLATE_TEXT)

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def pump(root, n=12):
    for _ in range(n):
        root.update()


def main():
    print("=" * 64)
    print("Проверка кнопки «💡 Перевести» в обычном (незаблокированном) уроке")
    print("=" * 64)

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("760x220")

    bar = InputBar(root, theme.DARK, on_send=lambda: None)
    bar.pack(side="bottom", fill="x")
    pump(root)

    def text_of():
        return bar.send_btn.cget("text")

    # ---------- 1. Обычный урок: русское слово ----------
    print("\n[1] Поле не заблокировано, в нём кириллица")
    check("поле не в замке", bar.is_locked is False)
    bar.set_text("примерн")
    pump(root)
    check("кнопка стала «💡 Перевести»", text_of() == TRANSLATE_TEXT, text_of())
    check("и она нажимаема", str(bar.send_btn.cget("state")) == "normal",
          bar.send_btn.cget("state"))

    # ---------- 2. Английский текст ----------
    print("\n[2] Поле не заблокировано, текст английский")
    bar.set_text("I eat flatbread")
    pump(root)
    check("кнопка снова «Отправить»", text_of() == SEND_TEXT, text_of())
    check("и нажимаема", str(bar.send_btn.cget("state")) == "normal",
          bar.send_btn.cget("state"))

    # ---------- 3. Нажатие клавиши пересчитывает подпись ----------
    print("\n[3] Подпись обновляется на каждое нажатие клавиши")
    bar.clear_text()
    pump(root)
    check("пустое поле → «Отправить»", text_of() == SEND_TEXT, text_of())
    bar._field.insert("end", "кот")
    bar._on_key_release()
    pump(root)
    check("после набора кириллицы кнопка пересчиталась", text_of() == TRANSLATE_TEXT,
          text_of())
    bar._field.delete("1.0", "end")
    bar._on_key_release()
    pump(root)
    check("после стирания вернулась «Отправить»", text_of() == SEND_TEXT, text_of())

    # ---------- 4. Экзамен: замок без словаря ----------
    print("\n[4] Экзамен (замок, словарь выключен): перевод не предлагаем")
    bar.set_locked(True, "🔒 Экзамен", allow_dictionary=False)
    bar.set_text("примерн")
    pump(root)
    check("кнопка осталась «Голосом»", text_of() == LOCK_BUTTON_TEXT, text_of())
    check("и выключена", str(bar.send_btn.cget("state")) == "disabled",
          bar.send_btn.cget("state"))
    bar.set_locked(False)
    pump(root)

    # ---------- 5. Замок СО словарём (урок голосом) ----------
    print("\n[5] Урок «только голосом»: перевод по-прежнему работает")
    bar.set_locked(True, "🎤 Говори в микрофон", allow_dictionary=True)
    bar.set_text("лежать")
    pump(root)
    check("кнопка «💡 Перевести»", text_of() == TRANSLATE_TEXT, text_of())
    bar.set_locked(False)
    bar.clear_text()
    pump(root)

    # ---------- 6. Гейт важнее кириллицы ----------
    print("\n[6] Нет профиля/модели — причина на кнопке важнее")
    bar.set_enabled(False, "Заполни профиль")
    bar.set_text("примерн")
    pump(root)
    check("на кнопке причина гейта", text_of() == "Заполни профиль", text_of())
    check("кнопка выключена", str(bar.send_btn.cget("state")) == "disabled",
          bar.send_btn.cget("state"))
    bar.set_enabled(True)
    pump(root)
    check("после гейта снова «💡 Перевести»", text_of() == TRANSLATE_TEXT, text_of())

    # ---------- 7. Исходник: нет пересчёта «только в замке» ----------
    print("\n[7] В _on_key_release нет условия «только если заблокировано»")
    src = open(os.path.join(ROOT, "ui", "widgets", "input_bar.py"),
               encoding="utf-8").read()
    block = src[src.find("def _on_key_release"):]
    block = block[:block.find("def _on_return")]
    check("_apply_state зовётся без if self._locked",
          "_apply_state()" in block and "if self._locked:" not in block,
          block.replace("\n", " ")[:160])

    root.destroy()

    print()
    if FAILED:
        print("❌ ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("   - " + name)
        return 1
    print("✅ Все проверки пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
