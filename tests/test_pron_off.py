# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_PRON_OFF.PY — сверка с эталоном в ЧАТЕ выключена (25.10.2026)
# =========================================================
#   python tests\test_pron_off.py
#
# Решение ученика (вариант А): подсказка «Попробуй ещё: ate вместо am,
# пропустил going» сравнивала реплику с ПРОШЛОЙ подсказкой переводчика и
# выбрасывала верный ответ (реплика не уходила в модель). Исправления
# предлагает только Вербот.
#
# Проверяем: флаг выключен, чат-сверка молчит даже при «живом» эталоне,
# а окно «Повторение» сверку НЕ теряет (оно ходит в pronunciation напрямую).
# =========================================================

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                      # noqa: E402
import pronunciation as pr         # noqa: E402
from ui.app import EnglishTeacherApp   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)


class FakeHintBar:
    """Полоса подсказки: запоминаем, что нам велели показать."""

    def __init__(self):
        self.notes = []
        self.statuses = []

    def show_note(self, text, english=""):
        self.notes.append((text, english))

    def show_status(self, text):
        self.statuses.append(text)


def make_app(pron_ref="", pron_at=0.0):
    """Приложение без Tk: нужны только поля сверки и полоса подсказки."""
    app = object.__new__(EnglishTeacherApp)
    app._pron_ref = pron_ref
    app._pron_at = pron_at
    app._pron_card = None
    app.hint_bar = FakeHintBar()
    return app


def test_flag():
    print("\n[1] Выключатель в config.py")
    check("PRON_CHECK_ENABLED есть в config", hasattr(config, "PRON_CHECK_ENABLED"))
    check("PRON_CHECK_ENABLED = False (решение 25.10.2026)",
          getattr(config, "PRON_CHECK_ENABLED", True) is False,
          getattr(config, "PRON_CHECK_ENABLED", None))


def test_remember_is_silent():
    print("\n[2] Эталон больше не запоминается")
    app = make_app()
    app._remember_pron_reference(["key — Open the door with this key."], True)
    check("_pron_ref пуст", app._pron_ref == "", app._pron_ref)
    check("_pron_at = 0", app._pron_at == 0.0, app._pron_at)
    app._remember_pron_reference("Open the door with this key.")
    check("фраза тоже не запоминается", app._pron_ref == "", app._pron_ref)


def test_stale_reference_is_ignored():
    print("\n[3] Живой случай: эталон есть, ответ верный — сверки НЕТ")
    # тот самый эталон из подсказки слова «лепешка»
    app = make_app(pron_ref="I'm going to eat flatbread", pron_at=time.monotonic())
    heard = "today i ate flatbread for breakfast and for lunch."
    report = app._pronunciation_report(heard)
    check("сверка не выполняется", report is None, report)
    sent = app._show_pronunciation(heard)
    check("реплику в диалог ПУСКАЕМ (False = отправить Верботу)", sent is False, sent)
    check("«Попробуй ещё» не показано", app.hint_bar.notes == [], app.hint_bar.notes)
    check("эталон не тронут (его и не читали)", app._pron_ref == "I'm going to eat flatbread",
          app._pron_ref)


def test_off_topic_also_passes():
    print("\n[4] Любая фраза проходит в диалог")
    for heard in ("i like flatbread", "yes", "flatbread for breakfast",
                  "I want to eat now"):
        app = make_app(pron_ref="Open the door with this key", pron_at=time.monotonic())
        check("«%s» → без сверки" % heard,
              app._show_pronunciation(heard) is False and not app.hint_bar.notes,
              app.hint_bar.notes)


def test_review_window_still_works():
    print("\n[5] Окно «Повторение» сверку НЕ потеряло (флаг не читает)")
    check("флага в pronunciation.py нет",
          "PRON_CHECK_ENABLED" not in open(
              os.path.join(ROOT, "pronunciation.py"), encoding="utf-8").read())
    good = pr.compare("Open the door with this key.", "open the door with this key")
    check("точный ответ → good", good.verdict == pr.GOOD, (good.verdict, good.score))
    almost = pr.compare("Open the door with this key.", "open the door with this keys")
    check("«keys» → almost", almost.verdict == pr.ALMOST,
          (almost.verdict, almost.score))
    try:
        from controllers.vocabulary_controller import VocabularyController
        check("VocabularyController импортируется и зовёт сверку",
              hasattr(VocabularyController, "answer"))
    except Exception as exc:                      # noqa: BLE001
        check("VocabularyController импортируется и зовёт сверку", False, exc)


def test_source_guards():
    print("\n[6] Вход в сверку закрыт флагом в обоих местах")
    src = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
    check("_remember_pron_reference читает флаг",
          "if not getattr(config, \"PRON_CHECK_ENABLED\", True):" in src)
    check("_pronunciation_report читает флаг",
          "or not self._pron_ref" in src)
    check("флаг стоит в одном месте (config.py)",
          src.count("PRON_CHECK_ENABLED = ") == 0)


def main():
    print("=" * 60)
    print("Проверка: сверка с эталоном в чате выключена")
    print("=" * 60)
    test_flag()
    test_remember_is_silent()
    test_stale_reference_is_ignored()
    test_off_topic_also_passes()
    test_review_window_still_works()
    test_source_guards()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
