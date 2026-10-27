# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_VOCAB_REVIEW.PY — окно «Повторение» (этап B)
# =========================================================
#   python tests\test_vocab_review.py   (окно НЕ создаётся, микрофон не нужен)
#
# Проверяем логику БЕЗ интерфейса (controllers/vocabulary_controller.py):
#   1) пример с пропуском («Open the door with this ___.»);
#   2) эталоны для сверки (пример и само слово);
#   3) «сегодня уже было?» (дата захода в профиле);
#   4) сборку захода: до 5 созревших слов, порядок, пустой заход;
#   5) ответы: удачный +1, промах уровень не двигает (решение 53);
#   6) ОДИН итог на карточку за заход (повтор не двигает уровень);
#   7) подсказка = промах, «Позже» — без изменений;
#   8) отметку даты захода в файле прогресса (total_lessons не растёт);
#   9) битые данные и отсутствующая карточка не ломают заход.
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

import config                                              # noqa: E402
import vocabulary                                          # noqa: E402
from controllers.vocabulary_controller import VocabularyController  # noqa: E402

FAILED = []

D0 = date(2026, 10, 18)


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeStore:
    """Подделка файла прогресса: карточки живут в памяти."""

    def __init__(self, cards=None):
        self.cards = cards if cards is not None else []
        self.marks = 0
        self.updates = []

    def vocabulary_cards(self, user_id=None):
        return self.cards

    def update_vocabulary_card(self, word, en, success, user_id=None):
        card = vocabulary.find_card(self.cards, word, en)
        if card is None:
            return None
        if success:
            vocabulary.register_success(card, today=D0)
        else:
            vocabulary.register_miss(card, today=D0)
        self.updates.append((word, en, success))
        return card

    def mark_vocab_session(self, day=None, user_id=None):
        self.marks += 1
        return "2026-10-18"


def make_cards(pairs):
    """[(русское, английское, пример), …] → список карточек на сегодня."""
    cards = []
    for word, en, example in pairs:
        vocabulary.add_meanings(cards, word, ["%s \u2014 %s" % (en, example)], today=D0)
    return cards


# =========================================================
# 1. Пример с пропуском
# =========================================================
def test_gap():
    print("\n[1] Пример с пропуском вместо слова")
    card = vocabulary.new_card("ключ", "key", "Open the door with this key.", today=D0)
    check("слово заменено пропуском",
          vocabulary.example_with_gap(card) == "Open the door with this ___.",
          vocabulary.example_with_gap(card))
    card = vocabulary.new_card("нога", "foot", "My foot hurts.", today=D0)
    check("короткий пример тоже работает",
          vocabulary.example_with_gap(card) == "My ___ hurts.")
    card = vocabulary.new_card("ключи", "key", "Where are the keys?", today=D0)
    check("форма с -s находится", vocabulary.example_with_gap(card) == "Where are the ___?",
          vocabulary.example_with_gap(card))
    card = vocabulary.new_card("играть", "play", "She played all day.", today=D0)
    check("форма с -ed находится", vocabulary.example_with_gap(card) == "She ___ all day.",
          vocabulary.example_with_gap(card))
    card = vocabulary.new_card("ключ", "key", "No such word here.", today=D0)
    check("слова нет в примере → пусто (не выдумываем)",
          vocabulary.example_with_gap(card) == "", vocabulary.example_with_gap(card))
    check("примера нет → пусто",
          vocabulary.example_with_gap({"en": "key", "example": ""}) == "")
    check("битая карточка не роняет",
          vocabulary.example_with_gap(None) == "" and example_ok())

    multi = vocabulary.new_card("искать", "look for", "I look for my keys.", today=D0)
    check("значение из двух слов заменяется целиком",
          vocabulary.example_with_gap(multi) == "I ___ my keys.",
          vocabulary.example_with_gap(multi))
    check("часть слова не съедается (key в keyhole — не совпадение)",
          example_ok(), vocabulary.example_with_gap(
              vocabulary.new_card("ключ", "key", "The keyhole is small.", today=D0)))


def example_ok():
    """Проверка «часть слова не съедается»: key не должен найтись в keyhole."""
    card = vocabulary.new_card("ключ", "key", "The keyhole is small.", today=D0)
    return vocabulary.example_with_gap(card) == ""


