# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GLOSSARY.PY — переводы по наведению: КУСКИ ПО СМЫСЛУ
# =========================================================
#   python tests\test_glossary.py
#
# ЗАЧЕМ. Решение ученика (03.11.2026): пословный перевод — ужас.
# На «Would you like a table by the window?» наведение давало
# «Было бы ты хотеть а стол у окна (определенный) окно». Теперь модель режет
# реплику на КУСКИ СМЫСЛА ([Would you like] хотели бы вы [a table] столик
# [by the window] у окна), а КОД проверяет, что куски покрывают ВСЕ слова
# реплики по порядку. Не покрыли — разбор выбрасывается.
#
# Проверяем:
#   1) токены: апострофы/знаки, word_at попадает в слово;
#   2) lookup: наведение на любое слово куска даёт КУСОК; «word» — слово
#      под курсором (его произносим по клику);
#   3) prime: один запрос на реплику, повтор — из кэша, таймаут;
#   4) брак: битый JSON → повтор; куски не покрыли реплику → отказ;
#      пословный ответ модели → отказ; мусор → (False, причина);
#   5) файл кэша: «chunks», второй запуск бесплатен;
#   6) разбор ответа модели: ```json, пусто, без ключа, без ru;
#   7) пример со скриншота: «by the window» — один кусок, а не слова.
# Модель подменяется пустышкой, микрофон и сеть не нужны.
# =========================================================

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import glossary                                                   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


SENTENCE = "Look forward to seeing you there, Damil! Don\u2019t forget."

ANSWER = json.dumps({"chunks": [
    {"en": "Look forward to", "ru": "с нетерпением ждать"},
    {"en": "seeing you", "ru": "видеть тебя"},
    {"en": "there", "ru": "там"},
    {"en": "Damil", "ru": "Дамиль"},
    {"en": "Don't forget", "ru": "не забудь"},
]}, ensure_ascii=False)

COVERED = "Look forward to seeing you there, Damil! Don't forget."


