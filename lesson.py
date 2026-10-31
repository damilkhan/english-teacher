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

import difflib
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

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
except Exception:                                     # pragma: no cover
    DEFAULT_REPLY_TARGET = 12
# Проверка блока = ЭКЗАМЕН: ровно 10 вопросов (решение ученика 24.10.2026).
# Число живёт в exam.py (там же балл и проходной), здесь только читаем —
# чтобы не было двух разных «10» в проекте.
try:
    import exam as _exam
    CHECK_REPLY_TARGET = max(1, int(_exam.QUESTIONS))
except Exception:                                     # pragma: no cover
    CHECK_REPLY_TARGET = 10

# ---------- задания внутри урока (§36, 26.10.2026) ----------
# Обычный урок = несколько маленьких заданий, каждое по циклу:
# дал задание → ученик ответил (с ошибкой) → исправил и попросил повторить →
# ученик повторил ВЕРНО → задание засчитано → сразу следующее.
# Значения берём из config (одна точка настройки), дефолт — безопасный.
try:
    TASKS_PER_LESSON = max(0, int(getattr(_config, "LESSON_TASKS", 3)))
except Exception:                                     # pragma: no cover
    TASKS_PER_LESSON = 3
try:
    MAX_TASK_ATTEMPTS = max(1, int(getattr(_config, "LESSON_TASK_ATTEMPTS", 3)))
except Exception:                                     # pragma: no cover
    MAX_TASK_ATTEMPTS = 3

# Фаза задания:
#   TASK_ASK  — задание дано, ждём первый ответ ученика;
#   TASK_FIX  — ответ с ошибкой, ждём ВЕРНЫЙ ПОВТОР исправления;
#   TASK_DONE — все задания сделаны (урок закрывается).
TASK_ASK = "ask"
TASK_FIX = "fix"
TASK_DONE = "done"
# §55 (31.10.2026): первое задание урока — ДРИЛЛ по ПРОШЛОЙ ошибке ученика.
# От «fix» отличается только тем, КТО попросил повтор: там ошибка случилась
# сейчас, здесь — пара «было -> стало» взята из базы ошибок (gaps.top_pair).
TASK_DRILL = "drill"

# Что вернул Аналитик про ответ ученика (вариант Б, §36).
ANSWER_CORRECT = "correct"      # ответ по заданию и без реальных ошибок
ANSWER_NEEDS_FIX = "needs_fix"  # пытался, но есть что исправлять
ANSWER_REPEAT_OK = "repeat_ok"  # это тот самый верный повтор исправления
ANSWER_UNCLEAR = "unclear"      # не понять (вопрос, комментарий, не по теме)
ANSWER_STATES = (ANSWER_CORRECT, ANSWER_NEEDS_FIX, ANSWER_REPEAT_OK,
                 ANSWER_UNCLEAR)

# Насколько похожим должен быть повтор (вариант В, без модели).
REPEAT_RATIO = 0.80
# §55: дрилл по ПРОШЛОЙ ошибке строже. «go to lay down» и «go to lie down»
# отличаются одной буквой (похожесть 0.87), поэтому обычный порог засчитывал
# бы ученику сам его старый неверный вариант.
DRILL_RATIO = 0.95


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


def allows_dictionary(lesson_type: Any, exam_lesson: Any = None) -> bool:
    """Работает ли словарь-подсказка на этом занятии.

    Обычный урок — работает: подсказка это учёба, за неё не наказывают.
    Экзамен (проверка блока) — НЕ работает: подсказок нет вообще
    (решение ученика 24.10.2026), иначе балл становится фиктивным.
    exam_lesson: True/False/None — уточнение от окна, если известно.
    """
    if exam_lesson is False:
        return True
    return not is_check_lesson(lesson_type)


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
        # ЭКЗАМЕН: подсказок нет вообще (решение ученика) — ни перевода,
        # ни вставки ↺. Слово по-русски здесь не просим.
        return "🎯 Экзамен: отвечай вслух по-английски · подсказок нет"
    return "🎤 Говори в микрофон · слово по-русски → перевод"


def voice_hint(lesson_type: Any) -> str:
    """Подсказка к кнопке записи для голосовых уроков."""
    name = normalize_type(lesson_type)
    if name == LISTENING:
        return "🎧 Ответь голосом"
    if name == CHECK:
        return "📝 Ответь голосом"
    return "🎤 Ответь голосом"


