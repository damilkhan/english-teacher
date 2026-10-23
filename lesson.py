# -*- coding: utf-8 -*-
# =========================================================
# LESSON.PY — логика ЗАНЯТИЯ по карте (без Tk)
# =========================================================
# Здесь только «правила игры», без интерфейса и без модели:
#   * какие каналы ответа разрешены у урока (голос/текст);
#   * сколько реплик ученика нужно, чтобы занятие считалось отработанным;
#   * состояние сессии (идёт / завершено / прервано).
#
# ВАЖНО про термины (их легко перепутать):
#   * РЕЖИМ (mode) — как ведёт себя Джейн: "lesson" | "free" (это в config);
#   * ЗАНЯТИЕ (lesson session) — конкретный урок с карты (например «1.1»),
#     который ученик открыл из окна блока. Это ДРУГАЯ вещь.
#
# Типы уроков: speaking (только голос), chat (только текст),
# listening (только голос, Джейн начинает с аудио). mixed в UI не
# используется, оставлен только для совместимости данных.
#
# Модуль чистый: ни Tk, ни потоков — тестируется напрямую.
# =========================================================

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set, Tuple

_log = logging.getLogger(__name__)

# ---------- типы уроков ----------
SPEAKING = "speaking"
CHAT = "chat"
LISTENING = "listening"
# ПРОВЕРОЧНОЕ занятие в конце каждого блока: Джейн НЕ учит новому,
# а проверяет, закрепился ли материал блока (см. §8 снимка проекта).
CHECK = "check"
MIXED = "mixed"                 # не используем в UI (совместимость данных)

KNOWN_TYPES = (SPEAKING, CHAT, LISTENING, CHECK, MIXED)
DEFAULT_TYPE = SPEAKING

TYPE_LABELS = {
    SPEAKING: "говорение",
    CHAT: "текст",
    LISTENING: "аудирование",
    CHECK: "проверка",
    MIXED: "смешанный",
}

# Каналы ответа (наборы), по типам уроков.
_VOICE = {"voice"}
_TEXT = {"text"}

# ---------- сколько реплик — «занятие отработано» ----------
# Значение берём из config (одна точка настройки), с безопасным дефолтом.
try:
    import config as _config
    DEFAULT_REPLY_TARGET = max(1, int(getattr(_config, "LESSON_REPLY_TARGET", 12) or 12))
    # Проверка идёт дольше обычного урока: спрашиваем по всему блоку.
    CHECK_REPLY_TARGET = max(1, int(getattr(_config, "LESSON_CHECK_REPLY_TARGET", 16) or 16))
except Exception:                                     # pragma: no cover
    DEFAULT_REPLY_TARGET = 12
    CHECK_REPLY_TARGET = 16


# =========================================================
# Чистые функции по типу урока
# =========================================================
def normalize_type(value: Any) -> str:
    """Тип урока к одному из KNOWN_TYPES. Неизвестное/пустое → speaking."""
    name = str(value or "").strip().lower()
    return name if name in KNOWN_TYPES else DEFAULT_TYPE


def allowed_inputs(lesson_type: Any) -> Set[str]:
    """Какие каналы ответа разрешены: {'voice'}, {'text'} или оба.

    speaking / listening → только голос (главная цель проекта — говорение);
    chat → только текст; mixed → и голос, и текст.
    """
    name = normalize_type(lesson_type)
    if name == CHAT:
        return set(_TEXT)
    if name == MIXED:
        return set(_VOICE) | set(_TEXT)
    # speaking / listening / check — только голос
    return set(_VOICE)


def needs_microphone(lesson_type: Any) -> bool:
    """Нужен ли микрофон для этого урока."""
    return "voice" in allowed_inputs(lesson_type)


def needs_text(lesson_type: Any) -> bool:
    """Разрешён ли текстовый ввод на этом уроке."""
    return "text" in allowed_inputs(lesson_type)


def type_label(lesson_type: Any) -> str:
    """Человеческая подпись типа урока («говорение», «текст»…)."""
    return TYPE_LABELS.get(normalize_type(lesson_type), TYPE_LABELS[DEFAULT_TYPE])


