# -*- coding: utf-8 -*-
# =========================================================
# TEST_VOCAB_THEME.PY — слова по темам и смесь захода (решение 54)
# =========================================================
# Что проверяем:
#   1) банк слов: чтение файла уровня, пропуск битых строк, нет файла;
#   2) уровень ученика: из теста уровня, иначе из config.VOCAB_LEVEL;
#   3) текущая тема = первый НЕсданный блок уровня (проверка сдана = passed);
#   4) pick_mix: 5 новых + 3 текущей темы + 1 прошлой + 1 «трудное»;
#   5) пустая корзина место не теряет, дубликатов нет, новые — в конце;
#   6) норма новых слов в день: заведённые сегодня вычитаются;
#   7) контроллер: слова из банка пишутся в профиль, окно их показывает;
#   8) защита: подделка профиля без записи карточек новых слов не заводит.
# =========================================================

import os
import sys
import json
import tempfile
from datetime import date

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import config
import vocabulary
import word_bank
from controllers.vocabulary_controller import VocabularyController

FAILED = []
D0 = date(2026, 10, 27)


def check(name, ok, detail=None):
    if ok:
        print("  \u2705 %s" % name)
    else:
        print("  \u274c %s  \u2192  %s" % (name, detail))
        FAILED.append(name)


# ---------------------------------------------------------
# Подделки: карта курса, профиль, хранилище
# ---------------------------------------------------------
class FakeMap:
    """Карта курса: две локации A2 и одна A1 (ниже уровня — не считаем)."""

    def __init__(self):
        self._locs = {
            "easy": {"level": "A1", "points": [("easy/point_1", 1, "Easy Stuff")]},
            "city": {"level": "A2", "points": [("city/point_1", 1, "Making Arrangements"),
                                               ("city/point_2", 2, "At the Restaurant")]},
        }

    def level_rank(self, level):
        order = ("A0", "A1", "A2", "B1", "B2", "C1")
        name = str(level or "").strip().upper()
        return order.index(name) if name in order else -1

    def location_ids(self):
        return ["easy", "city"]

    def get_location(self, loc_id):
        return {"level": self._locs[loc_id]["level"]}

    def points_of(self, loc_id):
        return [{"id": pid, "number": num, "block_title": title}
                for pid, num, title in self._locs[loc_id]["points"]]

    def get_point(self, point_id):
        for loc in self._locs.values():
            for pid, num, title in loc["points"]:
                if pid == point_id:
                    return {"id": pid, "number": num, "block_title": title}
        return {}

    def lessons_of(self, point_id):
        code = point_id.split("_")[-1]
        prefix = point_id.rsplit("/point_", 1)[0]
        return [{"id": "%s/%s.1" % (prefix, code), "type": "speaking"},
                {"id": "%s/%s.4" % (prefix, code), "type": "check"}]


class FakeStore:
    """Профиль-подделка: карточки + «сданные» экзамены, без файлов."""

    def __init__(self, cards=None, profile=None, can_save=True):
        self.cards = list(cards or [])
        self.profile = dict(profile or {})
        if not can_save:
            # стор без умения сохранять карточки: банк должен молчать
            self.add_vocabulary_cards = None

    def load(self, user_id=None):
        return self.profile

    def vocabulary_cards(self, user_id=None):
        return self.cards

    def add_vocabulary_cards(self, cards, user_id=None):
        for card in cards or []:
            self.cards.append(dict(card))
        return list(cards or [])

    def update_vocabulary_card(self, word, en, success, user_id=None):
        for card in self.cards:
            if card.get("word") == word and card.get("en") == en:
                if success:
                    card["level"] = min(vocabulary.LEARNED, vocabulary.level_of(card) + 1)
                else:
                    card["misses"] = int(card.get("misses") or 0) + 1
                return card
        return None

    def mark_vocab_session(self, user_id=None):
        return "2026-10-27"


def make_card(word, en, level=1, theme="", misses=0, created="2026-10-20", due="2026-10-27"):
    card = vocabulary.new_card(word, en, "Example with %s." % en, today=created)
    card["level"] = level
    card["theme"] = theme
    card["misses"] = misses
    card["next_due"] = due
    return card


def fresh(level, theme, ru, en, example=""):
    return vocabulary.card_for_word(
        {"ru": ru, "en": en, "example": example, "theme": theme}, D0)