class FakeLLM:
    """Заглушка модели: считает вызовы и отдаёт заранее заданные ответы."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0
        self.last_timeout = None
        self.messages = None

    def complete(self, messages, max_tokens=None, temperature=None,
                 stop=None, timeout=60):
        self.calls += 1
        self.last_timeout = timeout
        self.messages = messages
        if not self.answers:
            return False, "нет заготовки"
        return True, self.answers.pop(0)


def tmp_path(folder):
    return os.path.join(folder, "glossary.json")


# ---------------------------------------------------------
print("[1] Токены и попадание курсора в слово")
tokens = glossary.tokenize(SENTENCE)
keys = [t["key"] for t in tokens]
check("слова найдены по порядку", keys[:4] == ["look", "forward", "to", "seeing"], keys[:4])
check("апостроф-ёлочка приведён к обычному", "don't" in keys, keys[-3:])
check("знаки не попали в слова",
      all(t["key"].replace("'", "").isalpha() for t in tokens), keys)
check("normalize снимает запятую и регистр",
      glossary.normalize("  Hello, ") == "hello", glossary.normalize("  Hello, "))

token = glossary.word_at(SENTENCE, 2)
check("word_at(2) = 'Look'", token and token["key"] == "look", token)
check("word_at на пробеле = None",
      glossary.word_at(SENTENCE, 4) is None, glossary.word_at(SENTENCE, 4))
check("word_at на кириллице = None",
      glossary.word_at("Привет hello", 3) is None)
check("sentence_key — слова реплики",
      glossary.sentence_key("Hi, Tom!") == "hi tom", glossary.sentence_key("Hi, Tom!"))

# ---------------------------------------------------------
print("\n[2] Подсказка по наведению: КУСОК целиком (без модели)")
folder = tempfile.mkdtemp()
gl = glossary.Glossary(llm=None, path=tmp_path(folder))
added = gl.add_chunks(COVERED, glossary.parse_chunks(ANSWER))
check("разбор реплики принят", added == 1, added)

hit = gl.lookup(SENTENCE, 2)
check("'Look' → кусок целиком", hit and hit["en"] == "Look forward to", hit)
check("перевод куска по смыслу", hit and hit["ru"] == "с нетерпением ждать", hit)
check("кусок из 3 слов помечен phrase=True", hit and hit["phrase"] is True, hit)
check("границы куска 0…15", hit and hit["start"] == 0 and hit["end"] == 15, hit)

hit2 = gl.lookup(SENTENCE, 9)          # курсор на 2-м слове куска ('forward')
check("курсор на 2-м слове даёт тот же кусок",
      hit2 and hit2["en"] == "Look forward to", hit2)

hit3 = gl.lookup(SENTENCE, SENTENCE.index("seeing"))
check("следующий кусок — «seeing you»", hit3 and hit3["en"] == "seeing you"
      and hit3["ru"] == "видеть тебя", hit3)

hit4 = gl.lookup(SENTENCE, SENTENCE.index("you"))   # 'you' внутри «seeing you»
check("клик на 'you' даёт кусок «seeing you»", hit4 and hit4["en"] == "seeing you", hit4)
check("«word» — СЛОВО под курсором (его произносим)",
      hit4 and hit4["word"] == "you", hit4)

check("неразобранная реплика → None (модель не зовём)",
      gl.lookup("Elephant", 1) is None)
check("кириллица → None", gl.lookup("Привет hello", 8) is None)
check("stats: попадания посчитаны", gl.stats["hits"] == 4, gl.stats)
check("stats: промахи посчитаны", gl.stats["misses"] >= 2, gl.stats)

# ---------------------------------------------------------
print("\n[3] prime: модель зовётся ровно один раз на реплику")
llm = FakeLLM([ANSWER])
gl2 = glossary.Glossary(llm=llm, path=tmp_path(tempfile.mkdtemp()))
ok, added = gl2.prime(COVERED)
check("первый разбор удался", ok is True, (ok, added))
check("добавлена 1 реплика", added == 1, added)
check("вызовов модели 1", llm.calls == 1, llm.calls)
check("таймаут передан в модель", llm.last_timeout == 120, llm.last_timeout)
check("в промпте есть требование кусков по смыслу",
      any("Would you like" in str(m.get("content", ""))
          for m in llm.messages or []), llm.messages)

ok, added2 = gl2.prime(COVERED)
check("повторный разбор без модели", ok is True and added2 == 0, (ok, added2))
check("вызовов модели по-прежнему 1", llm.calls == 1, llm.calls)

# ---------------------------------------------------------
print("\n[4] Брак: повтор, отказ и честная причина")
llm3 = FakeLLM(['{"chunks":[{"en":"hi","ru":"привет",', ANSWER])
gl3 = glossary.Glossary(llm=llm3, path=tmp_path(tempfile.mkdtemp()))
ok, added = gl3.prime(COVERED)
check("после повтора разбор удался", ok is True and added == 1, (ok, added))
check("вызовов модели 2", llm3.calls == 2, llm3.calls)
check("повтор посчитан", gl3.stats["retries"] == 1, gl3.stats)

# куски есть, но реплику не покрывают (пропущены слова) — брак
SKIP_WORDS = json.dumps({"chunks": [
    {"en": "Look forward to", "ru": "с нетерпением ждать"},
    {"en": "seeing you", "ru": "видеть тебя"},
]}, ensure_ascii=False)
llm4 = FakeLLM([SKIP_WORDS, SKIP_WORDS])
gl4 = glossary.Glossary(llm=llm4, path=tmp_path(tempfile.mkdtemp()))
ok, reason = gl4.prime(COVERED)
check("куски не покрыли реплику → отказ", ok is False, (ok, reason))
check("причина названа честно", "покрыли" in str(reason), reason)
check("провал посчитан", gl4.stats["failed"] == 1, gl4.stats)

# пословный ответ модели (артикль отдельным куском) — брак
BY_WORD = json.dumps({"chunks": [
    {"en": "Would", "ru": "было бы"},
    {"en": "you", "ru": "ты"},
    {"en": "like", "ru": "хотеть"},
    {"en": "a", "ru": "а"},
    {"en": "table", "ru": "стол"},
]}, ensure_ascii=False)
llm5 = FakeLLM([BY_WORD, BY_WORD])
gl5 = glossary.Glossary(llm=llm5, path=tmp_path(tempfile.mkdtemp()))
ok, reason = gl5.prime("Would you like a table")
check("пословный ответ модели не принят", ok is False, (ok, reason))

llm6 = FakeLLM(["мусор", "тоже мусор"])
gl6 = glossary.Glossary(llm=llm6, path=tmp_path(tempfile.mkdtemp()))
ok, reason = gl6.prime("Something unclear")
check("мусор → (False, причина)", ok is False and reason, (ok, reason))
check("провал посчитан", gl6.stats["failed"] == 1, gl6.stats)

gl7 = glossary.Glossary(llm=None, path=tmp_path(tempfile.mkdtemp()))
ok, reason = gl7.prime("Hello there")
check("нет модели → (False, 'нет модели')", ok is False and reason == "нет модели",
      (ok, reason))
check("пустая реплика → (False, 'нечего разбирать')",
      gl7.prime("   ")[1] == "нечего разбирать")

# ---------------------------------------------------------
print("\n[5] Файл кэша: второй запуск бесплатен")
folder5 = tempfile.mkdtemp()
gl8 = glossary.Glossary(llm=FakeLLM([ANSWER]), path=tmp_path(folder5))
gl8.prime(COVERED)
check("файл появился", os.path.exists(tmp_path(folder5)), tmp_path(folder5))
saved = json.load(open(tmp_path(folder5), encoding="utf-8"))
check("в файле раздел chunks", "chunks" in saved, list(saved))
check("в chunks одна реплика", len(saved.get("chunks") or {}) == 1,
      list(saved.get("chunks") or {}))
check("первый кусок сохранён как пара",
      (saved["chunks"][list(saved["chunks"])[0]][0]
       == ["Look forward to", "с нетерпением ждать"]),
      saved["chunks"][list(saved["chunks"])[0]][0])

llm9 = FakeLLM([])
gl9 = glossary.Glossary(llm=llm9, path=tmp_path(folder5))
hit = gl9.lookup(SENTENCE, 2)
check("новый объект читает кэш с диска",
      hit and hit["ru"] == "с нетерпением ждать", hit)
ok, added = gl9.prime(COVERED)
check("повторный разбор из кэша — без модели",
      ok is True and added == 0 and llm9.calls == 0, (ok, added, llm9.calls))

gl10 = glossary.Glossary(llm=None, path=os.path.join(tempfile.mkdtemp(), "нет.json"))
check("нет файла — не падаем", gl10.chunks == {}, gl10.chunks)

# старый формат (пословные words/phrases) не подхватывается: он и давал бред
legacy = os.path.join(tempfile.mkdtemp(), "glossary.json")
with open(legacy, "w", encoding="utf-8") as f:
    json.dump({"words": {"window": "окно"}, "phrases": {}}, f, ensure_ascii=False)
gl11 = glossary.Glossary(llm=None, path=legacy)
check("старый пословный кэш игнорируется",
      gl11.lookup("by the window", 4) is None, gl11.chunks)

# ---------------------------------------------------------
print("\n[6] Разбор ответа модели")
check("```json и текст вокруг — разбираются",
      len(glossary.parse_chunks("Вот куски:\n```json\n" + ANSWER + "\n```")) == 5)
check("null/пусто → []", glossary.parse_chunks("") == []
      and glossary.parse_chunks(None) == [])
check("без ключа chunks → []", glossary.parse_chunks('{"data": []}') == [])
check("куски без ru отбрасываются",
      glossary.parse_chunks('{"chunks":[{"en":"hi","ru":""},{"en":"yes","ru":"да"}]}')
      == [["yes", "да"]])

# ---------------------------------------------------------
print("\n[7] Пример со скриншота: смысл вместо слов")
BAD_SENTENCE = "Would you like a table by the window?"
gl12 = glossary.Glossary(llm=None, path=tmp_path(tempfile.mkdtemp()))
good = [["Would you like", "хотели бы вы"],
        ["a table", "столик"],
        ["by the window", "у окна"]]
check("хороший разбор принят", gl12.add_chunks(BAD_SENTENCE, good) == 1)

hit = gl12.lookup(BAD_SENTENCE, BAD_SENTENCE.index("the"))  # 'the' в «by the window»
check("наведение на 'the' даёт «by the window»",
      hit and hit["en"] == "by the window", hit)
check("перевод — «у окна», а не «определенный окно»",
      hit and hit["ru"] == "у окна", hit)
check("слово под курсором — 'the'", hit and hit["word"] == "the", hit)

check("пословный набор помечен браком",
      glossary.looks_word_by_word([["Would", "было бы"], ["a", "а"], ["table", "стол"]]))
check("нормальный разбор браком НЕ считается",
      not glossary.looks_word_by_word(good))
check("длинный кусок разрешён (длина по смыслу)",
      glossary.covers("Would you like a table by the window",
                      [["Would you like a table by the window",
                        "хотели бы вы столик у окна"]]))
check("пропущенное слово — не покрывает",
      not glossary.covers(BAD_SENTENCE, [["Would you like", "хотели бы вы"],
                                         ["a table", "столик"]]))

# ---------------------------------------------------------
print("\n" + ("ИТОГ: провалов %d" % len(FAILED) if FAILED
              else "ИТОГ: все проверки пройдены"))
if FAILED:
    print("  " + ", ".join(FAILED))
sys.exit(1 if FAILED else 0)