# Что Джейн делает в САМОМ НАЧАЛЕ урока — зависит от типа.
# Для listening это «режим рассказа»: короткая история на уровне ученика,
# а потом просьба пересказать её (по-русски или по-английски).
OPENING_TASKS = {
    SPEAKING: ("Greet the student and give the FIRST small speaking task "
               "(one thing at a time)."),
    CHAT: ("Greet the student and ask the FIRST small written question "
           "(the student answers by typing)."),
    LISTENING: ("Tell a SHORT, simple story (5-7 short sentences) that fits "
                "the topic and the student's level. Tell it warmly, with a "
                "beginning and an ending. Then ask the student to RETELL what "
                "they heard — in Russian or in English, as they prefer."),
    CHECK: ("This is a CHECK lesson: the student has already finished all the "
            "lessons of this block. Do NOT teach anything new and do not "
            "explain rules. Ask ONE question at a time from this block's "
            "topics and let the student answer; keep each question short. "
            "If the answer is wrong, do not correct at once — first give one "
            "more chance with a simpler question. Near the end say in two "
            "sentences what went well and what needs practice."),
}


def opening_task(lesson_type: Any) -> str:
    """Инструкция для первой реплики урока (пусто для неизвестного типа)."""
    return OPENING_TASKS.get(normalize_type(lesson_type), "")


def is_story_lesson(lesson_type: Any) -> bool:
    """Урок-рассказ (аудирование): слушаем историю и пересказываем."""
    return normalize_type(lesson_type) == LISTENING


def is_check_lesson(lesson_type: Any) -> bool:
    """ПРОВЕРОЧНОЕ занятие в конце блока: не учим, а проверяем."""
    return normalize_type(lesson_type) == CHECK


def locked_hint(lesson_type: Any) -> str:
    """Подсказка в поле ввода во время урока «только голосом» (single source).

    Замок отнимает ОТПРАВКУ английского текста, но НЕ ввод: ученик может
    написать слово по-русски и получить перевод — ответить он всё равно
    должен вслух (решение ученика 23.10.2026).
    """
    name = normalize_type(lesson_type)
    if name == LISTENING:
        return "🎧 Слушай и отвечай голосом · слово по-русски → перевод"
    if name == CHECK:
        return "📝 Проверка: отвечай голосом · слово по-русски → перевод"
    return "🎤 Говори в микрофон · слово по-русски → перевод"


def voice_hint(lesson_type: Any) -> str:
    """Подсказка к кнопке записи для голосовых уроков."""
    name = normalize_type(lesson_type)
    if name == LISTENING:
        return "🎧 Ответь голосом"
    if name == CHECK:
        return "📝 Ответь голосом"
    return "🎤 Ответь голосом"


