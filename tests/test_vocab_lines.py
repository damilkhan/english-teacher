# -*- coding: utf-8 -*-
# =========================================================
# TEST_VOCAB_LINES.PY — фразы Вербота в окне слов
# =========================================================
# Просьбы ученика 27.10.2026:
#   1) перед окном карточек Вербот ОТВЕЧАЕТ по-английски и проговаривает
#      фразу до конца — окно открывается после речи (см. test_vocab_request);
#   2) на верный ответ — РАЗНЫЕ похвалы, одна фраза не больше 2 раз за заход;
#   3) на промах — РЕДКО подбадривание, тоже разное;
#   4) одна главная кнопка: «Запись» → «Дальше» → «Готово» на последнем слове.
#
# Здесь проверяем ВЫБОР ФРАЗ и устройство окна по исходнику (Tk не нужен).
# =========================================================

import io
import os
import random
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import vocab_lines

FAILED = []


def check(name, ok, detail=None):
    if ok:
        print("  \u2705 %s" % name)
    else:
        print("  \u274c %s  \u2192  %s" % (name, detail))
        FAILED.append(name)


def has_cyrillic(text):
    return any("\u0400" <= ch <= "\u04ff" for ch in str(text or ""))


def read(path):
    with io.open(os.path.join(BASE, path), encoding="utf-8") as fh:
        return fh.read()


# =========================================================
# 1. Наборы фраз
# =========================================================
def test_sets():
    print("\n[1] Наборы фраз: английские, разные, без дублей")
    for label, lines in (("OPEN", vocab_lines.OPEN_LINES),
                         ("PRAISE", vocab_lines.PRAISE_LINES),
                         ("MOTIVATE", vocab_lines.MOTIVATE_LINES),
                         ("EMPTY", vocab_lines.EMPTY_LINES),
                         ("FREE", vocab_lines.FREE_LINES)):
        check("%s: не меньше 6 фраз" % label, len(lines) >= 6, len(lines))
        check("%s: без повторов" % label, len(set(lines)) == len(lines), len(lines))
        check("%s: только по-английски" % label,
              not any(has_cyrillic(line) for line in lines),
              [line for line in lines if has_cyrillic(line)])
        check("%s: без пустых строк" % label,
              all(str(line).strip() for line in lines), lines[:3])
        check("%s: с точкой или восклицанием в конце" % label,
              all(str(line).strip()[-1] in ".!" for line in lines), lines[:3])


# =========================================================
# 2. Фраза перед окном
# =========================================================
def test_open():
    print("\n[2] Фраза перед окном: из набора и не та же подряд")
    first = vocab_lines.pick_open()
    check("фраза из OPEN_LINES", first in vocab_lines.OPEN_LINES, first)
    same = [vocab_lines.pick_open(first) for _ in range(20)]
    check("предыдущая фраза не повторяется", first not in same, first)
    # свой генератор — проверка без случайности
    fixed = vocab_lines.pick_open("Okay! Here are your words.",
                                  rng=random.Random(1))
    check("исключение прошлой фразы работает",
          fixed != "Okay! Here are your words.", fixed)


