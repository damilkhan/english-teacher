# -*- coding: utf-8 -*-
# =========================================================
# VOCABULARY_CONTROLLER.PY — логика окна «Повторение» (этап B)
# =========================================================
# Что делает: собирает слова на сегодня (vocabulary.due_cards), проверяет
# ответ ученика сверкой произношения (pronunciation.py) и двигает уровень
# карточки в файле прогресса (profile_store).
#
# Окно (ui/panels/vocab_panel.py) только показывает: слово, пример с
# пропуском, кнопки. Вся «арифметика» — здесь, поэтому её можно проверить
# тестом без Tk и без микрофона.
#
# ПРАВИЛА (договорены):
#   • удачный ответ = вердикт GOOD («✅ Похоже!») → уровень +1;
#   • промах («🟡 Почти» / «🔁 Попробуй») → уровень НЕ меняется (решение 53),
#     только «спросить завтра»; уровень двигает ТОЛЬКО удачный ответ;
#   • ПОДСКАЗКА = промах: слово не вспомнилось само;
#   • «Позже» → ничего не меняется, слово вернётся в следующий раз;
#   • ОДИН итог на карточку за заход: первый результативный ответ двигает
#     уровень, дальше ученик может повторять для тренировки — уровень
#     больше не шевелится (иначе выходило бы «−1, потом +1» и лестница
#     теряла бы смысл);
#   • новые слова (решение 54): за заход до config.VOCAB_NEW_PER_DAY слов
#     из ТЕКУЩЕЙ темы (bank data/words_<уровень>.json); тема = первый
#     несданный блок карты (его «Проверка» не записана как сданная);
#   • повторы делятся на корзины: текущая тема / пройденные темы /
#     «трудные» (промахов ≥ 2) — см. vocabulary.pick_mix;
#   • сказал по-русски — это НЕ ответ: показываем перевод, ждём английский.
#
# Сверяем ответ с ДВУМЯ эталонами (пример и само слово) и берём лучший:
# «key» и «Open the door with this key.» — оба правильные.
# =========================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pronunciation
import profile_store
import vocabulary
import word_bank

# Насколько «хорош» вердикт — чтобы выбрать лучший из нескольких эталонов.
_VERDICT_RANK = {
    pronunciation.GOOD: 3,
    pronunciation.ALMOST: 2,
    pronunciation.OFF: 1,
    pronunciation.UNRELATED: 0,
}


# Карта курса нужна, чтобы найти текущий блок и его «Проверку».
# Читаем один раз на процесс: файл 50 КБ, но зачем его читать каждый заход.
_WORD_MAP = None


def _word_map():
    """Карта курса (progress_map.ProgressMap) или None, если не вышло."""
    global _WORD_MAP
    if _WORD_MAP is None:
        try:
            import progress_map
            _WORD_MAP = progress_map.ProgressMap()
        except Exception as exc:
            print("⚠️ Карта курса не прочитана: %s" % exc)
            _WORD_MAP = False
    return _WORD_MAP or None


