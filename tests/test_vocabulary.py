# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_VOCABULARY.PY — карточки слов (интервальное повторение)
# =========================================================
#   python tests\test_vocabulary.py   (окно НЕ создаётся, файлов в профиле нет)
#
# Проверяем:
#   1) разбор строки переводчика «key — пример»;
#   2) автозапись: все три значения → три карточки, дубликатов нет;
#   3) лестницу уровней 0→1→2→3→4→5 и даты 1/3/7/21 день;
#   4) промах: уровень НЕ меняется (решение 53), спросить завтра;
#   5) выученное слово не спрашиваем и не сбрасываем;
#   6) «что спросить сегодня»: только созревшие, порядок, лимит 5;
#   7) сводку для вкладки «Профиль»;
#   8) запись в файл прогресса: карточки есть, total_lessons НЕ растёт;
#   9) битые данные не ломают работу.
# =========================================================

import json
import os
import sys
import tempfile
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config      # noqa: E402
import vocabulary  # noqa: E402

FAILED = []

# Даты-«стенд»: слова в тестах живут всегда на одной и той же неделе.
D0 = date(2026, 10, 18)


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


# =========================================================
# 1. Разбор строки переводчика
# =========================================================
def test_parse():
    print("\n[1] Разбор строки переводчика")
    parsed = vocabulary.parse_line("key \u2014 Open the door with this key.")
    check("значение и пример разделены",
          parsed == ("key", "Open the door with this key."), parsed)
    parsed = vocabulary.parse_line("wrench \u2014 He fixed the car with a wrench.")
    check("второе значение тоже читается", parsed[0] == "wrench", parsed)
    parsed = vocabulary.parse_line("1. clef - The clef is on the staff.")
    check("нумерация убрана", parsed and parsed[0] == "clef", parsed)
    parsed = vocabulary.parse_line("key: Open the door with this key.")
    check("двоеточие тоже годится", parsed and parsed[0] == "key", parsed)
    parsed = vocabulary.parse_line("  \"key\"  ")
    check("слово без примера", parsed == ("key", ""), parsed)
    check("кириллица — не перевод", vocabulary.parse_line("key — дверной ключ") is None)
    check("пустая строка — None", vocabulary.parse_line("") is None
          and vocabulary.parse_line(None) is None)
    check("кавычки-«ёлочки» убираются",
          vocabulary.parse_line("\u201ckey\u201d") == ("key", ""),
          vocabulary.parse_line("\u201ckey\u201d"))

    meanings = vocabulary.parse_meanings([
        "key \u2014 Open the door with this key.",
        "wrench \u2014 He fixed the car with a wrench.",
        "key \u2014 Open the door with this key.",     # дубль внутри ответа
        "1. clef \u2014 The clef is on the staff.",
    ])
    check("три значения, дубль отброшен", len(meanings) == 3, meanings)
    check("порядок сохранён (частые — первыми)", meanings[0]["en"] == "key", meanings)


# =========================================================
# 2. Автозапись карточек
# =========================================================
def test_add():
    print("\n[2] Автозапись: все значения слова, без дубликатов")
    cards = []
    added = vocabulary.add_meanings(cards, "ключ", [
        "key \u2014 Open the door with this key.",
        "wrench \u2014 He fixed the car with a wrench.",
        "clef \u2014 The clef is on the staff.",
    ], today=D0)
    check("все три значения → три карточки", len(added) == 3 and len(cards) == 3, len(cards))
    check("у карточки есть пример", cards[0]["example"].startswith("Open"), cards[0])
    check("уровень новой карточки 0", cards[0]["level"] == 0, cards[0])
    check("новую можно спросить уже сегодня",
          cards[0]["next_due"] == "2026-10-18", cards[0]["next_due"])
    check("русское слово сохранено", cards[0]["word"] == "ключ", cards[0]["word"])

    added2 = vocabulary.add_meanings(cards, "ключ", [
        "key \u2014 Another example of the same meaning.",
    ], today=D0)
    check("повторный перевод ничего не добавил", added2 == [] and len(cards) == 3, len(cards))

    added3 = vocabulary.add_meanings(cards, "ключ", [
        "KEY \u2014 Uppercase is the same word.",
    ], today=D0)
    check("регистр не создаёт дубль", added3 == [], added3)

    added4 = vocabulary.add_meanings(cards, "замок", [
        "lock \u2014 The lock is broken.",
    ], today=D0)
    check("другое слово — новые карточки", len(added4) == 1 and len(cards) == 4, len(cards))

    check("поиск карточки работает",
          vocabulary.find_card(cards, "ключ", "wrench") is not None)
    check("поиск другой формы тоже", vocabulary.find_card(cards, "Ключ", "KEY") is not None)
    check("нет такой карточки → None", vocabulary.find_card(cards, "ключ", "dog") is None)