# =========================================================
# 2. Эталоны
# =========================================================
def test_references():
    print("\n[2] С чем сверяем произношение")
    card = vocabulary.new_card("ключ", "key", "Open the door with this key.", today=D0)
    refs = vocabulary.reference_texts(card)
    check("эталонов два: пример и слово",
          refs == ["Open the door with this key.", "key"], refs)
    card = vocabulary.new_card("ключ", "key", "", today=D0)
    check("без примера — только слово", vocabulary.reference_texts(card) == ["key"])
    check("пустая карточка → пусто", vocabulary.reference_texts({}) == [])


# =========================================================
# 3. «Сегодня уже было?»
# =========================================================
def test_session_day():
    print("\n[3] Не чаще раза в день")
    check("сегодня — было", vocabulary.session_today("2026-10-18", today=D0) is True)
    check("вчера — не было", vocabulary.session_today("2026-10-17", today=D0) is False)
    check("пусто — не было", vocabulary.session_today("", today=D0) is False)
    check("мусор — не было", vocabulary.session_today("когда-то", today=D0) is False)
    check("None — не было", vocabulary.session_today(None, today=D0) is False)


# =========================================================
# 4. Сборка захода
# =========================================================
def test_session():
    print("\n[3] Заход: все созревшие слова (не больше лимита)")
    cards = make_cards([("ключ", "key", "Open the door with this key."),
                        ("гайка", "nut", "A small nut."),
                        ("дверь", "door", "Close the door."),
                        ("окно", "window", "Open the window."),
                        ("стол", "table", "The table is big."),
                        ("стул", "chair", "Sit on the chair.")])
    store = FakeStore(cards)
    ctrl = VocabularyController(store=store, today=D0)
    queue = ctrl.start()
    check("в заходе все 6 созревших", len(queue) == 6 and ctrl.total == 6, len(queue))
    check("текущее слово есть", ctrl.current() and ctrl.current()["word"] == "ключ",
          ctrl.current())
    check("номер слова 1", ctrl.position == 1, ctrl.position)
    check("пропуск посчитан заранее",
          ctrl.current()["gap"] == "Open the door with this ___.", ctrl.current())
    check("в очереди есть уровень", "level" in ctrl.current())

    # «Позже» двигает очередь
    ctrl.next()
    check("следующее слово — второе", ctrl.position == 2 and ctrl.current()["word"] == "гайка",
          ctrl.current())
    while ctrl.next():
        pass
    check("после последнего слова заход закончен", ctrl.is_active is False)
    check("итог: показано 6", ctrl.summary()["shown"] == 6, ctrl.summary())

    empty = VocabularyController(store=FakeStore([]), today=D0)
    check("пустой заход: очередь пуста", empty.start() == [] and empty.is_active is False)
    check("пустой заход: ответ не падает", empty.answer("key")["status"] == "no_card")

    early = make_cards([("ключ", "key", "Open the door.")])
    early[0]["next_due"] = "2026-11-01"          # ещё рано
    check("не созревшее в заход не берём",
          VocabularyController(store=FakeStore(early), today=D0).start() == [])

    late = make_cards([("ключ", "key", "Open the door."),
                       ("дверь", "door", "Close the door.")])
    late[1]["next_due"] = "2026-10-10"           # просрочено сильнее
    ctrl2 = VocabularyController(store=FakeStore(late), today=D0)
    ctrl2.start()
    check("просроченное спрашиваем первым", ctrl2.current()["word"] == "дверь",
          ctrl2.current())


