# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_GLOSSARY.PY — переводы по наведению (без экрана)
# =========================================================
#   python tests\test_glossary.py
#
# ЗАЧЕМ. Решение ученика (25.10.2026): подсказка-перевод появляется ТОЛЬКО
# по наведению курсора на английское слово в реплике Вербота. Устойчивые
# выражения (look forward to) переводятся одним куском по смыслу.
# Производительность: наведение модель НЕ трогает — только файловый кэш.
#
# Проверяем:
#   1) токены: апострофы/знаки, word_at попадает в слово;
#   2) lookup: слово, выражение важнее слова, курсор на 2-м слове фразы;
#   3) prime: разобранное кладётся в кэш, повторный разбор — 0 запросов;
#   4) битый JSON → повтор один раз; совсем мусор → (False, причина);
#   5) файл кэша: сохраняется и читается обратно (второй запуск бесплатен).
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


ANSWER = json.dumps({"items": [
    {"en": "Look forward to", "ru": "с нетерпением ждать", "phrase": True},
    {"en": "seeing", "ru": "видеть", "phrase": False},
    {"en": "you", "ru": "тебя", "phrase": False},
    {"en": "there", "ru": "там", "phrase": False},
]}, ensure_ascii=False)

COVERED = "Look forward to seeing you there"       # все слова есть в ANSWER