# =========================================================
# 3. Лестница вверх
# =========================================================
def test_ladder_up():
    print("\n[3] Лестница 0 → 1 → 2 → 3 → 4 → 5 (1/3/7/21 день)")
    card = vocabulary.new_card("ключ", "key", "Open the door.", today=D0)
    steps = [(1, "2026-10-19"), (2, "2026-10-21"), (3, "2026-10-25"),
             (4, "2026-11-08"), (5, None)]
    for level, due in steps:
        vocabulary.register_success(card, today=D0)
        check("уровень стал %d" % level, card["level"] == level, card["level"])
        check("  дата вопроса %s" % (due or "больше не спрашиваем"),
              card["next_due"] == due, card["next_due"])
    check("выучено = уровень 5", vocabulary.is_learned(card) is True)
    check("успехов насчитано 5", card["hits"] == 5, card["hits"])
    vocabulary.register_success(card, today=D0)
    check("выше 5 уровень не растёт", card["level"] == 5, card["level"])
    check("next_due остаётся пустым", card["next_due"] is None, card["next_due"])
    check("даты ступеней в config-логике прямые: 1/3/7/21",
          vocabulary.INTERVALS_DAYS == (0, 1, 3, 7, 21, None), vocabulary.INTERVALS_DAYS)


# =========================================================
# 4. Промах
# =========================================================
def test_miss():
    print("\n[4] Промах: уровень НЕ меняется (решение 53), спросить завтра")
    card = vocabulary.new_card("ключ", "key", "Open the door.", today=D0)
    card["level"] = 3
    vocabulary.register_miss(card, today=D0)
    check("уровень 3 остался 3 (промах не понижает)", card["level"] == 3, card["level"])
    check("спросить завтра", card["next_due"] == "2026-10-19", card["next_due"])
    check("промахов 1", card["misses"] == 1, card["misses"])
    card["level"] = 0
    vocabulary.register_miss(card, today=D0)
    check("с нуля ниже не падает", card["level"] == 0, card["level"])
    check("промахов 2", card["misses"] == 2, card["misses"])
    card["level"] = 5
    vocabulary.register_miss(card, today=D0)
    check("выученное промах не разучивает", card["level"] == 5, card["level"])


# =========================================================
# 5. Выученное слово
# =========================================================
def test_learned():
    print("\n[5] Выученное слово не спрашиваем и не сбрасываем")
    cards = []
    vocabulary.add_meanings(cards, "ключ", ["key \u2014 Open the door."], today=D0)
    card = cards[0]
    card["level"] = 5
    card["next_due"] = None
    added = vocabulary.add_meanings(cards, "ключ", ["key \u2014 Open the door."], today=D0)
    check("повторный перевод не создал карточку", added == [], added)
    check("выученное осталось на уровне 5", card["level"] == 5, card["level"])
    check("и не попало в вопросы", vocabulary.due_cards(cards, today=D0) == [],
          vocabulary.due_cards(cards, today=D0))


# =========================================================
# 6. Что спросить сегодня
# =========================================================
def test_due():
    print("\n[6] Что спросить сегодня: только созревшие, лимит 5")
    cards = []
    for word, en in [("ключ", "key"), ("гайка", "nut"), ("дверь", "door"),
                     ("окно", "window"), ("стол", "table"), ("стул", "chair")]:
        vocabulary.add_meanings(cards, word, ["%s \u2014 A simple example." % en], today=D0)
    check("все шесть новых — на сегодня",
          len(vocabulary.due_cards(cards, today=D0, limit=0)) == 6,
          len(vocabulary.due_cards(cards, today=D0, limit=0)))
    session = vocabulary.due_cards(cards, today=D0)
    check("за заход берём 5 слов", len(session) == 5, len(session))
    check("лимит берётся из config (VOCAB_SESSION_SIZE = 5)",
          config.VOCAB_SESSION_SIZE == vocabulary.session_size() == 5,
          (config.VOCAB_SESSION_SIZE, vocabulary.session_size()))

    cards[0]["next_due"] = "2026-10-17"      # просрочено на день
    cards[1]["next_due"] = "2026-11-01"      # ещё рано
    out = vocabulary.due_cards(cards, today=D0, limit=10)
    check("просроченное спрашиваем первым", out and out[0] is cards[0], out[:1])
    check("не созревшее не спрашиваем", cards[1] not in out, [c["en"] for c in out])
    check("всего к повторению 5", len(out) == 5, len(out))

    session = vocabulary.due_cards(cards, today=D0, limit=2)
    check("limit=2 уважается", len(session) == 2, len(session))
    check("пустой список не падает",
          vocabulary.due_cards([], today=D0) == []
          and vocabulary.due_cards(None, today=D0) == [])