# =========================================================
# 1. Банк слов
# =========================================================
def test_bank():
    print("\n[1] Банк слов: чтение, битые строки, нет файла")
    bank = word_bank.load("A2")
    words = word_bank.words_of_theme("A2", "city/point_1")
    check("банк A2 прочитан", bool(bank.get("themes")), list(bank.get("themes"))[:3])
    check("тема city/point_1 не пустая", len(words) >= 10, len(words))
    check("слово содержит ru/en/example/theme",
          all(w.get("ru") and w.get("en") and w.get("theme") == "city/point_1"
              for w in words), words[:1])

    tmp = tempfile.mkdtemp(prefix="et_bank_")
    path = os.path.join(tmp, "words_c1.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"level": "C1", "themes": {
            "sky/point_1": [{"ru": "хороший", "en": "good", "example": "Good day."},
                            {"ru": "плохой"},
                            "мусор",
                            {"en": "only english"}]}}, fh, ensure_ascii=False)
    word_bank.forget("C1", tmp)
    parsed = word_bank.words_of_theme("C1", "sky/point_1", path=tmp)
    check("битые строки отброшены", len(parsed) == 1, parsed)
    check("тема подставлена из ключа", parsed and parsed[0]["theme"] == "sky/point_1", parsed)
    word_bank.forget("C1", tmp)

    empty = word_bank.words_of_theme("B2", "ruins/point_1", path=tempfile.mkdtemp(prefix="et_none_"))
    check("нет файла → пустой список, без падения", empty == [], empty)


# =========================================================
# 2. Уровень ученика
# =========================================================
def test_level():
    print("\n[2] Уровень ученика")
    check("из теста уровня (последний)",
          word_bank.student_level({"level_tests": [{"level": "A1"}, {"level": "A2"}]}) == "A2",
          word_bank.student_level({"level_tests": [{"level": "A2"}]}))
    check("нет тестов → A2 по умолчанию", word_bank.student_level({}) == "A2",
          word_bank.student_level({}))
    old = getattr(config, "VOCAB_LEVEL", "")
    config.VOCAB_LEVEL = "B1"
    try:
        check("config.VOCAB_LEVEL сильнее профиля",
              word_bank.student_level({"level_tests": [{"level": "A2"}]}) == "B1",
              word_bank.student_level({"level_tests": [{"level": "A2"}]}))
    finally:
        config.VOCAB_LEVEL = old


# =========================================================
# 3. Текущая тема
# =========================================================
def test_theme():
    print("\n[3] Текущая тема: первый несданный блок уровня")
    wordmap = FakeMap()
    check("без профиля — первый блок своего уровня",
          word_bank.current_theme({}, wordmap, "A2") == "city/point_1",
          word_bank.current_theme({}, wordmap, "A2"))
    passed = {"exams": {"city/1.4": {"score": 8.0, "passed": True}}}
    check("проверка сдана → следующая тема",
          word_bank.current_theme(passed, wordmap, "A2") == "city/point_2",
          word_bank.current_theme(passed, wordmap, "A2"))
    failed = {"exams": {"city/1.4": {"score": 3.0, "passed": False}}}
    check("проверка не сдана → та же тема",
          word_bank.current_theme(failed, wordmap, "A2") == "city/point_1",
          word_bank.current_theme(failed, wordmap, "A2"))
    check("локация ниже уровня не берётся",
          word_bank.current_theme({}, wordmap, "A2") != "easy/point_1",
          word_bank.current_theme({}, wordmap, "A2"))
    both = {"exams": {"city/1.4": {"passed": True}, "city/2.4": {"passed": True}}}
    check("всё сдано → пустая тема", word_bank.current_theme(both, wordmap, "A2") == "",
          word_bank.current_theme(both, wordmap, "A2"))
    check("название блока для интерфейса",
          word_bank.theme_label(wordmap, "city/point_1") == "1. Making Arrangements",
          word_bank.theme_label(wordmap, "city/point_1"))


# =========================================================
# 4. Смесь захода
# =========================================================
def test_mix():
    print("\n[4] pick_mix: 5 новых + 3 темы + 1 прошлое + 1 трудное")
    theme = "city/point_1"
    cards = [make_card("слово%d" % i, "word%d" % i, theme=theme) for i in range(5)]
    cards += [make_card("старое%d" % i, "old%d" % i, theme="desert/point_1") for i in range(3)]
    cards += [make_card("трудное", "hard", theme="desert/point_2", misses=3)]
    bank = [fresh(theme, theme, "новое%d" % i, "fresh%d" % i) for i in range(7)]

    queue, new = vocabulary.pick_mix(cards, bank, theme=theme, today=D0, new_limit=5)
    check("новых ровно 5", len(new) == 5, len(new))
    check("всего 10 слов", len(queue) == 10, len(queue))
    kinds = {"new": 0, "theme": 0, "passed": 0, "hard": 0}
    for card in queue:
        if card in new:
            kinds["new"] += 1
        elif card.get("word") == "трудное":
            kinds["hard"] += 1
        elif card.get("theme") == theme:
            kinds["theme"] += 1
        else:
            kinds["passed"] += 1
    check("раскладка 5/3/1/1",
          kinds == {"new": 5, "theme": 3, "passed": 1, "hard": 1}, kinds)
    check("новые стоят в конце очереди", queue[-1] in new, queue[-1].get("word"))

    # без банка: только повторы, дубликатов нет
    queue2, new2 = vocabulary.pick_mix(cards, [], theme=theme, today=D0, new_limit=5)
    words = [c.get("word") for c in queue2]
    check("без банка новых нет", new2 == [], new2)
    check("дубликатов в очереди нет", len(words) == len(set(words)), words)

    # пустая корзина «трудных» — место добирается другими
    plain = [make_card("слово%d" % i, "word%d" % i, theme=theme) for i in range(6)]
    queue3, _ = vocabulary.pick_mix(plain, [], theme=theme, today=D0)
    check("пустая корзина добирается другими", len(queue3) == len(set(
        c.get("word") for c in queue3)) and len(queue3) >= 3, len(queue3))

    # уже заведённое слово второй раз не добавляется
    have = [make_card("встречаться", "meet", theme=theme)]
    cand = [fresh(theme, theme, "встречаться", "meet")]
    _, new3 = vocabulary.pick_mix(have, cand, theme=theme, today=D0)
    check("дубликат из банка не заводится заново", new3 == [], new3)