class VocabularyController:
    """Заход повторения: очередь слов, ответы, уровни, итог.

    store — объект с методами vocabulary_cards / update_vocabulary_card /
    mark_vocab_session (по умолчанию profile_store; в тестах — подделка).
    today — дата «стенда» для тестов (по умолчанию настоящая).
    cards — готовый список карточек (тесты); иначе читаем из профиля.
    """

    def __init__(self, store=None, user_id=None, today=None, cards=None):
        self.store = store if store is not None else profile_store
        self.user_id = user_id
        self._today = today
        self._cards = cards
        self._queue: List[Dict[str, Any]] = []
        self._index = -1
        self._graded = False      # по текущей карточке уже был итог
        self._touched = False     # заход отмечен в профиле (не чаще раза)
        self._stats = {"shown": 0, "good": 0, "miss": 0, "skipped": 0}

    # -----------------------------------------------------
    # Заход
    # -----------------------------------------------------
    def start(self, cards=None) -> List[Dict[str, Any]]:
        """Собрать заход: новые слова темы + повторы по корзинам.

        Возвращает очередь (список «снимков» карточек для окна). Новые
        карточки сразу пишутся в профиль — иначе окно покажет слово,
        которого в профиле нет, и ответ некуда будет записать.
        """
        self._index = -1
        self._graded = False
        self._touched = False
        self._stats = {"shown": 0, "good": 0, "miss": 0, "skipped": 0, "new": 0}
        source = cards if cards is not None else self._source_cards()
        theme = self._theme() if self._bank_ready() else ""
        candidates = self._new_candidates(theme)
        left = max(0, vocabulary.new_per_day() - vocabulary.created_today(source, self._today))
        queue, fresh = vocabulary.pick_mix(source, candidates, theme=theme,
                                          today=self._today, new_limit=left)
        if fresh:
            self._save_new(fresh)
        self._queue = [self._snapshot(card) for card in queue]
        fresh_keys = {vocabulary.card_key(c.get("word"), c.get("en")) for c in fresh}
        for snap in self._queue:
            if fresh_keys and vocabulary.card_key(snap.get("word"), snap.get("en")) in fresh_keys:
                snap["is_new"] = True
        self._stats["shown"] = len(self._queue)
        self._stats["new"] = len(fresh)
        self._theme_id = theme
        self._index = 0 if self._queue else -1
        return list(self._queue)

    # -----------------------------------------------------
    # Тема и банк слов (решение 54)
    # -----------------------------------------------------
    def _profile(self) -> dict:
        """Профиль-прогресс (уровень и сданные проверки). Ошибки → {}."""
        try:
            return self.store.load(self.user_id) or {}
        except Exception:
            return {}

    def _theme(self) -> str:
        """Текущая тема: первый несданный блок карты уровня ученика."""
        try:
            profile = self._profile()
            level = word_bank.student_level(profile)
            return word_bank.current_theme(profile, _word_map(), level)
        except Exception as exc:
            print("⚠️ Тема не определена: %s" % exc)
            return ""

    def _new_candidates(self, theme) -> List[dict]:
        """Слова для новых карточек: текущая тема, при нехватке — следующая."""
        if not theme:
            return []
        try:
            profile = self._profile()
            level = word_bank.student_level(profile)
            words = word_bank.words_for_new(profile, _word_map(), level)
        except Exception as exc:
            print("⚠️ Банк слов не прочитан: %s" % exc)
            return []
        return [vocabulary.card_for_word(item, self._today) for item in words]

    def _save_new(self, fresh) -> None:
        """Записать новые карточки в профиль (молча, если стор не умеет)."""
        save = getattr(self.store, "add_vocabulary_cards", None)
        if not callable(save):
            return
        try:
            save(fresh, self.user_id)
        except Exception as exc:
            print("⚠️ Новые слова не записаны: %s" % exc)

    @property
    def theme(self) -> str:
        """Тема текущего захода (пусто — банка нет, тема неизвестна)."""
        return getattr(self, "_theme_id", "") or ""

    def has_material(self) -> bool:
        """Есть ли что спросить: созревшие слова ИЛИ новые из банка."""
        try:
            source = self._source_cards()
            if vocabulary.due_cards(source, today=self._today, limit=0):
                return True
            theme = self._theme() if self._bank_ready() else ""
            if not theme:
                return False
            left = vocabulary.new_per_day() - vocabulary.created_today(source, self._today)
            return left > 0 and bool(self._new_candidates(theme))
        except Exception:
            return False

    def _bank_ready(self) -> bool:
        """Банк слов работает, только если стор умеет сохранять карточки.

        Это защита: тестовые подделки профиля (только чтение) не должны
        молча заводить новые слова, которых потом некуда записать.
        """
        return callable(getattr(self.store, "add_vocabulary_cards", None))

    def _source_cards(self) -> List[dict]:
        if self._cards is not None:
            return self._cards
        try:
            return self.store.vocabulary_cards(self.user_id)
        except Exception as exc:
            print("⚠️ Слова не прочитаны: %s" % exc)
            return []
    @staticmethod
    def _snapshot(card) -> Dict[str, Any]:
        """Что нужно окну: только данные, без связи с файлом."""
        return {
            "word": str(card.get("word") or ""),
            "en": str(card.get("en") or ""),
            "example": str(card.get("example") or ""),
            "gap": vocabulary.example_with_gap(card),
            "level": vocabulary.level_of(card),
        }



    # -----------------------------------------------------
    # Текущая карточка
    # -----------------------------------------------------
    @property
    def is_active(self) -> bool:
        return 0 <= self._index < len(self._queue)

    def current(self) -> Optional[Dict[str, Any]]:
        return self._queue[self._index] if self.is_active else None

    def next(self) -> bool:
        """Следующее слово. True — есть ещё, False — заход закончен."""
        self._index += 1
        self._graded = False
        return self.is_active

    def graded(self) -> bool:
        """По текущей карточке итог уже есть (её уровень больше не меняем)."""
        return self._graded

    # -----------------------------------------------------
    # Ответы ученика
    # -----------------------------------------------------
    def answer(self, text) -> Dict[str, Any]:
        """Проверить произнесённое вслух.

        status: good | miss | russian | unrelated | empty | no_card.
        Уровень двигается ТОЛЬКО при первом итоге по карточке.
        """
        card = self.current()
        if card is None:
            return {"status": "no_card"}
        heard = str(text or "").strip()
        if not heard:
            return {"status": "empty"}
        if pronunciation.has_cyrillic(heard):
            return {"status": "russian", "heard": heard, "en": card["en"]}
        report = self._best_report(card, heard)
        if report.verdict == pronunciation.UNRELATED:
            return {"status": "unrelated", "report": report, "heard": heard,
                    "en": card["en"], "example": card["example"]}
        success = (report.verdict == pronunciation.GOOD)
        first = not self._graded
        before, after, changed = self._grade(success)
        if first and changed:
            self._stats["good" if success else "miss"] += 1
        return {
            "status": "good" if success else "miss",
            "verdict": report.verdict,
            "report": report,
            "heard": heard,
            "level_from": before,
            "level_to": after,
            "changed": changed,
            "learned": after >= vocabulary.LEARNED,
        }

    def reveal(self) -> Dict[str, Any]:
        """Кнопка «Подсказка»: показать ответ и засчитать промах."""
        card = self.current()
        if card is None:
            return {"status": "no_card"}
        first = not self._graded
        before, after, changed = self._grade(False)
        if first and changed:
            self._stats["miss"] += 1
        return {
            "status": "hint",
            "en": card["en"],
            "example": card["example"],
            "level_from": before,
            "level_to": after,
            "changed": changed,
        }

    def skip(self) -> Optional[Dict[str, Any]]:
        """Кнопка «Позже»: ни уровня, ни даты не трогаем."""
        card = self.current()
        if card is None:
            return None
        self._graded = True          # после «Позже» ответы уже ничего не меняют
        self._touch()
        self._stats["skipped"] += 1
        return dict(card)

    # -----------------------------------------------------
    # Итог
    # -----------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        """Сводка захода для финального экрана окна."""
        return dict(self._stats)

    @property
    def total(self) -> int:
        return len(self._queue)

    @property
    def position(self) -> int:
        """Номер текущего слова (1..N); 0 — заход ещё не начат."""
        return self._index + 1 if self.is_active else len(self._queue)

    # -----------------------------------------------------
    # Внутреннее
    # -----------------------------------------------------
    @staticmethod
    def _best_report(card, heard):
        """Лучший вердикт из эталонов карточки.

        Эталоны: пример, само слово и СИНОНИМЫ («привет» → hey/hi/hello).
        Синоним, который ученик произнёс, — такой же верный ответ.
        """
        best = None
        references = list(vocabulary.reference_texts(card))
        references += vocabulary.alternatives(card)
        for reference in references:
            try:
                report = pronunciation.compare(reference, heard)
            except Exception as exc:
                print("⚠️ Сверка не удалась (%s): %s" % (reference, exc))
                continue
            if best is None or _VERDICT_RANK.get(report.verdict, 0) > _VERDICT_RANK.get(best.verdict, 0):
                best = report
            elif (_VERDICT_RANK.get(report.verdict, 0) == _VERDICT_RANK.get(best.verdict, 0)
                    and report.score > best.score):
                best = report
        if best is None:
            # сверять не с чем — считаем, что ученик сказал своё (молчим)
            return pronunciation.Report(reference="", heard=heard,
                                        verdict=pronunciation.UNRELATED)
        return best

    def _grade(self, success):
        """Записать итог по карточке → (было, стало, записано?).

        «Записано?» — True, если в профиле что-то сохранилось. Промах
        уровень НЕ меняет (решение 53), но дату вопроса переносит —
        это тоже запись.
        """
        card = self.current()
        before = card["level"]
        if self._graded:
            return before, before, False
        self._graded = True
        self._touch()
        try:
            updated = self.store.update_vocabulary_card(
                card["word"], card["en"], success, self.user_id)
        except Exception as exc:
            print("⚠️ Итог слова не записан: %s" % exc)
            return before, before, False
        if updated is None:
            return before, before, False
        after = vocabulary.level_of(updated)
        card["level"] = after
        return before, after, True

    def _touch(self):
        """Первый ответ в заходе → отметить дату в профиле (не чаще раза)."""
        if self._touched:
            return
        self._touched = True
        try:
            self.store.mark_vocab_session(user_id=self.user_id)
        except Exception as exc:
            print("⚠️ Дата повторения не записана: %s" % exc)
