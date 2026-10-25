# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GLOSSARY_HIGHLIGHT.PY — подсветка слова под курсором
# =========================================================
#   python tests\test_glossary_highlight.py
#
# ЗАЧЕМ. Решение ученика (25.10.2026): в окне подсказки — ТОЛЬКО русский
# перевод, а переводимое слово/фраза в облачке ВЫДЕЛЯЕТСЯ ЦВЕТОМ, пока
# окно открыто. При уходе курсора, смене слова и прокрутке выделение снять.
#
# ГЛАВНАЯ ГРАБЛЯ (замерено 25.10.2026, живой tk.Text):
#   * get("1.0","end-1c") картинку-эмодзи НЕ возвращает (короче на число
#     эмодзи), а в индексах Tk она занимает 1 символ: "1.0 + 4c" -> 1.4.
#   Поэтому смещение из словаря нельзя переводить как "1.0 + Nc" —
#   нужна карта, собранная при вставке (chat_view._fill_body).
#
# Проверяем:
#   1) карту смещений: конец текста сходится с end-1c;
#   2) выделение одного слова (в т.ч. ПОСЛЕ эмодзи) — точные границы;
#   3) выделение фразы из двух слов, между которыми эмодзи;
#   4) смену слова: выделен ровно один диапазон;
#   5) снятие: уход курсора и прокрутка;
#   6) цвет — warn из палитры, фон облачка не тронут;
#   7) в окне ровно одна надпись (только русский);
#   8) в облачке ученика выделение работает так же.
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

import customtkinter as ctk      # noqa: E402

import theme                     # noqa: E402
from ui.widgets.chat_view import ChatView   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  \u2705 " if ok else "  \u274c ") + name + ("" if ok else "  \u2190 " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def ranges(body):
    """Диапазоны тега gloss как список пар индексов."""
    flat = body.tag_ranges("gloss")
    return [(str(flat[i]), str(flat[i + 1])) for i in range(0, len(flat), 2)]


def hit_for(clean, word, ru="перевод", phrase=False):
    start = clean.find(word)
    return {"en": word, "ru": ru, "phrase": phrase,
            "start": start, "end": start + len(word)}


root = ctk.CTk()
root.geometry("760x520+40+40")
root.withdraw()
palette = theme.DARK
chat = ChatView(root, palette, on_hover_word=lambda text, pos: None)
chat.pack(fill="both", expand=True)
root.update()

# ---------------------------------------------------------
print("[1] Карта смещений (эмодзи считаются в индексах Tk)")
mark = chat.add_message("Jane", "\U0001F916 Nice to see you there!")
root.update()
body = chat._messages[mark].body
clean = body.get("1.0", "end-1c")
table = getattr(body, "_gloss_map", None)
check("карта построена при вставке", isinstance(table, list) and len(table) > 1, table)
check("карта начинается с (0, 0)", table and table[0] == (0, 0), table and table[:1])
end_idx = body.index("end-1c")
check("конец текста по карте = end-1c",
      chat._text_index(body, len(clean)) == end_idx,
      (chat._text_index(body, len(clean)), end_idx))

pictures = tuple(body.image_names())
check("эмодзи нарисованы картинками", len(pictures) >= 1, len(pictures))


# ---------------------------------------------------------
print("\n[2] Выделение слова после эмодзи")
hit = hit_for(clean, "there", "там")
check("слово найдено в тексте", hit["start"] > 0, clean)
chat._gloss_show(hit, 100, 100, body=body)
root.update()
got = ranges(body)
check("тег gloss появился", len(got) == 1, got)
if got:
    check("выделено ровно слово «there»", body.get(got[0][0], got[0][1]) == "there",
          body.get(got[0][0], got[0][1]))
    check("границы совпали с посчитанными",
          got[0] == (chat._text_index(body, hit["start"]),
                     chat._text_index(body, hit["end"])), got)
    if pictures:
        # ЗАМЕР ГРАБЛИ: наивный "1.0 + Nc" и карта дают РАЗНЫЕ индексы —
        # эмодзи-картинка сдвигает текст на 1 символ индекса.
        naive = body.index("1.0 + %dc" % hit["start"])
        real = chat._text_index(body, hit["start"])
        check("карта не совпадает с наивным «1.0 + Nc»", naive != real, (naive, real))
        check("по карте стоит первая буква «there»", body.get(real) == "t",
              (real, body.get(real)))
        check("по наивному индексу слова нет", body.get(naive) != "t",
              (naive, body.get(naive)))

