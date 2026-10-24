# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_VOCAB_SYNONYMS.PY — синонимы принимаются за верный ответ
# =========================================================
#   python tests\test_vocab_synonyms.py   (Tk и микрофон НЕ нужны)
#
# Решение ученика (24.10.2026): на карточку «привет» правильны и «Hey»,
# и «Hi», и «Hello». Раньше сверка была буквальная, и живой ответ «hello»
# считался «сказал своё» — с потерей уровня за правильный английский.
#
# Проверяем:
#   1) «привет → Hey» принимает hello и hi (уровень растёт);
#   2) своё собственное слово НЕ дублируется в синонимах;
#   3) чужая фраза по-прежнему «сказал своё» (не всё подряд верно);
#   4) группу находим и по русскому слову, и по английскому значению;
#   5) слово вне таблицы ведёт себя как раньше;
#   6) регистр и знаки препинания не мешают;
#   7) сравнение текста same_text.
# =========================================================

import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import vocabulary                                          # noqa: E402
from controllers.vocabulary_controller import VocabularyController  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    if ok:
        print("  ✅ %s" % name)
    else:
        print("  ❌ %s  →  %s" % (name, detail))
        FAILED.append(name)


class FakeStore:
    """Профиль-подделка: уровень двигается как в настоящем профиле."""

    def __init__(self, cards):
        self.cards = cards

    def vocabulary_cards(self, user_id=None):
        return self.cards

    def update_vocabulary_card(self, word, en, success, user_id=None):
        for card in self.cards:
            if card.get("word") == word and card.get("en") == en:
                level = int(card.get("level") or 0)
                card["level"] = max(0, level + (1 if success else -1))
                return card
        return None

    def mark_vocab_session(self, user_id=None):
        return None


def make_ctrl(word, en, example):
    card = vocabulary.new_card(word, en, example, today=date(2026, 10, 24))
    ctrl = VocabularyController(store=FakeStore([card]), today=date(2026, 10, 24))
    ctrl.start(cards=[card])
    return ctrl


def test_synonyms_are_good():
    """[1] «hello» и «hi» на карточку «привет → Hey» — верный ответ."""
    print("\n[1] синонимы засчитываются как верный ответ")
    for said in ("hello", "hi", "Hey"):
        ctrl = make_ctrl("привет", "Hey", "Hey, what's up?")
        res = ctrl.answer(said)
        check("«%s» → good" % said, res.get("status") == "good", res.get("status"))
        check("«%s» уровень 0 → 1" % said, res.get("level_to") == 1, res)


def test_own_word_not_repeated():
    """[2] своё слово в синонимы не попадает."""
    print("\n[2] своё значение не дублируется")
    alts = vocabulary.alternatives({"word": "привет", "en": "hi"})
    check("для hi синонимы без hi", "hi" not in alts, alts)
    check("но hello и hey есть", "hello" in alts and "hey" in alts, alts)
    alts = vocabulary.alternatives({"word": "привет", "en": "Hey"})
    check("для Hey синонимы без hey", "hey" not in alts, alts)


def test_other_speech_still_unrelated():
    """[3] чужая фраза — по-прежнему «сказал своё»."""
    print("\n[3] «не всё подряд верно»")
    ctrl = make_ctrl("привет", "Hey", "Hey, what's up?")
    res = ctrl.answer("I had a wonderful vacation by the sea")
    check("длинная чужая фраза → unrelated", res.get("status") == "unrelated", res)
    check("уровень не двинулся", ctrl.current()["level"] == 0, ctrl.current())
    ctrl2 = make_ctrl("привет", "Hey", "Hey, what's up?")
    res2 = ctrl2.answer("banana")
    check("одно чужое слово → unrelated", res2.get("status") == "unrelated", res2)


def test_group_found_two_ways():
    """[4] группу находим по русскому слову И по английскому значению."""
    print("\n[4] поиск группы с двух сторон")
    by_ru = vocabulary.alternatives({"word": "спасибо", "en": "Thank you."})
    check("по-русски: thanks", "thanks" in by_ru, by_ru)
    by_en = vocabulary.alternatives({"word": "благодарность", "en": "thanks"})
    check("по-английски: thank you", "thank you" in by_en, by_en)


def test_word_outside_table():
    """[5] слово вне таблицы — поведение как раньше."""
    print("\n[5] слова вне таблицы")
    check("ключ/key синонимов не имеет",
          vocabulary.alternatives({"word": "ключ", "en": "key"}) == [])
    ctrl = make_ctrl("ключ", "key", "Open the door with this key.")
    check("«key» → good", ctrl.answer("key").get("status") == "good")
    ctrl2 = make_ctrl("ключ", "key", "Open the door with this key.")
    check("«open» → unrelated", ctrl2.answer("open").get("status") == "unrelated")


def test_case_and_punctuation():
    """[6] регистр и знаки препинания не мешают."""
    print("\n[6] регистр и знаки")
    ctrl = make_ctrl("привет", "Hey", "Hey, what's up?")
    res = ctrl.answer("Hello!")
    check("«Hello!» → good", res.get("status") == "good", res.get("status"))
    check("пустых синонимов нет",
          all(str(item).strip() for item in vocabulary.alternatives({"word": "привет", "en": "Hey"})))


def test_same_text():
    """[7] сравнение текста."""
    print("\n[7] same_text")
    check("«Hello!» = «hello»", vocabulary.same_text("Hello!", "hello"))
    check("«Hey» ≠ «hello»", not vocabulary.same_text("Hey", "hello"))
    check("лишние пробелы не мешают", vocabulary.same_text("  thank   you ", "Thank you"))


def main():
    print("=" * 60)
    print("ТЕСТ: синонимы принимаются за верный ответ (решение ученика 24.10)")
    print("=" * 60)
    test_synonyms_are_good()
    test_own_word_not_repeated()
    test_other_speech_still_unrelated()
    test_group_found_two_ways()
    test_word_outside_table()
    test_case_and_punctuation()
    test_same_text()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
