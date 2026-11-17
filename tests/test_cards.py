# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_CARDS.PY — карточки правил (§79)
# =========================================================
#   python tests\test_cards.py
#
# Решение ученика 12.11.2026: клик по красному куску реплики открывает
# карточку правила с примерами. Здесь проверяется ВТОРОЕ: данные карточек
# и выбор нужной карточки под ошибку Аналитика.
#   1) файл читается, 24 карточки, ключи уникальны;
#   2) все правила из закрытого списка Аналитика закрыты (кроме "other");
#   3) у каждой карточки есть заголовок, «когда», примеры и «как не надо»;
#   4) pick() выбирает верную карточку (18 случаев, в т.ч. said -> say/tell);
#   5) неизвестное правило / промах -> None (карточку НЕ выдумываем).
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

import cards                                           # noqa: E402
import gaps                                            # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  \u2705 " if ok else "  \u274c ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def test_load():
    print("\n[1] Файл карточек")
    all_cards = cards.load()
    check("24 карточки", len(all_cards) == 24, len(all_cards))
    check("ключи — строки id", all(isinstance(k, str) and k for k in all_cards), list(all_cards)[:3])
    check("id внутри карточки совпадает с ключом",
          all(k == c["id"] for k, c in all_cards.items()), "да")


def test_rules_covered():
    print("\n[2] Все правила Аналитика закрыты")
    closed = set(gaps.RULES) - {"other"}
    covered = cards.rules_covered()
    missing = sorted(closed - covered)
    check("нет пропущенных правил", not missing, missing)
    check("лишних правил нет", not (covered - set(gaps.RULES)), sorted(covered - set(gaps.RULES)))


def test_fields():
    print("\n[3] Обязательные поля")
    bad = []
    for card_id, card in cards.load().items():
        if not str(card.get("title") or "").strip():
            bad.append(card_id + ":title")
        if not str(card.get("when") or "").strip():
            bad.append(card_id + ":when")
        if not str(card.get("wrong") or "").strip():
            bad.append(card_id + ":wrong")
        examples = card.get("examples") or []
        if not examples or not all(str(e).strip() for e in examples):
            bad.append(card_id + ":examples")
    check("заголовок, когда, примеры, как не надо — у всех", not bad, bad)
    kinds = {c.get("kind") for c in cards.load().values()}
    check("виды карточек: grammar и choice", kinds == {"grammar", "choice"}, kinds)


CASES = [
    ("article", "Jacket is too big.", "The jacket is too big.", "article_the"),
    ("article", "I need jacket.", "I need a jacket.", "article_a"),
    ("plural", "two mans", "two men", "plural_irregular"),
    ("plural", "two book", "two books", "plural_s"),
    ("past_simple", "I didn't went", "I didn't go", "past_irregular"),
    ("past_simple", "Yesterday I work", "Yesterday I worked", "past_simple_ed"),
    ("verb_form", "She will comes", "She will come", "verb_form_modal"),
    ("verb_form", "I like swim", "I like swimming", "verb_form_ing"),
    ("preposition", "in Monday", "on Monday", "preposition_time"),
    ("preposition", "cup in the table", "cup on the table", "preposition_place"),
    ("word_choice", "She said me the truth", "She told me the truth", "a2.say_tell"),
    ("word_choice", "I make my homework", "I do my homework", "a2.do_make"),
    ("word_choice", "I put on a new sweater every day", "I wear a new sweater", "a2.wear_puton"),
    ("word_choice", "Can I lend ten rubles from you", "Can I borrow ten rubles", "a2.borrow_lend"),
    ("word_choice", "Yesterday I heard to music", "Yesterday I listened to music", "a2.hear_listen"),
    ("spelling", "stoped", "stopped", "spelling"),
    ("word_order", "Where you live?", "Where do you live?", "word_order"),
    ("aux_verb", "You like coffee?", "Do you like coffee?", "aux_verb"),
    # клик приносит только «как надо» (без текста реплики) — тоже должно работать
    ("article", "", "The jacket is too big.", "article_the"),
]


def test_pick():
    print("\n[4] Какая карточка под какую ошибку")
    wrong_cases = []
    for rule, said, right, want in CASES:
        card = cards.pick(rule, said, right)
        got = card["id"] if card else None
        if got != want:
            wrong_cases.append("%s: '%s' -> %s (ждали %s)" % (rule, said, got, want))
    check("%d случаев выбраны верно" % len(CASES), not wrong_cases, wrong_cases)


def test_no_card():
    print("\n[5] Нет карточки — не выдумываем")
    check("правило other -> None", cards.pick("other", "что-то", "что-то ещё") is None)
    check("пустое правило -> None", cards.pick("", "", "") is None)
    check("неизвестный id -> None", cards.get("a2.такого_нет") is None)
    check("неизвестное правило по id -> None", cards.get("нет-такого") is None)
    # word_choice без совпадений — тоже None, а не случайная пара
    check("word_choice мимо библиотеки -> None",
          cards.pick("word_choice", "I go to school", "I go to the school") is None)


def main():
    test_load()
    test_rules_covered()
    test_fields()
    test_pick()
    test_no_card()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d" % len(FAILED))
        for name in FAILED:
            print("  - " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
