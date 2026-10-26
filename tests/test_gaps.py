# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GAPS.PY — карта пробелов (gaps.py, §46)
# =========================================================
#   python tests\test_gaps.py
#
# Что проверяем:
#   1) normalize_rule: только закрытый список, всё прочее -> other;
#   2) guess_rule: догадка правила по паре «было -> стало»;
#   3) aggregate: счёт по правилам, примеры, даты, порог «пробел»,
#      «прочее» всегда последним и пробелом не считается;
#   4) prompt_block: 3 правила, без «other», запрет выдумывать, флаг config;
#   5) table_rows: подписи по-русски, примеры через «->», лимит строк.
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

import config                     # noqa: E402
import gaps                       # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  OK   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def rows(*items):
    """Быстрые записи для aggregate: (правило, было, стало, дата)."""
    return [{"rule": r, "wrong": w, "correct": c, "date": d, "type": "grammar",
             "source": "chat"} for r, w, c, d in items]


SAMPLE = rows(
    ("past_simple", "I make", "I made", "2026-10-01T10:00:00"),
    ("past_simple", "drink", "drank", "2026-10-02T10:00:00"),
    ("past_simple", "go", "went", "2026-10-03T10:00:00"),
    ("word_order", "have usually breakfast", "usually have breakfast", "2026-10-04T10:00:00"),
    ("word_order", "I very like it", "I like it very much", "2026-10-05T10:00:00"),
    ("article", "go to school", "go to the school", "2026-10-06T10:00:00"),
    ("other", "one time in month", "once a month", "2026-10-07T10:00:00"),
)


# =========================================================
# 1. Закрытый список правил
# =========================================================
def test_normalize():
    print("\n[1] normalize_rule")
    check("10 правил в списке", len(gaps.RULES) == 10, gaps.RULES)
    check("правило из списка проходит", gaps.normalize_rule("past_simple") == "past_simple")
    check("регистр и пробелы чинятся", gaps.normalize_rule(" Word Order ") == "word_order")
    check("дефис тоже", gaps.normalize_rule("past-simple") == "past_simple")
    check("придуманное слово -> other", gaps.normalize_rule("темпоральность") == "other")
    check("пусто -> other", gaps.normalize_rule(None) == "other")
    check("у каждого правила есть русская подпись",
          all(rule in gaps.RULE_RU for rule in gaps.RULES))


# =========================================================
# 2. Догадка правила
# =========================================================
def test_guess():
    print("\n[2] guess_rule")
    cases = [
        ("make", "made", "past_simple"),
        ("drink", "drank", "past_simple"),
        ("walk", "walked", "past_simple"),
        ("you not have", "you don't have", "aux_verb"),
        ("I must to say", "I must say", "verb_form"),
        ("have usually breakfast", "usually have breakfast", "word_order"),
        ("two book", "two books", "plural"),
        ("normaly", "normally", "spelling"),
        ("possible", "possibly", "word_choice"),
        ("go to lay down", "go to lie down", "word_choice"),
        ("one time in month", "once a month", "preposition"),
        ("make", "meet", "word_choice"),
        ("go to school", "go to the school", "article"),
        ("I live in Moscow", "I live in Moscow", "other"),
        ("", "books", "other"),
    ]
    for wrong, correct, want in cases:
        got = gaps.guess_rule(wrong, correct)
        check("%r -> %r = %s" % (wrong, correct, want), got == want, got)


# =========================================================
# 3. Агрегация
# =========================================================
def test_aggregate():
    print("\n[3] aggregate")
    result = gaps.aggregate(rows=SAMPLE)
    order = [b["rule"] for b in result]
    check("сначала самое частое", order[0] == "past_simple", order)
    check("потом word_order", order[1] == "word_order", order)
    first = result[0]
    check("счёт past_simple = 3", first["count"] == 3, first)
    check("примеры собраны", first["examples"][0] == ("I make", "I made"), first["examples"])
    check("не больше трёх примеров", len(first["examples"]) <= 3, first["examples"])
    check("первая дата", first["first"].startswith("2026-10-01"), first["first"])
    check("последняя дата", first["last"].startswith("2026-10-03"), first["last"])
    check("подпись по-русски", first["label"] == gaps.RULE_RU["past_simple"], first["label"])
    check("3 раза = пробел", first["is_gap"] is True, first)
    article = [b for b in result if b["rule"] == "article"][0]
    check("1 раз = ещё не пробел", article["is_gap"] is False, article)

    check("«прочее» всегда последним",
          order[-1] == "other", order)
    other = [b for b in result if b["rule"] == "other"][0]
    check("«без правила» пробелом не считается", other["is_gap"] is False, other)

    old = getattr(config, "GAPS_MIN_COUNT", 2)
    config.GAPS_MIN_COUNT = 1
    try:
        result = gaps.aggregate(rows=SAMPLE)
        check("порог из config работает",
              all(b["is_gap"] for b in result if b["rule"] != "other"), result)
        check("«прочее» не пробел даже при пороге 1",
              [b for b in result if b["rule"] == "other"][0]["is_gap"] is False,
              result)
    finally:
        config.GAPS_MIN_COUNT = old