# ---------- задания: кто и как решает «сдано» (§36) ----------
def tasks_for(lesson_type: Any) -> int:
    """Сколько заданий в уроке: 0 — считаем по репликам, как раньше.

    Экзамен (check) и аудирование (listening) в цикл заданий НЕ входят:
    у экзамена свои 10 вопросов (exam.QUESTIONS, §30), у рассказа —
    пересказ целиком, его на «повтори фразу» не разложишь.
    """
    if normalize_type(lesson_type) in (CHECK, LISTENING):
        return 0
    return TASKS_PER_LESSON


def _flat(text: Any) -> str:
    """Текст без регистра, знаков и лишних пробелов — чтобы сравнивать «то же».

    Та же нормализация, что у Аналитика (roles/analyst.py): сравнение повтора
    не должно зависеть от точки в конце и большой буквы.
    """
    value = str(text or "").lower()
    keep = []
    for ch in value:
        keep.append(ch if (ch.isalnum() or ch == "'") else " ")
    return " ".join("".join(keep).split())


def says_fix(student_text: Any, corrections) -> bool:
    """Ученик ПОВТОРИЛ исправление? Проверка без модели (вариант В, §36).

    Быстрый путь: Аналитик уже назвал правильные куски (`errors[].correct`),
    мы их запомнили и сравниваем текст ученика:
      * правильный кусок есть в сказанном целиком («went» в «I went home»);
      * или фраза похожа на нужную (difflib ≥ REPEAT_RATIO) — на случай,
        когда просили повторить целое предложение.
    ВАЖНО: пустой список исправлений → False. Иначе зачёт был бы бесплатным.
    Ограничение честное: смысл не понимаем, поэтому синонимы («I'm gonna»)
    этот путь НЕ ловит — для них есть Аналитик (вариант Б).
    """
    said = _flat(student_text)
    if not said:
        return False
    wanted = [_flat(item) for item in (corrections or [])]
    wanted = [item for item in wanted if item]
    if not wanted:
        return False
    for want in wanted:
        if want in said:
            continue
        if difflib.SequenceMatcher(None, said, want).ratio() >= REPEAT_RATIO:
            continue
        return False
    return True


