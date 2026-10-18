# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_VOCAB_PROMPT.PY — слова ученика в разговоре (этап C)
# =========================================================
#   python tests\test_vocab_prompt.py   (окно НЕ нужно, модель НЕ нужна)
#
# Проверяем:
#   1) базовый промпт БЕЗ слов не изменился ни на символ (вызов без words
#      и с words=None дают одинаковый текст);
#   2) блок слов добавляется В КОНЕЦ и только когда слова есть;
#   3) vocabulary.prompt_words: выученные не берём, порядок — от трудных,
#      лимит соблюдается, битые данные не ломают;
#   4) ChatController сам собирает слова из профиля ученика;
#   5) выключатели VOCAB_ENABLED / VOCAB_IN_PROMPT работают.
# =========================================================

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                                                   # noqa: E402
import profile_store                                            # noqa: E402
import prompt_builder                                           # noqa: E402
import vocabulary                                               # noqa: E402
from controllers.chat_controller import ChatController          # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


BASE_PROFILE = {"mistakes": {}, "strengths": [], "topics_passed": [],
                "total_lessons": 0}


# =========================================================
# 1. База промпта не изменилась
# =========================================================
def test_base_unchanged():
    print("\n[1] Без слов промпт прежний")
    for mode in ("lesson", "free"):
        old = prompt_builder.build_system_prompt(mode, BASE_PROFILE, "en")
        new = prompt_builder.build_system_prompt(mode, BASE_PROFILE, "en", words=None)
        check("%s: words=None → тот же текст" % mode, old == new,
              len(old) - len(new))
        check("%s: без блока слов в тексте" % mode,
              "VOCABULARY" not in old, old[-200:])
        check("%s: пустой список = тот же текст" % mode,
              prompt_builder.build_system_prompt(mode, BASE_PROFILE, "en", words=[])
              == old)
        check("%s: строки-пустышки не добавляют блок" % mode,
              prompt_builder.build_system_prompt(mode, BASE_PROFILE, "en",
                                                 words=["", "   "]) == old)


# =========================================================
# 2. Блок слов
# =========================================================
def test_words_block():
    print("\n[2] Блок слов: в конец и только когда есть")
    base = prompt_builder.build_system_prompt("lesson", BASE_PROFILE, "en")
    with_words = prompt_builder.build_system_prompt(
        "lesson", BASE_PROFILE, "en", words=["ключ — key", "дверь — door"])
    check("текст стал длиннее", len(with_words) > len(base),
          (len(base), len(with_words)))
    check("блок добавлен В КОНЕЦ", with_words.startswith(base))
    check("слова в блоке", "ключ — key" in with_words and "дверь — door" in with_words)
    check("слова списком", "\n- ключ — key" in with_words, with_words[-260:])
    check("просьба «не устраивать опрос» есть",
          "not turn it into a test" in with_words.lower(), with_words[-400:])
    check("просит 1-2 слова, а не все",
          "ONE or TWO" in with_words, with_words[-400:])
    # остальные необязательные блоки не сдвинулись
    full = prompt_builder.build_system_prompt(
        "lesson", {"level": "A1", "mistakes": {}, "weak_topics": [{"topic": "numbers"}],
                   "total_lessons": 3},
        "en", level="A1", student={"name": "Дамиль", "gender": "male"},
        context="METHOD NOTE", plan="Focus: numbers", words=["ключ — key"])
    order = [full.find(x) for x in ("STUDENT ENGLISH LEVEL", "WEAK TOPICS",
                                    "STUDENT:", "TODAY'S LESSON PLAN",
                                    "TEACHING NOTES", "VOCABULARY")]
    check("порядок блоков прежний, слова — последние",
          all(v >= 0 for v in order) and order == sorted(order), order)


# =========================================================
# 3. Какие слова берём
# =========================================================
def make_cards(pairs):
    cards = []
    for word, en, level, misses in pairs:
        card = vocabulary.new_card(word, en, "Example with %s." % en)
        card["level"] = level
        card["misses"] = misses
        cards.append(card)
    return cards


