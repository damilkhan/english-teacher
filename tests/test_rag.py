# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_RAG.PY — проверка rag.py (база знаний knowledge_base/)
# =========================================================
#   python tests\test_rag.py
#
# Проверяем:
#   1) поиск по англ. запросу находит нужный чанк и сортирует по score;
#   2) поиск по русскому запросу находит чанк из tutor_strategy_taxonomy;
#   3) пустой/бессмысленный запрос → пустой результат, без падения;
#   4) отсутствующий или битый index.json → «пустая база», без падения;
#   5) build_context собирает непустой контекст с разделителями;
#   6) текст извлекается для ВСЕХ чанков из index.json;
#   7) _match сравнивает слова по границам (без ложных подсовпадений);
#   8) стоп-слова не служат «мостом» между запросом и чанками.
# =========================================================

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# консоль Windows по умолчанию cp1251 — без этого падаем на эмодзи
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import rag  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def _ids(results):
    return [c["chunk_id"] for c in results]


def _files(results):
    return [c["file"] for c in results]


# =========================================================
# 1. Поиск по английскому запросу
# =========================================================
def test_search_motivation():
    print("\n[1] Поиск «motivation»")
    db = rag.RAG()
    res = db.search("motivation", top_k=5)
    check("нашёлся чанк tblt_motivation", "tblt_motivation" in _ids(res), _ids(res))
    check("результат непустой", len(res) > 0)
    check(
        "отсортировано по score (убывание)",
        all(res[i]["score"] >= res[i + 1]["score"] for i in range(len(res) - 1)),
        [c["score"] for c in res],
    )
    keys_ok = all(
        {"chunk_id", "file", "heading", "score"} <= set(c.keys()) for c in res
    )
    check("у результатов все поля (chunk_id/file/heading/score)", keys_ok)


# =========================================================
# 2. Поиск по русскому запросу (мост через заголовки чанков)
# =========================================================
def test_search_student_error():
    print("\n[2] Поиск «шкала вмешательства» (русский запрос по заголовку)")
    db = rag.RAG()
    res = db.search("шкала вмешательства", top_k=5)
    found = any(f.startswith("feedback/tutor_strategy_taxonomy") for f in _files(res))
    check("нашёлся чанк из tutor_strategy_taxonomy", found, _ids(res))
    check("это именно чанк tutor_ladder", "tutor_ladder" in _ids(res), _ids(res))


# =========================================================
# 3. Пустой запрос
# =========================================================
def test_empty_query():
    print("\n[3] Пустой запрос")
    db = rag.RAG()
    check("пустая строка → []", db.search("") == [])
    check("None → []", db.search(None) == [])
    check("только стоп-слова → []", db.search("и в на с по а но или") == [])
    check("пробелы → []", db.search("     ") == [])
    check("build_context('') → ''", db.build_context("") == "")


# =========================================================
# 4. Отсутствующий / битый index.json — «пустая база»
# =========================================================
def test_missing_index():
    print("\n[4] Нет index.json (пустая база)")
    tmp = tempfile.mkdtemp(prefix="rag_empty_")
    db = rag.RAG(base_path=tmp)
    check("search не падает и пуст", db.search("motivation") == [])
    check("build_context пуст", db.build_context("motivation") == "")
    chunk = {"file": "methodology/tblt_willis_1996.md", "heading": "2.3 Motivation"}
    check("load_chunk_text пуст", db.load_chunk_text(chunk) == "")
    check("load_chunk_text по пустому чанку пуст", db.load_chunk_text({}) == "")

    print("[4b] Битый index.json")
    with open(os.path.join(tmp, "index.json"), "w", encoding="utf-8") as fh:
        fh.write("{ это не json")
    db_broken = rag.RAG(base_path=tmp)
    check("битый index.json → поиск пуст", db_broken.search("motivation") == [])
    check("битый index.json → контекст пуст", db_broken.build_context("motivation") == "")


# =========================================================
# 5. build_context
# =========================================================
def test_build_context():
    print("\n[5] build_context")
    db = rag.RAG()
    ctx = db.build_context("motivation", top_k=2)
    check("непустая строка", isinstance(ctx, str) and len(ctx.strip()) > 0, len(ctx))
    check("есть разделитель блоков", "---" in ctx)
    check("есть текст чанка (слово 'motivation')", "motivation" in ctx.lower())
    check("пустой запрос → пустой контекст", db.build_context("") == "")


# =========================================================
# 6. Текст извлекается для ВСЕХ чанков из index.json
# =========================================================
def test_all_chunks_extractable():
    print("\n[6] Извлечение текста всех чанков")
    db = rag.RAG()
    index_path = os.path.join(ROOT, "knowledge_base", "index.json")
    with open(index_path, "r", encoding="utf-8") as fh:
        index = json.load(fh)

    total = 0
    bad = []
    for file_entry in index.get("files", []):
        for chunk in file_entry.get("chunks", []):
            total += 1
            text = db.load_chunk_text(
                {"file": file_entry["file"], "heading": chunk["heading"]}
            )
            first_line = text.splitlines()[0] if text else ""
            if not text or chunk["heading"].lower() not in first_line.lower():
                bad.append((chunk["id"], chunk["heading"]))

    check(f"все {total} чанков извлекаются без ошибок", not bad, bad)


# =========================================================
# 7. _match: границы слов (защита от ложных подсовпадений)
# =========================================================
def test_match_boundaries():
    print("\n[7] _match по границам слов")
    match = rag.RAG._match
    check("use / because → False", match("use", "because") is False)
    check("act / practice → False", match("act", "practice") is False)
    check("task / task-based → True", match("task", "task-based") is True)
    check("pre / pre-task → True", match("pre", "pre-task") is True)
    check("motivation / motivation → True", match("motivation", "motivation") is True)
    check("is / island → False (короткое слово не матчит)", match("is", "island") is False)
    check("пустые аргументы → False",
          match("", "task") is False and match("use", "") is False)


# =========================================================
# 8. Стоп-слова не служат «мостом» между запросом и чанками
# =========================================================
def test_stopwords_no_bridge():
    print("\n[8] Стоп-слова игнорируются")
    db = rag.RAG()
    check("запрос из одних RU-стоп-слов → []", db.search("что и для это как") == [])
    check("запрос из одних EN-стоп-слов → []",
          db.search("that this is are do be will can not so") == [])

def main():
    print("=" * 60)
    print("Проверка rag.py (knowledge_base)")
    print("=" * 60)

    test_search_motivation()
    test_search_student_error()
    test_empty_query()
    test_missing_index()
    test_build_context()
    test_all_chunks_extractable()
    test_match_boundaries()
    test_stopwords_no_bridge()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