# =========================================================
# 5. Ответы
# =========================================================
def test_answers():
    print("\n[5] Ответы: +1 за «Похоже», промах уровень не двигает")
    cards = make_cards([("ключ", "key", "Open the door with this key.")])
    store = FakeStore(cards)
    ctrl = VocabularyController(store=store, today=D0)
    ctrl.start()
    res = ctrl.answer("open the door with this key")
    check("вся фраза → вердикт good", res["status"] == "good", res)
    check("уровень 0 → 1", res["level_from"] == 0 and res["level_to"] == 1, res)
    check("уровень записан в файл", store.updates == [("ключ", "key", True)], store.updates)

    cards2 = make_cards([("ключ", "key", "Open the door with this key.")])
    ctrl2 = VocabularyController(store=FakeStore(cards2), today=D0)
    ctrl2.start()
    res = ctrl2.answer("key")
    check("одно слово «key» тоже good (сверяем и со словом)",
          res["status"] == "good", res)

    cards3 = make_cards([("ключ", "key", "Open the door with this key.")])
    cards3[0]["level"] = 3
    ctrl3 = VocabularyController(store=FakeStore(cards3), today=D0)
    ctrl3.start()
    res = ctrl3.answer("keys")
    check("«keys» вместо «key» → промах", res["status"] == "miss", res)
    check("уровень 3 остался 3", res["level_from"] == 3 and res["level_to"] == 3, res)
    check("вердикт «почти/попробуй»", res["verdict"] in ("almost", "off"), res["verdict"])

    cards4 = make_cards([("ключ", "key", "Open the door with this key.")])
    ctrl4 = VocabularyController(store=FakeStore(cards4), today=D0)
    ctrl4.start()
    res = ctrl4.answer("сегодня хорошая погода")
    check("по-русски — это не ответ", res["status"] == "russian", res)
    check("уровень не двинулся", ctrl4.current()["level"] == 0, ctrl4.current())

    res = ctrl4.answer("I had a wonderful vacation by the sea")
    check("сказал своё → unrelated", res["status"] == "unrelated", res)
    check("и уровень тоже не двинулся", ctrl4.current()["level"] == 0, ctrl4.current())

    cards5 = make_cards([("ключ", "key", "Open the door.")])
    ctrl5 = VocabularyController(store=FakeStore(cards5), today=D0)
    ctrl5.start()
    res = ctrl5.answer("key")
    check("уровень 0 → 1, выученным не стал", res["level_to"] == 1 and res["learned"] is False,
          res)

    cards6 = make_cards([("ключ", "key", "Open the door.")])
    cards6[0]["level"] = 4
    ctrl6 = VocabularyController(store=FakeStore(cards6), today=D0)
    ctrl6.start()
    res = ctrl6.answer("key")
    check("4 → 5: слово выучено", res["level_to"] == 5 and res["learned"] is True, res)


# =========================================================
# 6. Один итог на карточку
# =========================================================
def test_one_grade():
    print("\n[6] Один итог на карточку за заход")
    cards = make_cards([("ключ", "key", "Open the door with this key.")])
    cards[0]["level"] = 3
    store = FakeStore(cards)
    ctrl = VocabularyController(store=store, today=D0)
    ctrl.start()
    first = ctrl.answer("keys")           # промах: уровень не двигается
    check("первый промах записан, уровень 3 остался", first["level_to"] == 3 and first["changed"] is True,
          first)
    check("по карточке уже есть итог", ctrl.graded() is True)
    second = ctrl.answer("key")           # теперь верно — но уровень не растёт
    check("повторная удачная попытка уровень НЕ поднимает",
          second["changed"] is False and second["level_to"] == 3, second)
    check("и в файл второй раз не пишем", len(store.updates) == 1, store.updates)
    check("итог захода: промах 1, удачно 0",
          ctrl.summary()["miss"] == 1 and ctrl.summary()["good"] == 0, ctrl.summary())


# =========================================================
# 7. Подсказка и «Позже»
# =========================================================
def test_hint_and_skip():
    print("\n[7] Подсказка = промах, «Позже» — без изменений")
    cards = make_cards([("ключ", "key", "Open the door with this key.")])
    cards[0]["level"] = 2
    store = FakeStore(cards)
    ctrl = VocabularyController(store=store, today=D0)
    ctrl.start()
    res = ctrl.reveal()
    check("подсказка показала значение", res["status"] == "hint" and res["en"] == "key", res)
    check("подсказка уровень не снизила",
          res["level_from"] == 2 and res["level_to"] == 2, res)
    again = ctrl.answer("key")
    check("после подсказки можно повторить вслух без второго итога",
          again["changed"] is False and again["level_to"] == 2, again)

    cards2 = make_cards([("ключ", "key", "Open the door with this key.")])
    cards2[0]["level"] = 2
    store2 = FakeStore(cards2)
    ctrl2 = VocabularyController(store=store2, today=D0)
    ctrl2.start()
    skipped = ctrl2.skip()
    check("«Позже» вернуло карточку", skipped and skipped["word"] == "ключ", skipped)
    check("уровень не изменился", cards2[0]["level"] == 2, cards2[0]["level"])
    check("в файл ничего не писали", store2.updates == [], store2.updates)
    check("итог: пропущено 1", ctrl2.summary()["skipped"] == 1, ctrl2.summary())
    check("после «Позже» ответ уровень не двигает",
          ctrl2.answer("key")["changed"] is False, store2.updates)