# ---------------------------------------------------------
print("\n[3] Окно: только русский, одна надпись")
texts = []
tip = chat._gloss_tip
if tip is not None:
    for child in tip.winfo_children():
        for label in child.winfo_children():
            try:
                texts.append(label.cget("text"))
            except Exception:
                pass
check("в окне ровно одна надпись", len(texts) == 1, texts)
check("надпись — русский перевод", texts == ["там"], texts)

# ---------------------------------------------------------
print("\n[4] Цвет и фон")
check("цвет тега = warn из палитры",
      str(body.tag_cget("gloss", "foreground")).lower() == palette["warn"].lower(),
      body.tag_cget("gloss", "foreground"))
check("фон облачка не тронут",
      body.tag_cget("gloss", "background") in ("", None, "None"),
      body.tag_cget("gloss", "background"))
check("подсвеченное облачко запомнено", chat._gloss_body is body)

# ---------------------------------------------------------
print("\n[5] Смена слова — один диапазон")
hit2 = hit_for(clean, "see", "видеть")
chat._gloss_show(hit2, 120, 120, body=body)
root.update()
got = ranges(body)
check("остался один диапазон", len(got) == 1, got)
if got:
    check("выделено новое слово «see»", body.get(got[0][0], got[0][1]) == "see",
          body.get(got[0][0], got[0][1]))

# ---------------------------------------------------------
print("\n[6] Снятие выделения")
chat._gloss_hide()
root.update()
check("после ухода курсора тег пуст", ranges(body) == [], ranges(body))
check("облачко забыто", chat._gloss_body is None, chat._gloss_body)

chat._gloss_show(hit, 100, 100, body=body)
root.update()
check("выделение вернулось", len(ranges(body)) == 1, ranges(body))
chat._on_wheel(None)
root.update()
check("прокрутка сняла выделение", ranges(body) == [], ranges(body))
check("прокрутка закрыла окно", chat._gloss_tip is None)

# ---------------------------------------------------------
print("\n[7] Фраза из двух слов, между ними эмодзи")
mark2 = chat.add_message("Jane", "Look \U0001F44D forward to it!")
root.update()
body2 = chat._messages[mark2].body
clean2 = body2.get("1.0", "end-1c")
start = clean2.find("Look")
end = clean2.find("forward") + len("forward")
chat._gloss_show({"en": "look forward to", "ru": "с нетерпением ждать",
                  "phrase": True, "start": start, "end": end}, 100, 100, body=body2)
root.update()
got = ranges(body2)
check("фраза выделена одним диапазоном", len(got) == 1, got)
if got:
    marked = body2.get(got[0][0], got[0][1])
    check("выделение покрывает оба слова",
          marked.startswith("Look") and marked.endswith("forward") and
          "forward" in marked, marked)
    check("«to» в выделение НЕ попало", not marked.endswith("to"), marked)
chat._gloss_hide()

# ---------------------------------------------------------
print("\n[8] Облачко ученика — так же")
chat.add_message("\u0412\u044b", "I mean that moment, thanks")
mark3 = chat._order[-1]        # у реплики ученика метка не возвращается
root.update()
body3 = chat._messages[mark3].body
check("это реплика ученика", chat._messages[mark3].is_user is True)
clean3 = body3.get("1.0", "end-1c")
hit3 = hit_for(clean3, "moment", "момент")
chat._gloss_show(hit3, 100, 100, body=body3)
root.update()
got = ranges(body3)
check("у ученика выделение появилось", len(got) == 1, got)
if got:
    check("выделено «moment»", body3.get(got[0][0], got[0][1]) == "moment",
          body3.get(got[0][0], got[0][1]))
check("подсказка у ученика открыта", chat._gloss_tip is not None)
chat._gloss_hide()
check("у ученика выделение снято", ranges(body3) == [], ranges(body3))

# ---------------------------------------------------------
print()
if FAILED:
    print("\u0418\u0422\u041e\u0413: \u043f\u0440\u043e\u0432\u0430\u043b\u043e\u0432: %d" % len(FAILED))
    for name in FAILED:
        print("  - " + name)
    sys.exit(1)
print("\u0418\u0422\u041e\u0413: \u0432\u0441\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 \u043f\u0440\u043e\u0439\u0434\u0435\u043d\u044b")