# =========================================================
# 4. Строка в промпт
# =========================================================
def test_prompt_block():
    print("\n[4] prompt_block")
    text = gaps.prompt_block(rows=SAMPLE)
    check("строка непустая", bool(text), text)
    check("есть past simple", "past simple" in text, text)
    check("есть word order", "word order" in text, text)
    check("счёт указан", "3 times" in text, text)
    check("пример в кавычках", '"I make" -> "I made"' in text, text)
    check("запрет выдумывать на месте", "Never invent a mistake" in text, text)
    check("слово other в промпт не идёт", "other" not in text.lower(), text)
    check("правило с одним случаем не в промпте", "articles a/an/the" not in text, text)

    many = rows(*[("past_simple", "go", "went", "2026-10-01"),
                  ("past_simple", "make", "made", "2026-10-02"),
                  ("word_order", "a", "b", "2026-10-01"),
                  ("word_order", "c", "d", "2026-10-02"),
                  ("plural", "book", "books", "2026-10-01"),
                  ("plural", "cat", "cats", "2026-10-02"),
                  ("spelling", "normaly", "normally", "2026-10-01"),
                  ("spelling", "recieve", "receive", "2026-10-02"),
                  ("article", "a", "the", "2026-10-01"),
                  ("article", "a", "an", "2026-10-02")])
    text = gaps.prompt_block(rows=many, limit=3)
    check("не больше трёх правил", text.count("\n- ") == 3, text)

    check("пустая база -> пусто", gaps.prompt_block(rows=[]) == "")
    check("только other -> пусто", gaps.prompt_block(rows=rows(("other", "a", "b", "2026-10-01"))) == "")

    old = getattr(config, "GAPS_IN_PROMPT", True)
    config.GAPS_IN_PROMPT = False
    try:
        check("флаг выключает блок", gaps.prompt_block(rows=SAMPLE) == "")
    finally:
        config.GAPS_IN_PROMPT = old


# =========================================================
# 5. Строки таблицы для «Профиля»
# =========================================================
def test_table_rows():
    print("\n[5] table_rows")
    data = gaps.table_rows(rows=SAMPLE)
    check("строки есть", len(data) == 4, data)
    top = data[0]
    check("подпись по-русски", top["label"] == "прошедшее время", top)
    check("счёт в строке", top["count"] == 3, top)
    check("примеры через стрелку", top["examples"].startswith("I make →"), top)
    check("пометка пробела", top["gap"] is True, top)
    short = gaps.table_rows(rows=SAMPLE, limit=2)
    check("лимит строк работает", len(short) == 2, short)


# =========================================================
# 6. Кому идёт строка: Планировщику — да, Аналитику — нет (замер!)
# =========================================================
def test_role_flags():
    print("\n[6] Флаги ролей")
    import tempfile
    import profile_store
    import stats_store
    import user_manager
    from controllers.chat_controller import ChatController

    real = (user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE)
    tmp = tempfile.mkdtemp(prefix="et_gaps_")
    keep_analyst = getattr(config, "GAPS_IN_ANALYST", False)
    try:
        user_manager.PROFILES_DIR = tmp
        user_manager.LAST_USER_FILE = os.path.join(tmp, "last_user.txt")
        profile_store.set_active_user(None)
        stats_store.forget_migrated()
        stats_store.add_mistakes([
            {"wrong": "I make", "correct": "I made", "rule": "past_simple"},
            {"wrong": "drink", "correct": "drank", "rule": "past_simple"},
            {"wrong": "go", "correct": "went", "rule": "past_simple"},
        ], 1)
        chat = ChatController(llm=None, user_id=1)
        planner_text = chat._gaps_block()
        check("Планировщику строка идёт", "past simple" in planner_text, planner_text)
        check("Аналитику по умолчанию НЕ идёт", chat._gaps_block(for_analyst=True) == "",
              chat._gaps_block(for_analyst=True))
        config.GAPS_IN_ANALYST = True
        check("флаг GAPS_IN_ANALYST включает строку",
              "past simple" in chat._gaps_block(for_analyst=True))
    finally:
        config.GAPS_IN_ANALYST = keep_analyst
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE = real
        profile_store.set_active_user(None)
        stats_store.forget_migrated()


def main():
    test_normalize()
    test_guess()
    test_aggregate()
    test_prompt_block()
    test_table_rows()
    test_role_flags()
    print("\n" + ("ВСЁ ПРОЙДЕНО" if not FAILED else "ПРОВАЛЕНО: %d" % len(FAILED)))
    for name in FAILED:
        print("  - " + name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