# =========================================================
# 8. Файл прогресса
# =========================================================
class temp_profile:
    """Временный файл прогресса: настоящий профиль ученика не трогаем."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_review_")
        import profile_store
        self.ps = profile_store
        self.real_path = profile_store.PROFILE_PATH
        profile_store.PROFILE_PATH = os.path.join(self.dir, "student_profile.json")
        profile_store.set_active_user(None)
        return profile_store.PROFILE_PATH

    def __exit__(self, *exc):
        self.ps.PROFILE_PATH = self.real_path


def test_store():
    print("\n[8] Отметка даты захода в профиле")
    import profile_store
    # банк слов здесь не нужен: тест про запись в файл (слова из профиля).
    # Иначе окно честно подмешает 5 новых слов текущей темы — и проверка
    # «заход собрался из профиля» упадёт не по делу.
    saved_new = config.VOCAB_NEW_PER_DAY
    config.VOCAB_NEW_PER_DAY = 0
    with temp_profile():
        path = profile_store.PROFILE_PATH
        profile_store.ensure_profile()
        before = profile_store.load().get("total_lessons", 0)
        check("свежий профиль: захода не было",
              profile_store.vocab_last_session() == "", profile_store.vocab_last_session())

        profile_store.add_vocabulary("ключ", ["key \u2014 Open the door with this key."])
        controller = VocabularyController(user_id=None)
        started = controller.start()
        check("заход собрался из профиля", len(started) == 1, started)
        check("до первого ответа дата не отмечена",
              profile_store.vocab_last_session() == "", profile_store.vocab_last_session())

        controller.answer("key")
        today = profile_store.vocab_last_session()
        check("после ответа дата отмечена", today != "", today)
        check("и это сегодня", vocabulary.session_today(today) is True, today)

        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        check("дата лежит в файле", raw.get("vocab_last_session") == today,
              raw.get("vocab_last_session"))
        check("total_lessons НЕ вырос (это не занятие)",
              raw.get("total_lessons", 0) == before, (before, raw.get("total_lessons")))
        check("уровень карточки вырос в файле",
              profile_store.vocabulary_cards()[0]["level"] == 1,
              profile_store.vocabulary_cards()[0])
    config.VOCAB_NEW_PER_DAY = saved_new


# =========================================================
# 9. Битые данные
# =========================================================
def test_broken():
    print("\n[9] Битые данные и отсутствующая карточка")
    cards = make_cards([("ключ", "key", "Open the door.")])
    store = FakeStore([])                  # карточки в «файле» нет
    ctrl = VocabularyController(store=store, cards=cards, today=D0)
    ctrl.start()
    res = ctrl.answer("key")
    check("ответ верный, но карточки нет → уровень не меняем",
          res["status"] == "good" and res["changed"] is False, res)

    learned = make_cards([("ключ", "key", "Open the door.")])
    learned[0]["level"] = 5
    check("выученное слово в заход не попадает",
          VocabularyController(store=FakeStore(learned), today=D0).start() == [])

    zero = make_cards([("ключ", "key", "Open the door.")])
    ctrl2 = VocabularyController(store=FakeStore(zero), today=D0)
    ctrl2.start()
    res = ctrl2.answer("keys")          # «почти» = промах
    check("промах уровень 0 не сдвигает",
          res["level_to"] == 0 and res["changed"] is True, res)
    check("промах посчитан", zero[0]["misses"] == 1, zero[0])

    ctrl3 = VocabularyController(store=FakeStore([]), cards=[{"word": "x"}], today=D0)
    ctrl3.start()
    check("карточка без en в заход не попадает", ctrl3.is_active is False)


def main():
    print("=" * 60)
    print("Проверка окна «Повторение» (этап B)")
    print("=" * 60)
    test_gap()
    test_references()
    test_session_day()
    test_session()
    test_answers()
    test_one_grade()
    test_hint_and_skip()
    test_store()
    test_broken()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