# =========================================================
# Сессия занятия
# =========================================================
class LessonSession:
    """Состояние одного занятия по карте (урок из окна блока).

    Считает реплики УЧЕНИКА: голос и текст одинаково. Когда набрано
    reply_target реплик — помечается завершённым. Если ученик вышел
    раньше — прервано (не засчитывается, но прогресс уже записан).
    """

    def __init__(self, lesson_id: str, point_id: Optional[str] = None,
                 lesson_type: Any = SPEAKING, title: str = "", topic: str = "",
                 block_number: Optional[int] = None, block_title: str = "",
                 reply_target: Optional[int] = None, code: str = "") -> None:
        self.lesson_id = str(lesson_id or "").strip()
        # code — короткий номер для экрана («1.1»). id уникален во всём
        # плане («forest/1.1»), но ученику такое показывать незачем.
        self.code = str(code or "").strip() or self.lesson_id
        self.point_id = str(point_id or "").strip() or None
        self.lesson_type = normalize_type(lesson_type)
        self.title = str(title or "").strip() or self.lesson_id
        self.topic = str(topic or "").strip() or self.title
        self.block_number = block_number
        self.block_title = str(block_title or "").strip()
        # 0 — это НЕ «нет значения»: явный лимит доводим до минимума 1,
        # а дефолт берём только когда лимит не задан вовсе (None).
        if reply_target is None:
            # проверочное занятие по умолчанию длиннее обычного урока
            target = (CHECK_REPLY_TARGET if self.lesson_type == CHECK
                      else DEFAULT_REPLY_TARGET)
        else:
            target = reply_target
        try:
            target = int(target)
        except (TypeError, ValueError):
            target = DEFAULT_REPLY_TARGET
        self.reply_target = max(1, target)

        self.replies = 0
        # Счётчики ДЛЯ ИТОГА занятия (решение ученика 23.10.2026: накопленное
        # не показываем по ходу, только в конце).
        #   hints    — подсказки переводчика, которые ученик ПРОИЗНЁС вслух;
        #   mistakes — сумма ошибок от Аналитика за занятие.
        self.hints = 0
        self.mistakes = 0
        self.finished = False
        self.aborted = False

    # ---------- свойства ----------
    @property
    def progress(self) -> Tuple[int, int]:
        """(реплик сделано, сколько нужно)."""
        return (self.replies, self.reply_target)

    @property
    def should_finish(self) -> bool:
        """Пора завершать (набрано достаточно реплик)."""
        return self.replies >= self.reply_target

    @property
    def is_active(self) -> bool:
        """Занятие идёт (не завершено и не прервано)."""
        return not (self.finished or self.aborted)

    # ---------- каналы ответа ----------
    def allowed_inputs(self) -> Set[str]:
        return allowed_inputs(self.lesson_type)

    def allows_voice(self) -> bool:
        return "voice" in self.allowed_inputs()

    def allows_text(self) -> bool:
        return "text" in self.allowed_inputs()

    def needs_microphone(self) -> bool:
        return needs_microphone(self.lesson_type)

    def locked_hint(self) -> str:
        return locked_hint(self.lesson_type)

    # ---------- счётчики для итога ----------
    def use_hint(self) -> int:
        """Ученик подглядел перевод И произнёс его вслух.

        Считаем ТОЛЬКО удачную подсказку (решение ученика): набранное слово,
        которое так и не прозвучало, подсказкой не считается. Возвращает
        новое число подсказок за занятие.
        """
        if self.is_active:
            self.hints += 1
        return self.hints

    def add_mistakes(self, count: int = 1) -> int:
        """Учесть ошибки разбора Аналитика (сумма за занятие)."""
        try:
            n = max(0, int(count))
        except (TypeError, ValueError):
            n = 0
        if self.is_active:
            self.mistakes += n
        return self.mistakes

    # ---------- ход занятия ----------
    def register_reply(self) -> Dict[str, Any]:
        """Учесть ОДНУ реплику ученика. Возвращает снимок состояния."""
        if not self.is_active:
            return self.state()
        self.replies += 1
        if self.replies >= self.reply_target:
            self.finished = True
        return self.state()

    def finish(self) -> None:
        """Завершить занятие успешно (дошёл до конца)."""
        self.finished = True
        self.aborted = False

    def abort(self) -> None:
        """Прервать занятие (ученик вышел раньше). НЕ засчитывается."""
        self.aborted = True
        self.finished = False

    # ---------- подписи ----------
    def label(self) -> str:
        """«Урок 1.1 · Hello / Hi» (короткий номер, без префикса локации)."""
        return "Урок %s · %s" % (self.code, self.title)

    def progress_text(self) -> str:
        """«4/12»."""
        return "%d/%d" % (self.replies, self.reply_target)

    def state(self) -> Dict[str, Any]:
        """Снимок состояния (для колбэков и тестов)."""
        return {
            "lesson_id": self.lesson_id,
            "code": self.code,
            "point_id": self.point_id,
            "type": self.lesson_type,
            "title": self.title,
            "replies": self.replies,
            "target": self.reply_target,
            "hints": self.hints,
            "mistakes": self.mistakes,
            "finished": self.finished,
            "aborted": self.aborted,
            "active": self.is_active,
        }