def test_prompt_words():
    print("\n[3] vocabulary.prompt_words: только «трудные» слова")
    cards = make_cards([("ключ", "key", 0, 0), ("дверь", "door", 3, 2),
                        ("окно", "window", 5, 5), ("стол", "table", 1, 4)])
    words = vocabulary.prompt_words(cards, limit=4)
    check("выученное (5) не попадает",
          not any("window" in w for w in words), words)
    check("сначала нижний уровень", words[0].endswith("key"), words)
    check("затем по числу промахов",
          words[1].endswith("table") and words[2].endswith("door"), words)
    check("формат «слово — значение»", " — " in words[0], words[0])
    check("лимит соблюдается", len(vocabulary.prompt_words(cards, limit=2)) == 2)
    check("по умолчанию не больше VOCAB_PROMPT_LIMIT",
          len(vocabulary.prompt_words(cards)) <= int(config.VOCAB_PROMPT_LIMIT),
          vocabulary.prompt_words(cards))
    check("пусто → пустой список", vocabulary.prompt_words([]) == []
          and vocabulary.prompt_words(None) == [])
    broken = [{"word": "", "en": "x"}, {"word": "a", "en": ""},
              {"word": "b", "en": "bee", "level": "мусор"}]
    check("битые карточки не ломают", vocabulary.prompt_words(broken) == ["b — bee"],
          vocabulary.prompt_words(broken))


# =========================================================
# 4-5. ChatController и выключатели
# =========================================================
class temp_profile:
    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_vocab_prompt_")
        self.real = profile_store.PROFILE_PATH
        profile_store.PROFILE_PATH = os.path.join(self.dir, "student_profile.json")
        profile_store.set_active_user(None)
        profile_store.ensure_profile()
        return profile_store.PROFILE_PATH

    def __exit__(self, *exc):
        profile_store.PROFILE_PATH = self.real


def make_controller():
    real_rag = config.RAG_ENABLED
    config.RAG_ENABLED = False
    try:
        return ChatController(llm=object(), dispatch=lambda fn: fn())
    finally:
        config.RAG_ENABLED = real_rag


def test_controller():
    print("\n[4] ChatController берёт слова из профиля")
    with temp_profile():
        profile_store.add_vocabulary("ключ", ["key \u2014 Open the door with this key."])
        ctrl = make_controller()
        check("слово найдено", ctrl._prompt_words() == ["ключ — key"],
              ctrl._prompt_words())

        print("\n[5] Выключатели этапа C")
        real_in_prompt = config.VOCAB_IN_PROMPT
        real_enabled = config.VOCAB_ENABLED
        try:
            config.VOCAB_IN_PROMPT = False
            check("VOCAB_IN_PROMPT=False → блок не добавляется",
                  ctrl._prompt_words() == [], ctrl._prompt_words())
            config.VOCAB_IN_PROMPT = True
            config.VOCAB_ENABLED = False
            check("VOCAB_ENABLED=False → блок не добавляется",
                  ctrl._prompt_words() == [], ctrl._prompt_words())
        finally:
            config.VOCAB_IN_PROMPT = real_in_prompt
            config.VOCAB_ENABLED = real_enabled

        profile_store.PROFILE_PATH = os.path.join(os.path.dirname(
            profile_store.PROFILE_PATH), "нет_такого_файла.json")
        check("пропавший профиль не ломает ответ", ctrl._prompt_words() == [],
              ctrl._prompt_words())

    print("\n[6] Промпт реального запроса содержит слова")
    with temp_profile():
        profile_store.add_vocabulary("дверь", ["door \u2014 Close the door."])
        captured = {}

        class FakeLLM:
            def complete(self, messages, **kwargs):
                captured["system"] = messages[0]["content"]
                return True, "Ok!"

        ctrl = ChatController(llm=FakeLLM(), dispatch=lambda fn: fn())
        real_rag = config.RAG_ENABLED
        config.RAG_ENABLED = False
        ctrl.rag = None
        try:
            ok, reply = ctrl._request("Hello")
        finally:
            config.RAG_ENABLED = real_rag
        system = captured.get("system", "")
        check("ответ получен", ok and reply == "Ok!", (ok, reply))
        check("в промпте запроса есть слово ученика", "дверь — door" in system,
              system[-200:] if system else "пусто")
        check("и блок стоит в самом конце",
              system.rstrip().endswith("what to practise."),
              system[-80:])


def main():
    print("=" * 60)
    print("Проверка этапа C: слова ученика в разговоре")
    print("=" * 60)
    test_base_unchanged()
    test_words_block()
    test_prompt_words()
    test_controller()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
