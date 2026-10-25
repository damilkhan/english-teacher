# -*- coding: utf-8 -*-
# =========================================================
# LESSON_SUMMARY.PY — итог ОБЫЧНОГО занятия (без Tk, модели и микрофона)
# =========================================================
# Зачем отдельный файл: итог нужен и в чате (текст по-русски), и в голосе
# (короткая похвала по-английски). Tk-модуль импортировать ради строк нельзя —
# тогда текст не проверить тестом без окна.
#
# Решения ученика (25.10.2026):
#   * итог показывается в КОНЦЕ занятия, по ходу — ничего (как у экзамена);
#   * НУЛИ показываем честно: «Подсказок: 0», «Ошибок: 0»;
#   * обычные занятия за подсказки НЕ наказывают (штраф — только экзамен);
#   * голосом читаем АНГЛИЙСКУЮ похвалу (цель проекта — говорение),
#     русский итог остаётся текстом: русские слова английским голосом
#     звучат мусором (см. tts.voice_for).
#
# Пороги похвалы по ошибкам разбора (одобрено 25.10.2026):
#   0 ошибок   → «Молодец, чисто!»
#   1–2 ошибки → «Хорошо! Пара ошибок — закрепим в следующем уроке»
#   3 и больше → «Есть что повторить — разберём в следующем уроке»
# =========================================================

from __future__ import annotations

# Границы похвалы по числу ошибок Аналитика.
CLEAN_MISTAKES = 0          # столько ошибок — «чисто»
FEW_MISTAKES = 2            # до этого включительно — «пара ошибок»


def _value(session, name, default=0):
    """Поле сессии: работает и с объектом, и со словарём (state())."""
    if session is None:
        return default
    if isinstance(session, dict):
        value = session.get(name, default)
    else:
        value = getattr(session, name, default)
    return default if value is None else value


def _count(session, name):
    """Число из сессии без падений на мусоре."""
    try:
        return max(0, int(_value(session, name, 0)))
    except (TypeError, ValueError):
        return 0


def mistake_note(mistakes) -> str:
    """Русская похвала по числу ошибок (пороги — решения ученика)."""
    try:
        count = max(0, int(mistakes))
    except (TypeError, ValueError):
        count = 0
    if count <= CLEAN_MISTAKES:
        return "👍 Молодец, чисто!"
    if count <= FEW_MISTAKES:
        return "👍 Хорошо! Пара ошибок — закрепим в следующем уроке."
    return "👍 Есть что повторить — разберём в следующем уроке."


def summary_text(session, block_title: str = "") -> str:
    """Итог обычного занятия для чата: балла тут нет, только счётчики.

    session — LessonSession (или её state() словарём);
    block_title — название блока, если он закрыт ЦЕЛИКОМ (иначе пусто).
    """
    lesson_id = str(_value(session, "lesson_id", "") or "").strip()
    replies = _count(session, "replies")
    target = _count(session, "target") or _count(session, "reply_target")
    hints = _count(session, "hints")
    mistakes = _count(session, "mistakes")

    head = "🎉 Урок %s пройден!" % lesson_id if lesson_id else "🎉 Урок пройден!"
    title = str(block_title or "").strip()
    if title:
        head += " Блок «%s» пройден целиком!" % title

    lines = [head]
    if target:
        lines.append("🗣 Реплик: %d из %d" % (replies, target))
    else:
        lines.append("🗣 Реплик: %d" % replies)
    lines.append("💡 Подсказок: %d" % hints)
    lines.append("📝 Ошибок: %d" % mistakes)
    lines.append(mistake_note(mistakes))
    return "\n".join(lines)


# Похвала для озвучки: ТОЛЬКО латиница и цифры — иначе английский голос
# (en-US-AvaMultilingualNeural) прочитает русские слова мусором.
PRAISE_CLEAN = "Perfect! %d replies and no mistakes at all. Well done!"
PRAISE_FEW = "Good job! %d replies and only %d %s. Keep it up!"
PRAISE_MANY = "Nice try! %d replies and %d %s. We will fix them next lesson."


def praise_text(session) -> str:
    """Короткая английская похвала для голоса (её же видно в чате)."""
    replies = _count(session, "replies")
    mistakes = _count(session, "mistakes")
    if mistakes <= CLEAN_MISTAKES:
        return PRAISE_CLEAN % replies
    word = "mistake" if mistakes == 1 else "mistakes"
    if mistakes <= FEW_MISTAKES:
        return PRAISE_FEW % (replies, mistakes, word)
    return PRAISE_MANY % (replies, mistakes, word)


def finish_messages(session, block_title: str = ""):
    """Два сообщения конца занятия: (русский итог, английская похвала)."""
    return (summary_text(session, block_title=block_title), praise_text(session))