# =========================================================
# Сессия занятия
# =========================================================
class LessonSession:
    """Состояние одного занятия по карте (урок из окна блока).

    Считает реплики УЧЕНИКА: голос и текст одинаково. Когда набрано
    reply_target реплик — помечается завершённым. Если ученик вышел
    раньше — прервано (не засчитывается, но прогресс уже записан).

    С 26.10.2026 (§36) у обычного урока есть ещё ЗАДАНИЯ (tasks_total):
    урок закрывается, когда сданы ВСЕ задания, а счётчик реплик остаётся
    страховкой от зависания. Экзамен и аудирование живут по репликам.
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
        # ---------- задания (§36) ----------
        # tasks_total = 0 — урок считается по репликам, как раньше
        # (экзамен, аудирование, или LESSON_TASKS = 0).
        self.tasks_total = tasks_for(self.lesson_type)
        self.tasks_done = 0
        self.tasks_marked = 0        # сколько заданий засчитано «с подсказкой»
        self.task_attempts = 0       # неудачных повторов в ТЕКУЩЕМ задании
        self.task_phase = TASK_ASK if self.tasks_total else ""
        # что просили повторить (вариант В): правильные куски из разбора
        self.repeat_expected = []    # type: List[str]
        self.last_credited = ""      # текст, за который задание уже засчитано
        # §55: материал дрилла (что ученик сказал раньше и как надо)
        self.drill_wrong = ""
        self.drill_correct = ""

    # ---------- свойства ----------
    @property
    def progress(self) -> Tuple[int, int]:
        """(реплик сделано, сколько нужно)."""
        return (self.replies, self.reply_target)

    @property
    def hard_reply_limit(self) -> int:
        """Страховочный предел реплик для урока С ЗАДАНИЯМИ.

        reply_target (12) — это ПЛАН занятия. Раньше он же был обрывом: на
        12-й реплике урок закрывался, даже если ученик стоял посреди задания,
        и бот «сбегал» из темы (живой баг 26.10.2026: «скажи Hi иначе» → итог
        и фото). Теперь сверх плана есть запас (LESSON_HARD_REPLY_EXTRA):
        диалог не рвётся, но и бесконечным не становится.
        """
        if not self.has_tasks:
            return self.reply_target
        try:
            extra = max(0, int(getattr(_config, "LESSON_HARD_REPLY_EXTRA", 8)))
        except (TypeError, ValueError):
            extra = 8
        return self.reply_target + extra

    @property
    def should_finish(self) -> bool:
        """Пора завершать: все задания сданы ИЛИ набран страховочный предел.

        Для урока с заданиями лимит-план реплик НЕ закрывает занятие: иначе
        бот бросает текущее задание на полуслове. Экзамен и аудирование
        (заданий нет) живут по репликам, как раньше.
        """
        if self.has_tasks:
            return self.all_tasks_done or self.replies >= self.hard_reply_limit
        return self.replies >= self.reply_target

    @property
    def has_tasks(self) -> bool:
        """Урок считается по ЗАДАНИЯМ (а не по репликам)."""
        return self.tasks_total > 0

    @property
    def all_tasks_done(self) -> bool:
        """Все задания сданы."""
        return self.has_tasks and self.tasks_done >= self.tasks_total

    @property
    def task_index(self) -> int:
        """Номер ТЕКУЩЕГО задания (1..tasks_total); 0 — заданий нет."""
        if not self.has_tasks:
            return 0
        return min(self.tasks_total, self.tasks_done + 1)

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

    def allows_dictionary(self) -> bool:
        """Можно ли подсказку-перевод (на экзамене — нельзя)."""
        return allows_dictionary(self.lesson_type)

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
        # Урок С ЗАДАНИЯМИ закрывает ПРИЛОЖЕНИЕ — после ответа и зачёта
        # задания. Если закрыть здесь, `is_active` станет False и зачёт
        # последнего задания не сработает: ученик отвечает верно, а в итоге
        # «Заданий: 2 из 3» (живой баг 26.10.2026).
        if self.has_tasks:
            return self.state()
        # ЭКЗАМЕН закрывает НЕ счётчик реплик, а _finish_exam() в окне — уже
        # ПОСЛЕ разбора Аналитика: там считается балл последнего ответа.
        # Раньше сессия закрывалась прямо здесь на 10-й реплике — окно
        # видело урок без итога экзамена и показывало ОБЫЧНЫЙ итог плюс
        # фото-задание (живой баг 31.10.2026), а модель успевала задать
        # лишний вопрос: флаг «реплика закрывает урок» уже не ставился.
        if self.lesson_type == CHECK:
            return self.state()
        # аудирование живёт по репликам — как раньше
        if self.should_finish:
            self.finished = True
        return self.state()

    # ---------- задания (§36) ----------
    def start_drill(self, wrong, correct) -> bool:
        """Первое задание урока = ДРИЛЛ по прошлой ошибке ученика (§55).

        Материал готовый: пара «было -> стало» из базы ошибок
        (gaps.top_pair). Модель ничего не придумывает — она только просит
        повторить. Зачёт по тексту (says_fix), как в фазе «fix», поэтому
        ложных зачётов нет. Урок остаётся про свою тему: дрилл занимает
        ТОЛЬКО первое из трёх заданий.
        """
        want = str(correct or "").strip()
        if not want or not self.is_active or not self.has_tasks:
            return False
        self.drill_wrong = str(wrong or "").strip()
        self.drill_correct = want
        self.repeat_expected = [want]
        self.task_phase = TASK_DRILL
        self.task_attempts = 0
        return True

    def expect_repeat(self, corrections) -> List[str]:
        """Запомнить, что просили повторить, и перейти в фазу «ждём повтор».

        corrections — правильные куски из разбора Аналитика
        (`errors[].correct`). Пустой список тоже переводит в фазу «ждём
        повтор»: сравнивать будет нечего (вариант В молчит), но попытки
        считаются и через MAX_TASK_ATTEMPTS задание засчитается с пометкой.
        """
        if not self.is_active or not self.has_tasks:
            return []
        items = []                                    # type: List[str]
        for raw in (corrections or []):
            text = str(raw or "").strip()
            if text and text not in items:
                items.append(text)
        self.repeat_expected = items
        self.task_phase = TASK_FIX
        self.task_attempts = 0
        return items

    def says_fix(self, student_text: Any) -> bool:
        """Ученик повторил исправление? Мгновенно, без модели (вариант В)."""
        if self.task_phase not in (TASK_FIX, TASK_DRILL):
            return False
        if self.task_phase == TASK_DRILL and self.drill_correct:
            # §55: фраза должна совпасть почти точно, а СТАРАЯ ошибка в
            # сказанном не должна звучать (иначе дрилл засчитывает сам промах)
            said = _flat(student_text)
            want = _flat(self.drill_correct)
            wrong = _flat(self.drill_wrong)
            if not said:
                return False
            if want in said:
                return True
            if wrong and wrong in said:
                return False
            return difflib.SequenceMatcher(None, said, want).ratio() >= DRILL_RATIO
        return says_fix(student_text, self.repeat_expected)

    def note_task_attempt(self) -> int:
        """Ещё один неудачный повтор. Возвращает их число в задании."""
        if self.is_active and self.has_tasks:
            self.task_attempts += 1
        return self.task_attempts

    def already_credited(self, student_text: Any) -> bool:
        """За ЭТУ реплику задание уже засчитали (защита от двойного зачёта).

        Нужна потому, что зачёт приходит ДВАЖДЫ: сразу по тексту (вариант В,
        до ответа учителя) и позже разбором Аналитика (вариант Б).
        """
        return bool(self.last_credited) and _flat(student_text) == self.last_credited

    def credit_task(self, student_text: Any = "", marked: bool = False) -> Dict[str, Any]:
        """Засчитать ТЕКУЩЕЕ задание и перейти к следующему.

        marked=True — засчитано «с подсказкой»: ученик так и не повторил
        верно (MAX_TASK_ATTEMPTS попыток), но урок держать открытым нельзя.
        После последнего задания сессия сразу считается завершённой.
        """
        if not self.is_active or not self.has_tasks:
            return self.state()
        if self.already_credited(student_text):
            return self.state()
        self.tasks_done += 1
        if marked:
            self.tasks_marked += 1
        self.last_credited = _flat(student_text)
        self.repeat_expected = []
        self.task_attempts = 0
        self.drill_wrong = ""
        self.drill_correct = ""
        if self.all_tasks_done:
            self.task_phase = TASK_DONE
            self.finished = True
        else:
            self.task_phase = TASK_ASK
        return self.state()

    def credit_rest(self, marked: bool = True) -> int:
        """Засчитать НЕДОДЕЛАННЫЕ задания, когда урок упирается в предел.

        Живой баг 26.10.2026: урок закрылся по страховочному пределу реплик,
        в итоге «Заданий: 2 из 3», а блок всё равно засчитан — цифры не
        сходились. Решение ученика (вариант Б): остаток засчитываем С
        ПОМЕТКОЙ «с подсказкой». Тогда в итоге честно «3 из 3
        (с подсказкой: 1)», и урок не застревает навсегда.

        Возвращает, сколько заданий добрали.
        """
        if not self.is_active or not self.has_tasks:
            return 0
        added = 0
        # потолок — сами задания: защита от бесконечного цикла
        while not self.all_tasks_done and added <= self.tasks_total:
            before = self.tasks_done
            self.credit_task("", marked=marked)
            if self.tasks_done == before:
                break
            added += 1
        return added


    def task_prompt(self) -> Dict[str, Any]:
        """Что рассказать модели про задания (пусто — заданий нет).

        Словарь уходит в промпт урока (`prompt_builder._lesson_block`).
        Для экзамена и аудирования он ПУСТОЙ — промпт там прежний.
        """
        if not self.has_tasks:
            return {}
        payload = {
            "tasks_total": self.tasks_total,
            "tasks_done": self.tasks_done,
            "task_index": self.task_index,
            "task_phase": self.task_phase,
            "repeat_expected": ", ".join(self.repeat_expected),
        }
        # §55: в фазе дрилла промпту нужно, ЧТО ученик сказал неправильно
        if self.task_phase == TASK_DRILL and self.drill_wrong:
            payload["drill_wrong"] = self.drill_wrong
        return payload

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
        """Счётчик для полосы урока: «Задание 2/3» или «4/12».

        Урок с заданиями показывает ЗАДАНИЯ (решение ученика 26.10.2026:
        задания не должны считаться по репликам). Экзамен, аудирование и
        урок с LESSON_TASKS = 0 — по-прежнему реплики.
        """
        if self.has_tasks:
            return "Задание %d/%d" % (self.task_index, self.tasks_total)
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
            "tasks_total": self.tasks_total,
            "tasks_done": self.tasks_done,
            "tasks_marked": self.tasks_marked,
            "task_index": self.task_index,
            "task_phase": self.task_phase,
            "repeat_expected": list(self.repeat_expected),            "hints": self.hints,
            "mistakes": self.mistakes,
            "exam": self.lesson_type == CHECK,
            "dictionary": allows_dictionary(self.lesson_type),
            "finished": self.finished,
            "aborted": self.aborted,
            "active": self.is_active,
        }