# =========================================================
# 7. Сводка
# =========================================================
def test_stats():
    print("\n[7] Сводка для вкладки «Профиль»")
    cards = []
    vocabulary.add_meanings(cards, "ключ", ["key \u2014 Open the door.",
                                          "wrench \u2014 He fixed the car."], today=D0)
    vocabulary.add_meanings(cards, "дверь", ["door \u2014 Close the door."], today=D0)
    cards[0]["level"] = 5
    cards[0]["next_due"] = None
    cards[1]["next_due"] = "2026-12-01"
    s = vocabulary.stats(cards, today=D0)
    check("всего 3", s["total"] == 3, s)
    check("выучено 1", s["learned"] == 1, s)
    check("в учёбе 2", s["learning"] == 2, s)
    check("к повторению 1 (только созревшее)", s["due"] == 1, s)


# =========================================================
# 8. Файл прогресса (profile_store)
# =========================================================
class temp_profile:
    """Временный файл прогресса: настоящий профиль ученика не трогаем."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_vocab_")
        import profile_store
        self.ps = profile_store
        self.real_path = profile_store.PROFILE_PATH
        profile_store.PROFILE_PATH = os.path.join(self.dir, "student_profile.json")
        profile_store.set_active_user(None)
        return profile_store.PROFILE_PATH

    def __exit__(self, *exc):
        self.ps.PROFILE_PATH = self.real_path


def test_store():
    print("\n[8] Запись в файл прогресса (рядом с ошибками)")
    import profile_store
    with temp_profile():
        path = profile_store.PROFILE_PATH
        profile_store.ensure_profile()
        before = profile_store.load().get("total_lessons", 0)

        added = profile_store.add_vocabulary("ключ", [
            "key \u2014 Open the door with this key.",
            "wrench \u2014 He fixed the car with a wrench.",
        ])
        check("две карточки записаны", len(added) == 2, len(added))
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        check("ключ vocabulary в файле есть", isinstance(raw.get("vocabulary"), list)
              and len(raw["vocabulary"]) == 2, raw.get("vocabulary"))
        check("слово и значение в файле",
              raw["vocabulary"][0]["word"] == "ключ"
              and raw["vocabulary"][0]["en"] == "key", raw["vocabulary"][0])
        check("total_lessons НЕ вырос (это не занятие)",
              raw.get("total_lessons", 0) == before, (before, raw.get("total_lessons")))

        again = profile_store.add_vocabulary("ключ", ["key \u2014 Open the door."])
        check("повторный перевод — без новых карточек", again == [], again)
        check("и в файле по-прежнему 2", len(profile_store.vocabulary_cards()) == 2,
              len(profile_store.vocabulary_cards()))

        card = profile_store.update_vocabulary_card("ключ", "key", True)
        check("успех: уровень 1", card and card["level"] == 1, card)
        check("и это видно в файле",
              profile_store.vocabulary_cards()[0]["level"] == 1,
              profile_store.vocabulary_cards()[0])
        card = profile_store.update_vocabulary_card("ключ", "key", False)
        check("промах: уровень остался 1", card and card["level"] == 1, card)
        check("чужой карточки нет → None",
              profile_store.update_vocabulary_card("ключ", "dog", True) is None)
        check("файл по-прежнему читается",
              profile_store.load().get("vocabulary") is not None)


def test_migration():
    print("\n[9] Старый профиль без карточек и битые данные")
    import profile_store
    with temp_profile():
        path = profile_store.PROFILE_PATH
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"student_name": "Старый", "total_lessons": 3}, fh, ensure_ascii=False)
        check("старый профиль читается", profile_store.vocabulary_cards() == [],
              profile_store.vocabulary_cards())
        added = profile_store.add_vocabulary("дверь", ["door \u2014 Open the door."])
        check("карточка добавилась в старый профиль", len(added) == 1, added)

        cards = [None, 42, {"en": "key", "level": "abc"}, {"word": "x"}]
        check("битый уровень → 0", vocabulary.level_of(cards[2]) == 0, cards[2])
        check("битые записи не роняют сводку", vocabulary.stats(cards)["total"] == 2,
              vocabulary.stats(cards))
        check("без next_due — «давно пора»",
              len(vocabulary.due_cards([{"word": "x", "en": "y", "level": 0}], today=D0)) == 1)
        check("next_due мусором — не падает",
              len(vocabulary.due_cards([{"word": "x", "en": "y", "next_due": "когда-то"}],
                                       today=D0)) == 1)


def main():
    print("=" * 60)
    print("Проверка карточек слов (vocabulary.py + profile_store)")
    print("=" * 60)
    test_parse()
    test_add()
    test_ladder_up()
    test_miss()
    test_learned()
    test_due()
    test_stats()
    test_store()
    test_migration()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