# =========================================================
# 5. Норма новых слов в день
# =========================================================
def test_daily_norm():
    print("\n[5] Норма новых слов в день")
    theme = "city/point_1"
    today_card = fresh(theme, theme, "утро", "morning")
    old_card = fresh(theme, theme, "вечер", "evening")
    old_card["created"] = "2026-10-20"
    check("заведённые сегодня посчитаны", vocabulary.created_today([today_card, old_card], D0) == 1,
          vocabulary.created_today([today_card, old_card], D0))
    check("норма из config", vocabulary.new_per_day() == config.VOCAB_NEW_PER_DAY,
          (vocabulary.new_per_day(), config.VOCAB_NEW_PER_DAY))
    left = max(0, vocabulary.new_per_day() - vocabulary.created_today([today_card] * 5, D0))
    check("норма вычитается до нуля", left == max(0, config.VOCAB_NEW_PER_DAY - 5), left)


# =========================================================
# 6. Контроллер: слова из банка попадают в заход и в профиль
# =========================================================
def test_controller_bank():
    print("\n[6] Контроллер: новые слова темы в заходе и в профиле")
    import controllers.vocabulary_controller as vc
    saved = vc._WORD_MAP
    vc._WORD_MAP = FakeMap()
    try:
        store = FakeStore(profile={"level_tests": [{"level": "A2"}]})
        ctrl = VocabularyController(store=store, today=D0)
        queue = ctrl.start()
        check("заход собрался", len(queue) == 5, len(queue))
        check("тема найдена", ctrl.theme == "city/point_1", ctrl.theme)
        check("новые слова записаны в профиль",
              len([c for c in store.cards if c.get("source") == "bank"]) == 5,
              len(store.cards))
        check("у новых есть тема",
              all(c.get("theme") == "city/point_1" for c in store.cards), store.cards[:1])
        check("в окне помечены как новые",
              sum(1 for item in queue if item.get("is_new")) == 5, queue[:1])
        check("счётчик новых в итоге захода", ctrl.summary().get("new") == 5, ctrl.summary())

        # второй заход в тот же день новых не даёт
        ctrl2 = VocabularyController(store=store, today=D0)
        queue2 = ctrl2.start()
        check("норма дня уже израсходована", ctrl2.summary().get("new") == 0, ctrl2.summary())
        check("второй заход без новых", all(not item.get("is_new") for item in queue2),
              [item.get("word") for item in queue2])
    finally:
        vc._WORD_MAP = saved


def test_controller_guard():
    print("\n[7] Защита: подделка профиля без записи карточек")
    import controllers.vocabulary_controller as vc
    saved = vc._WORD_MAP
    vc._WORD_MAP = FakeMap()
    try:
        store = FakeStore(profile={"level_tests": [{"level": "A2"}]}, can_save=False)
        ctrl = VocabularyController(store=store, today=D0)
        queue = ctrl.start()
        check("новых не завели", ctrl.summary().get("new") == 0, ctrl.summary())
        check("заход пуст (повторять нечего)", queue == [], queue)
        check("материала нет", ctrl.has_material() is False, ctrl.has_material())

        store2 = FakeStore(profile={"level_tests": [{"level": "A2"}]})
        ctrl2 = VocabularyController(store=store2, today=D0)
        check("с рабочим стором материал есть", ctrl2.has_material() is True,
              ctrl2.has_material())
    finally:
        vc._WORD_MAP = saved


def main():
    print("=" * 60)
    test_bank()
    test_level()
    test_theme()
    test_mix()
    test_daily_norm()
    test_controller_bank()
    test_controller_guard()
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