# =========================================================
# 3. Похвала: не больше двух раз за заход
# =========================================================
def test_praise():
    print("\n[3] Похвала: каждый раз разная, одна фраза — не больше 2 раз")
    # 1) настоящий заход: 10 слов (config.VOCAB_SESSION_SIZE)
    session = vocab_lines.LinePicker(rng=random.Random(2))
    ten = [session.praise() for _ in range(10)]
    check("за заход 10 слов — 10 похвал", all(ten), ten)
    check("за заход ни одна фраза не звучит больше 2 раз",
          max(ten.count(line) for line in set(ten)) <= vocab_lines.MAX_REPEAT,
          max(ten.count(line) for line in set(ten)))
    check("за заход похвалы разные", len(set(ten)) >= 8, len(set(ten)))

    # 2) запас лимита исчерпан: 14 фраз × 2 = 28, берём 27 —
    #    последний разрешённый повтор отдаётся ДРУГОЙ фразе (не то же подряд)
    capacity = vocab_lines.MAX_REPEAT * len(vocab_lines.PRAISE_LINES) - 1
    picker = vocab_lines.LinePicker(rng=random.Random(7))
    heard = [picker.praise() for _ in range(capacity)]
    check("все фразы из PRAISE_LINES",
          all(line in vocab_lines.PRAISE_LINES for line in heard), set(heard))
    worst = max(heard.count(line) for line in set(heard))
    check("ни одна фраза не звучала больше 2 раз", worst <= vocab_lines.MAX_REPEAT, worst)
    check("фразы не кончаются (каждая по столько раз, сколько разрешено)",
          len(set(heard)) == len(vocab_lines.PRAISE_LINES), len(set(heard)))
    check("подряд одна и та же не повторяется",
          all(heard[i] != heard[i + 1] for i in range(len(heard) - 1)), heard[:10])
    check("счётчик повторов собирается",
          picker.used(heard[0]) == min(vocab_lines.MAX_REPEAT, heard.count(heard[0])),
          (heard[0], picker.used(heard[0])))
    check("журнал произнесённого ведётся", len(picker.spoken) == capacity,
          len(picker.spoken))
    # лимит исчерпан — Вербот не замолкает, но не повторяет то же подряд
    more = [picker.praise() for _ in range(30)]
    check("после лимита похвала всё равно звучит", all(more), more[:5])
    check("подряд повтор не выпадает",
          (heard[-1] != more[0]) and all(more[i] != more[i + 1] for i in range(len(more) - 1)),
          more[:8])

    # новый заход — лимит повторов снова свободен
    fresh = vocab_lines.LinePicker(rng=random.Random(7))
    check("новый заход начинает счёт заново", fresh.used(heard[0]) == 0,
          fresh.used(heard[0]))

    # когда лимит исчерпан у ВСЕХ фраз — по-прежнему говорим, но не то же подряд
    stingy = vocab_lines.LinePicker(rng=random.Random(3), max_repeat=1)
    many = [stingy.praise() for _ in range(40)]
    check("лимит 1: сначала все фразы по разу",
          len(set(many[:len(vocab_lines.PRAISE_LINES)])) == len(vocab_lines.PRAISE_LINES),
          len(set(many[:len(vocab_lines.PRAISE_LINES)])))
    check("лимит исчерпан — всё равно звучит (не пусто)", all(many), many[:5])


# =========================================================
# 4. Подбадривание: редко и не подряд
# =========================================================
def test_motivate():
    print("\n[4] Подбадривание на промах: редко, разное, не два раза подряд")
    # 1) как часто вообще звучит (300 промахов — статистика шанса)
    picker = vocab_lines.LinePicker(rng=random.Random(11))
    sounds = [picker.maybe_motivate() for _ in range(300)]
    spoken = [line for line in sounds if line]
    share = len(spoken) / 300.0
    check("звучит не на каждый промах", share < 0.6, round(share, 2))
    check("но и не молчит всегда", share > 0.1, round(share, 2))
    check("все фразы из MOTIVATE_LINES",
          all(line in vocab_lines.MOTIVATE_LINES for line in spoken), set(spoken))

    # 2) лимит повторов: 7 фраз × 2 = 14, берём 13 (заход — 10 слов)
    limited = vocab_lines.LinePicker(rng=random.Random(4), chance=1.0)
    said = [limited.maybe_motivate() for _ in range(13)]
    check("подряд одно и то же не повторяется",
          all(said[i] != said[i + 1] for i in range(len(said) - 1)), said[:8])
    check("лимит повторов соблюдён",
          max(said.count(line) for line in set(said)) <= vocab_lines.MAX_REPEAT,
          max(said.count(line) for line in set(said)))

    silent = vocab_lines.LinePicker(rng=random.Random(5), chance=0.0)
    check("шанс 0 — всегда молчит", silent.maybe_motivate() == "", silent.maybe_motivate())
    always = vocab_lines.LinePicker(rng=random.Random(5), chance=1.0)
    check("шанс 1 — говорит всегда", all(always.maybe_motivate() for _ in range(10)))