class FakeLLM:
    """Заглушка модели: считает вызовы и отдаёт заранее заданные ответы."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0
        self.last_timeout = None

    def complete(self, messages, max_tokens=None, temperature=None,
                 stop=None, timeout=60):
        self.calls += 1
        self.last_timeout = timeout
        if not self.answers:
            return False, "нет заготовки"
        return True, self.answers.pop(0)


def tmp_path(folder):
    return os.path.join(folder, "glossary.json")


# ---------------------------------------------------------
print("[1] Токены и попадание курсора в слово")
sentence = "Look forward to seeing you there, Damil! Don\u2019t forget."
tokens = glossary.tokenize(sentence)
keys = [t["key"] for t in tokens]
check("слова найдены по порядку", keys[:4] == ["look", "forward", "to", "seeing"], keys[:4])
check("апостроф-ёлочка приведён к обычному", "don't" in keys, keys[-3:])
check("знаки не попали в слова",
      all(t["key"].replace("'", "").isalpha() for t in tokens), keys)
check("normalize снимает запятую и регистр",
      glossary.normalize("  Hello, ") == "hello", glossary.normalize("  Hello, "))

token = glossary.word_at(sentence, 2)
check("word_at(2) = 'Look'", token and token["key"] == "look", token)
check("word_at на пробеле = None",
      glossary.word_at(sentence, 4) is None, glossary.word_at(sentence, 4))
check("word_at на кириллице = None",
      glossary.word_at("Привет hello", 3) is None)

# ---------------------------------------------------------
print("\n[2] Подсказка по наведению (без модели)")
folder = tempfile.mkdtemp()
gl = glossary.Glossary(llm=None, path=tmp_path(folder))
gl.add(glossary.parse_items(ANSWER))

hit = gl.lookup(sentence, 2)
check("слово 'Look' → фраза целиком", hit and hit["en"] == "Look forward to", hit)
check("перевод фразы по смыслу", hit and hit["ru"] == "с нетерпением ждать", hit)
check("фраза помечена phrase=True", hit and hit["phrase"] is True, hit)
check("границы фразы 0…15", hit and hit["start"] == 0 and hit["end"] == 15, hit)

hit2 = gl.lookup(sentence, 9)          # курсор на 2-м слове фразы ('forward')
check("курсор на 2-м слове даёт ту же фразу",
      hit2 and hit2["en"] == "Look forward to", hit2)

hit3 = gl.lookup(sentence, 20)         # 'seeing'
check("отдельное слово вне фразы", hit3 and hit3["en"] == "seeing"
      and hit3["ru"] == "видеть", hit3)

check("незнакомое слово → None (модель не зовём)",
      gl.lookup("Elephant", 1) is None)
check("кириллица → None", gl.lookup("Привет hello", 8) is None)
check("stats: попадание посчитано", gl.stats["hits"] == 3, gl.stats)

# ---------------------------------------------------------
print("\n[3] prime: модель зовётся ровно один раз на реплику")
llm = FakeLLM([ANSWER])
gl2 = glossary.Glossary(llm=llm, path=tmp_path(tempfile.mkdtemp()))
ok, added = gl2.prime(COVERED)
check("первый разбор удался", ok is True, (ok, added))
check("пар добавлено 4", added == 4, added)
check("вызовов модели 1", llm.calls == 1, llm.calls)
check("таймаут передан в модель", llm.last_timeout == 120, llm.last_timeout)

ok, added2 = gl2.prime(COVERED)
check("повторный разбор без модели", ok is True and added2 == 0, (ok, added2))
check("вызовов модели по-прежнему 1", llm.calls == 1, llm.calls)

# ---------------------------------------------------------
print("\n[4] Битый JSON: один повтор, потом честный провал")
llm3 = FakeLLM(["{\"items\":[{\"en\":\"hi\",\"ru\":\"привет\",", ANSWER])
gl3 = glossary.Glossary(llm=llm3, path=tmp_path(tempfile.mkdtemp()))
ok, added = gl3.prime(COVERED)
check("после повтора разбор удался", ok is True and added == 4, (ok, added))
check("вызовов модели 2", llm3.calls == 2, llm3.calls)
check("повтор посчитан", gl3.stats["retries"] == 1, gl3.stats)

llm4 = FakeLLM(["мусор", "тоже мусор"])
gl4 = glossary.Glossary(llm=llm4, path=tmp_path(tempfile.mkdtemp()))
ok, reason = gl4.prime("Something unclear")
check("мусор → (False, причина)", ok is False and "JSON" in reason, (ok, reason))
check("провал посчитан", gl4.stats["failed"] == 1, gl4.stats)

gl5 = glossary.Glossary(llm=None, path=tmp_path(tempfile.mkdtemp()))
ok, reason = gl5.prime("Hello there")
check("нет модели → (False, 'нет модели')", ok is False and reason == "нет модели",
      (ok, reason))
check("пустая реплика → (False, 'нечего разбирать')",
      gl5.prime("   ")[1] == "нечего разбирать")

# ---------------------------------------------------------
print("\n[5] Файл кэша: второй запуск бесплатен")
folder5 = tempfile.mkdtemp()
gl6 = glossary.Glossary(llm=FakeLLM([ANSWER]), path=tmp_path(folder5))
gl6.prime(COVERED)
check("файл появился", os.path.exists(tmp_path(folder5)), tmp_path(folder5))
saved = json.load(open(tmp_path(folder5), encoding="utf-8"))
check("в файле 3 слова и 1 фраза",
      len(saved["words"]) == 3 and len(saved["phrases"]) == 1,
      (len(saved["words"]), len(saved["phrases"])))
check("ключ фразы через |", "look|forward|to" in saved["phrases"], saved["phrases"])

llm7 = FakeLLM([])
gl7 = glossary.Glossary(llm=llm7, path=tmp_path(folder5))
hit = gl7.lookup(sentence, 2)
check("новый объект читает кэш с диска",
      hit and hit["ru"] == "с нетерпением ждать", hit)
ok, added = gl7.prime(COVERED)
check("повторный разбор из кэша — без модели",
      ok is True and added == 0 and llm7.calls == 0, (ok, added, llm7.calls))

gl8 = glossary.Glossary(llm=None, path=os.path.join(tempfile.mkdtemp(), "нет.json"))
check("нет файла — не падаем", gl8.words == {} and gl8.phrases == {}, gl8.words)

# ---------------------------------------------------------
print("\n[6] Разбор ответа модели")
check("```json и текст вокруг — разбираются",
      len(glossary.parse_items("Вот словарь:\n```json\n" + ANSWER + "\n```")) == 4)
check("null/пусто → []", glossary.parse_items("") == []
      and glossary.parse_items(None) == [])
check("без ключа items → []", glossary.parse_items('{"data": []}') == [])
check("пары без ru отбрасываются",
      glossary.parse_items('{"items":[{"en":"hi","ru":""},{"en":"yes","ru":"да"}]}') ==
      [{"en": "yes", "ru": "да", "phrase": False}])

# ---------------------------------------------------------
print("\n[7] Защита от «слишком широких» выражений (замер 25.10.2026)")
gl9 = glossary.Glossary(llm=None, path=tmp_path(tempfile.mkdtemp()))
added = gl9.add([
    {"en": "look forward to seeing you there", "ru": "с нетерпением жду", "phrase": True},
    {"en": "your umbrella", "ru": "твой зонт", "phrase": True},
    {"en": "look forward to", "ru": "с нетерпением ждать", "phrase": True},
])
check("осталась только законная фраза", added == 1 and len(gl9.phrases) == 1,
      (added, list(gl9.phrases)))
check("6 слов и притяжательное отброшены (2 из 3)",
      gl9.stats["rejected"] == 2, gl9.stats)

check("подсказка на 'umbrella' пуста (слово не в кэше)",
      gl9.lookup("Don't forget your umbrella", 20) is None)

# ---------------------------------------------------------
print("\n" + ("ИТОГ: провалов %d" % len(FAILED) if FAILED
              else "ИТОГ: все проверки пройдены"))
if FAILED:
    print("  " + ", ".join(FAILED))
sys.exit(1 if FAILED else 0)