# =========================================================
# 5. Окно: одна главная кнопка
# =========================================================
def test_panel_source():
    print("\n[5] Окно слов: главная кнопка «Запись → Дальше → Готово»")
    body = read(os.path.join("ui", "panels", "vocab_panel.py"))
    check("подпись «Дальше» есть", "NEXT_TEXT = " in body)
    check("подпись «Готово ▶» есть", 'DONE_TEXT = "Готово  ▶"' in body, "нет DONE_TEXT")
    check("есть переключение главной кнопки", "def _set_main(self, mode" in body)
    check("после верного ответа главная кнопка = «Дальше»",
          'self._set_main("done" if self._at_last() else "next")' in body)
    check("последнее слово → «Готово»", "def _at_last(self)" in body,
          "нет _at_last")
    check("нижняя «Дальше» прячется в заходе", "def _hide_next_button(self)" in body)
    check("прошлый режим кнопок убран", "_set_answer_buttons" not in body,
          "остался _set_answer_buttons")
    check("нажатие главной кнопки листает слово",
          'if self._main_mode != "record":' in body)
    check("отпускание после «Дальше» не пишет звук",
          "self._skip_release" in body)
    check("похвала берётся из набора", "self._lines.praise()" in body)
    check("подбадривание берётся из набора", "self._lines.maybe_motivate()" in body)
    check("старое жёсткое «Good!» убрано", 'self._on_say("Good!")' not in body)


# =========================================================
# 5b. «Слов нет» и «свободное общение»
# =========================================================
def test_empty_and_free():
    print("\n[5b] Фраза «слов нет» и кнопка «Свободное общение»")
    first = vocab_lines.pick_empty()
    check("фраза из EMPTY_LINES", first in vocab_lines.EMPTY_LINES, first)
    same = [vocab_lines.pick_empty(first) for _ in range(20)]
    check("«слов нет» не повторяется подряд", first not in same, first)

    free = vocab_lines.pick_free()
    check("фраза из FREE_LINES", free in vocab_lines.FREE_LINES, free)
    same_free = [vocab_lines.pick_free(free) for _ in range(20)]
    check("«свободное общение» не повторяется подряд", free not in same_free, free)

    body = read(os.path.join("ui", "app.py"))
    check("есть фраза «слов нет» вместо пустого окна",
          "def _say_words_empty(self)" in body)
    check("фраза берётся из набора", "vocab_lines.pick_empty(" in body)
    check("старое объяснение про переводчик убрано", "_vocab_empty_note" not in body)
    check("окно не открывается, если слов нет", "self.vocab.has_material(on_demand=True)" in body)

    panel = read(os.path.join("ui", "panels", "vocab_panel.py"))
    check("у окна больше нет empty_text", "empty_text" not in panel)
    check("окно не объясняет лестницу повторов",
          "1 → 3 → 7 → 21" not in panel.split("def _show_empty")[1][:900]
          if "def _show_empty" in panel else False)


# =========================================================
# 6. Приложение: ответ голосом ДО окна
# =========================================================
def test_app_source():
    print("\n[6] Приложение: сначала фраза, потом окно")
    body = read(os.path.join("ui", "app.py"))
    check("есть открытие окна после речи", "def _open_words_after(self" in body)
    check("фраза берётся из набора", "vocab_lines.pick_open(" in body)
    check("окно открывается по концу озвучки", "self._say(line, on_done=_later)" in body)
    check("страховочный таймер из config",
          'getattr(config, "VOCAB_OPEN_GUARD_MS"' in body)
    start = body.find("    def _open_words_after(self")
    chunk = body[start:start + 1600] if start >= 0 else ""
    check("окно открывается РОВНО один раз", 'state["opened"]' in chunk, chunk[:60])
    old = body.find('"📚 Открываю слова: 5 новых')
    check("старая русская приписка убрана", old < 0, old)


def main():
    print("=" * 60)
    test_sets()
    test_open()
    test_praise()
    test_motivate()
    test_panel_source()
    test_empty_and_free()
    test_app_source()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛОВ: %d" % len(FAILED))
        for name in FAILED:
            print("  \u274c %s" % name)
    else:
        print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
