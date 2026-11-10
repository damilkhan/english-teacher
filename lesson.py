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

try:
    import phrases                    # библиотека смысловых пар (§55)
except Exception:                         # pragma: no cover
    phrases = None

_log = logging.getLogger(__name__)

# ---------- типы уроков ----------
SPEAKING = "speaking"
CHAT = "chat"
LISTENING = "listening"
# ПРОВЕРОЧНОЕ занятие в конце каждого блока: Джейн НЕ учит новому,
# а проверяет, закрепился ли материал блока (см. §8 снимка проекта).
CHECK = "check"
MIXED = "mixed"                 # не используем в UI (совместимость данных)
# Шаг 3 (02.11.2026): СЦЕНА — урок-диалог по жизненной ситуации (ресторан).
# Реплики участника (официанта) ведёт ПРИЛОЖЕНИЕ: готовые вопросы берутся из
# scenes.py по номеру шага, модель в сцене не зовётся совсем (вариант А).
SCENE = "scene"

KNOWN_TYPES = (SPEAKING, CHAT, LISTENING, CHECK, MIXED, SCENE)
DEFAULT_TYPE = SPEAKING

TYPE_LABELS = {
    SPEAKING: "говорение",
    CHAT: "текст",
    LISTENING: "аудирование",
    CHECK: "проверка",
    MIXED: "смешанный",
    SCENE: "сцена",
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
# Шаг 3 (02.11.2026): фаза СЦЕНЫ. Вопросы задаёт приложение (scenes.py),
# ученик отвечает; шаг считается пройденным, когда отвечен его последний
# вопрос. Задание урока = ШАГ сцены (6 шагов = 6 заданий).
TASK_SCENE = "scene"
# Сколько раз повторяем ОДИН вопрос сцены, если ответа на английском нет
# (молчание или русский текст), прежде чем идти дальше с пометкой.
SCENE_TRIES = 1

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
# §55 шаг 2: сколько раз даём попробовать ОДНУ фразу дрилла, прежде чем
# показать эталон и пойти дальше (иначе ученик застревает на фразе).
DRILL_TRIES = 2


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
    if name in (MIXED, SCENE):
        # сцена-пилот: на время проверки отвечаем и голосом, и текстом
        # (решение ученика 02.11.2026), чтобы быстрее поймать баги
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

# Слова, которые не делают задание «тем же самым» (11.11.2026).
# Нужно для правила «не спрашивай то, что ученик уже сделал».
_TASK_STOP_WORDS = frozenset(
    """the a an and or but to of in on at for with from by is are am was were
    be been you your yours i me my we our us he she it they them his her its this
    that these those do does did have has had can could would should will shall
    may might must please now then again say told tell repeat think want like
    about what who where when why how one two three four five six seven eight
    nine ten very really just also more most some any all not no yes ok okay
    good great nice well done right correct wrong another else thing things
    """.split())


def task_words(text: Any) -> set:
    """Смысловые слова задания: по ним видно, что задание ПОВТОРЯЕТСЯ."""
    return {w for w in _flat(text).split()
            if len(w) > 2 and w not in _TASK_STOP_WORDS}


def same_task(first: Any, second: Any) -> bool:
    """Одно и то же задание? (§70, 11.11.2026: «это что, молитва?»)

    Сравнение по СМЫСЛОВЫМ словам, а не по тексту: живой урок city/3.3 —
    модель дала `i bought a hat at the store`, засчитала, а потом попросила
    `i bought a hat` ещё раз (и это уже третье задание урока).
    Порог 0,5 подобран на этом же уроке: пересечение {bought, hat} = 1,0,
    а «What did you buy yesterday?» с ним не пересекается вовсе.
    """
    one = task_words(first)
    two = task_words(second)
    if not one or not two:
        return False
    common = len(one & two)
    return common >= 2 and common / float(min(len(one), len(two))) >= 0.5


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


def _latin_words(text: Any) -> List[str]:
    """Английские слова в ответе (латиница). Пусто — английского нет.

    Нужно сцене: на вопрос официанта ученик может ответить по-русски или
    молчанием — такой ответ не принимаем, вопрос повторяем (решение ученика:
    сцена — это практика говорения, а не перевод).
    """
    words = []
    for chunk in str(text or "").split():
        word = "".join(ch for ch in chunk if ch.isalpha())
        if word and all("a" <= ch.lower() <= "z" for ch in word):
            words.append(word.lower())
    return words


# ---------------------------------------------------------------------------
# §65 (10.11.2026): «НЕ ПРИДИРАТЬСЯ» — сравнение по СМЫСЛУ, а не по буквам
# ---------------------------------------------------------------------------
# Решение ученика 109: одну мысль можно сказать по-разному, и зачёт должен
# быть, если сказано ТО ЖЕ САМОЕ. Живой случай 10.11.2026: задание просило
# «would like to see», ученик сказал «I want to see» — и слышал «Not quite».
# Без модели приводим «чуть другое» к одной форме: сокращения, разговорные
# стяжки, вежливые вставки, порядок слов.
_CONTRACTIONS = (
    ("won't", "will not"), ("can't", "cannot"),
    ("i'm", "i am"), ("i've", "i have"), ("i'll", "i will"),
    ("i'd", "i would"), ("you're", "you are"), ("you've", "you have"),
    ("you'll", "you will"), ("you'd", "you would"),
    ("we're", "we are"), ("we've", "we have"), ("we'll", "we will"),
    ("they're", "they are"), ("they've", "they have"),
    ("they'll", "they will"), ("he's", "he is"), ("she's", "she is"),
    ("it's", "it is"), ("that's", "that is"), ("what's", "what is"),
    ("there's", "there is"), ("let's", "let us"),
    ("isn't", "is not"), ("aren't", "are not"), ("wasn't", "was not"),
    ("weren't", "were not"), ("don't", "do not"), ("doesn't", "does not"),
    ("didn't", "did not"), ("haven't", "have not"), ("hasn't", "has not"),
    ("hadn't", "had not"), ("wouldn't", "would not"),
    ("couldn't", "could not"), ("shouldn't", "should not"),
)
# Разговорные стяжки: в речи звучат так же, как полная форма.
_SPOKEN = (("wanna", "want to"), ("gonna", "going to"),
           ("gotta", "got to"), ("kinda", "kind of"),
           ("lemme", "let me"), ("gimme", "give me"))
# Вежливые вставки, которые смысла не меняют. «just»/«like»/«so» сюда НЕ
# входят: они бывают частью фразы («just looking», «I'd like»).
_FILLERS = frozenset(("please", "well", "um", "uh", "erm", "hmm",
                      "oh", "ah", "eh", "yeah", "ok", "okay"))
# Служебные слова: артикли, местоимения-подлежащие, формы be. Их пропуск
# смысла не меняет: «Looking for a jacket» и «I'm looking for a jacket» —
# одна мысль (решение 109: придираться к мелочам не надо). Отрицание
# («not») из списка СНАРУЖИ — его отдельно сверяет same_meaning.
_NEGATIONS = frozenset(("not", "no", "never", "nothing", "nobody"))
_SKIP = frozenset(("a", "an", "the", "i", "you", "we", "they", "he", "she",
                   "it", "am", "is", "are", "was", "were", "be"))


def _meaning_words(text: Any) -> List[str]:
    """Слова фразы в ОДНОЙ форме: сокращения раскрыты, вставки убраны."""
    value = " " + _flat(text) + " "
    for short, full in _CONTRACTIONS:
        value = value.replace(" " + short + " ", " " + full + " ")
    for short, full in _SPOKEN:
        value = value.replace(" " + short + " ", " " + full + " ")
    return [w for w in value.split()
            if w and w not in _FILLERS and w not in _SKIP]


def same_meaning(said: Any, want: Any) -> bool:
    """Сказано ТО ЖЕ САМОЕ, пусть и другими словами? (решение 109)

    Правило простое: все значимые слова эталона есть в ответе, порядок не
    важен, сокращения и вежливые вставки не считаются. Чего этот путь НЕ
    умеет — настоящие синонимы («see» / «watch»): их решает модель, но только
    в момент промаха (ui/app.py::_meaning_second_look), а не на каждом ответе.

    Отрицание сверяется ОТДЕЛЬНО: «I do» и «I don't» дают одинаковый набор
    значимых слов, и без этой проверки промах засчитывался бы как верный.
    """
    want_words = _meaning_words(want)
    if not want_words:
        return False
    said_words = _meaning_words(said)
    if not said_words:
        return False
    bad = sum(1 for w in said_words if w in _NEGATIONS)
    if bad != sum(1 for w in want_words if w in _NEGATIONS):
        return False
    have = set(said_words)
    return all(w in have for w in want_words)


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
        # §65 (решение 109): та же мысль другими словами — тоже зачёт
        if same_meaning(student_text, want):
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
        # §62: что было НЕПРАВИЛЬНО в исходной ошибке. Нужно, чтобы в фазе
        # «ждём повтор» засчитывать ТОЛЬКО целевую правку: посторонняя
        # мелочь (артикль, заглавная) больше не валит верный повтор.
        self.repeat_wrong = []       # type: List[str]
        self.last_credited = ""      # текст, за который задание уже засчитано
        # §70: ЧТО уже сделано в уроке (эталон, а не текст ученика).
        # По этому списку промпт и контроллер не дают попросить то же самое
        # второй раз: «одна фраза три раза — это что, молитва?».'«
        self.asked_tasks = []        # type: List[str]
        # §55: материал дрилла (что ученик сказал раньше и как надо)
        self.drill_wrong = ""
        self.drill_correct = ""
        # §55 шаг 2: дрилл на 3 фразы из библиотеки (phrases.py).
        # Пустая очередь = старый режим «одна фраза» (совместимость).
        self.drill_rule = ""         # id правила библиотеки (a2.lay_lie)
        self.drill_phrases = []      # type: List[Dict[str, Any]]
        self.drill_words = []        # type: List[str]
        self.drill_pos = 0           # сколько фраз уже сделано
        self.drill_errors = 0        # промахов за весь дрилл
        self.drill_tries = 0         # промахов в ТЕКУЩЕЙ фразе
        self.drill_why = ""          # объяснение последней фразы
        # Шаг 3: позиция в СЦЕНЕ (ресторан). Тексты вопросов — в scenes.py,
        # здесь только «где мы стоим» и счётчики для итога.
        self.scene_id = ""           # a2.restaurant ("" — это не сцена)
        self.scene_step = 1          # номер шага, 1..N
        self.scene_q = 0             # индекс вопроса ВНУТРИ шага (0..)
        self.scene_counts = []       # type: List[int] вопросов в каждом шаге
        self.scene_tries = 0         # осечек на ТЕКУЩЕМ вопросе
        self.scene_answers = 0       # принятых ответов за сцену
        self.scene_skipped = 0       # вопросов, брошенных после двух осечек
        self.scene_step_skipped = 0  # брошенных вопросов В ТЕКУЩЕМ шаге
        self.scene_said = []         # ответы ученика: [{q, a, step}] для разбора

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
    def start_drill(self, wrong, correct, phrases=None, rule_id="",
                    words=None) -> bool:
        """Первое задание урока = ДРИЛЛ по ПРОШЛОЙ ошибке ученика (§55).

        Два режима:
          * одна фраза (phrases пусто) — старый: материал «было -> стало»,
            зачёт по тексту через says_fix;
          * очередь фраз (1..3) — шаг 2: фразы берутся из библиотеки
            phrases.py, модель их НЕ сочиняет, ответ проверяет drill_check().
        Дрилл занимает ТОЛЬКО первое из трёх заданий урока.
        """
        want = str(correct or "").strip()
        if not want or not self.is_active or not self.has_tasks:
            return False
        self.drill_wrong = str(wrong or "").strip()
        self.drill_correct = want
        self.repeat_expected = [want]
        self.task_phase = TASK_DRILL
        self.task_attempts = 0
        self.drill_rule = str(rule_id or "").strip()
        self.drill_words = [str(w).strip() for w in (words or []) if str(w).strip()]
        queue = []                                   # type: List[Dict[str, str]]
        for item in (phrases or []):
            if isinstance(item, dict) and item.get("en"):
                queue.append({"ru": str(item.get("ru") or "").strip(),
                              "en": str(item.get("en") or "").strip(),
                              "why": str(item.get("why") or "").strip(),
                              "hint2": str(item.get("hint2") or "").strip()})
        self.drill_phrases = queue
        self.drill_pos = 0
        self.drill_errors = 0
        self.drill_tries = 0
        self.drill_why = ""
        if queue:
            self.repeat_expected = [queue[0]["en"]]
        return True

    # ---------- дрилл на 3 фразы (§55, шаг 2) ----------
    @property
    def drill_total(self) -> int:
        """Сколько фраз в дрилле (0 — режим одной фразы)."""
        return len(self.drill_phrases)

    @property
    def drill_clean(self) -> bool:
        """Все фразы сделаны и промахов не было ни одного."""
        return (self.drill_total > 0 and self.drill_errors == 0
                and self.drill_pos >= self.drill_total)

    def drill_current(self) -> Optional[Dict[str, Any]]:
        """Фраза, которую спрашиваем СЕЙЧАС (None — дрилл кончился)."""
        if not self.drill_phrases or self.drill_pos >= len(self.drill_phrases):
            return None
        item = self.drill_phrases[self.drill_pos]
        return {"ru": item["ru"], "en": item["en"], "why": item["why"],
                "hint2": item["hint2"], "index": self.drill_pos + 1,
                "total": len(self.drill_phrases)}

    def _drill_other_side(self, said: str, want: str) -> bool:
        """Сказал ДРУГУЮ сторону пары? (Lay вместо lie — ошибка, решение 79.)

        Смотрим только ключевые слова правила: одно есть в эталоне, другое —
        в сказанном. Без похожести на эталон это просто промах, а не подмена.
        """
        if phrases is None:
            return False
        words = [w for w in (self.drill_words or []) if w]
        if len(words) < 2:
            return False
        for mine in words:
            if not phrases.has_word(want, mine):
                continue
            for other in words:
                if other == mine:
                    continue
                if (phrases.has_word(said, other)
                        and not phrases.has_word(said, mine)):
                    return True
        return False

    def _drill_report(self, result: str, phrase: Dict[str, Any],
                      why: str = "") -> Dict[str, Any]:
        """Что окну делать дальше: result, текущая фраза, следующая, why."""
        total = self.drill_total
        finished = self.drill_pos >= total
        nxt = self.drill_current()
        self.repeat_expected = [nxt["en"]] if nxt else []
        self.drill_why = why
        return {"result": result, "phrase": phrase, "next": nxt, "why": why,
                "done": min(self.drill_pos, total), "total": total,
                "next_index": (nxt["index"] if nxt else total),
                "errors": self.drill_errors, "finished": finished}

    def drill_check(self, student_text: Any) -> Dict[str, Any]:
        """Ответ на текущую фразу дрилла, без модели.

        Результаты:
          ok          — сказал эталон, перешли к следующей фразе;
          wrong_side  — сказал ДРУГУЮ сторону пары: объяснение сразу (79);
          miss        — не то; после DRILL_TRIES промахов — reveal;
          reveal      — попытки кончились, эталон показан, идём дальше;
          done        — все фразы сделаны.
        """
        phrase = self.drill_current()
        if phrase is None:
            return {"result": "none", "finished": self.drill_total > 0}
        said = _flat(student_text)
        want = _flat(phrase.get("en"))
        old = _flat(self.drill_wrong)

        def fail(kind: str, why: str = "") -> Dict[str, Any]:
            self.drill_errors += 1
            self.drill_tries += 1
            if self.drill_tries >= DRILL_TRIES:
                # попытки кончились: эталон показываем и идём дальше,
                # иначе ученик застревает на одной фразе
                self.drill_pos += 1
                self.drill_tries = 0
                return self._drill_report("reveal", phrase, why or phrase["why"])
            return self._drill_report(kind, phrase, why)

        if not said:
            return fail("miss")
        # 1) эталон целиком прозвучал — зачёт
        if want and want in said:
            self.drill_pos += 1
            self.drill_tries = 0
            done = self.drill_pos >= self.drill_total
            return self._drill_report("done" if done else "ok", phrase,
                                      phrase["why"])
        # 2) старая ошибка внутри фразы — зачёта нет (§55, DRILL_RATIO)
        if old and old in said:
            return fail("miss")
        # 3) ДРУГАЯ сторона пары — ошибка и объяснение сразу (решение 79).
        #    Проверяем ДО порога похожести: «Lay down…» и «Lie down…»
        #    отличаются одним словом и иначе прошли бы как верный ответ.
        ratio = difflib.SequenceMatcher(None, said, want).ratio()
        if ratio >= 0.60 and self._drill_other_side(said, want):
            return fail("wrong_side", phrase["why"])
        # 4) §65: та же мысль другими словами — зачёт (решение ученика 109).
        #    Стоит ПОСЛЕ проверок старой ошибки и другой стороны пары: иначе
        #    «advise to me» прошло бы как верное к «advise me».
        if same_meaning(student_text, phrase.get("en")):
            self.drill_pos += 1
            self.drill_tries = 0
            done = self.drill_pos >= self.drill_total
            return self._drill_report("done" if done else "ok", phrase,
                                      phrase["why"])
        if ratio >= DRILL_RATIO:
            self.drill_pos += 1
            self.drill_tries = 0
            done = self.drill_pos >= self.drill_total
            return self._drill_report("done" if done else "ok", phrase,
                                      phrase["why"])
        return fail("miss")

    def expect_repeat(self, corrections, wrongs=None) -> List[str]:
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
        bad = []                                      # type: List[str]
        for raw in (wrongs or []):
            text = str(raw or "").strip()
            if text and text not in bad:
                bad.append(text)
        self.repeat_expected = items
        self.repeat_wrong = bad
        self.task_phase = TASK_FIX
        self.task_attempts = 0
        return items

    def says_fix(self, student_text: Any) -> bool:
        """Ученик повторил исправление? Мгновенно, без модели (вариант В)."""
        if self.task_phase not in (TASK_FIX, TASK_DRILL):
            return False
        if self.task_phase == TASK_DRILL and self.drill_phrases:
            # дрилл на 3 фразы: ответ принимает окно (drill_check),
            # случайная реплика в чате задание НЕ засчитывает
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
            if same_meaning(student_text, self.drill_correct):
                return True            # §65: та же мысль другими словами
            return difflib.SequenceMatcher(None, said, want).ratio() >= DRILL_RATIO
        return says_fix(student_text, self.repeat_expected)

    def target_repeated(self, student_text: Any) -> bool:
        """Повторил ли ученик ИМЕННО ту правку, которую просили (§62).

        Живой урок 2.3 (07.11.2026): дрилл был на «advise me», ученик сказал
        «i advise people to eat for dinner hamburger.» — целевая правка на месте,
        но Аналитик нашёл ДРУГУЮ ошибку (артикль), и задание снова ушло в
        «ждём повтор». Так ученик три раза повторял одно и то же.

        Правило: в фазе «ждём повтор» зачёт даёт ЦЕЛЕВАЯ правка. Посторонние
        ошибки в той же реплике — отдельная тема (их разберёт обычный урок),
        но верный повтор они не отменяют.

        Старая ошибка в реплике всё равно блокирует зачёт («advise to me»
        рядом с «advise me» — значит не исправил).
        """
        if not self.is_active or not self.has_tasks:
            return False
        if self.task_phase not in (TASK_FIX, TASK_DRILL):
            return False
        said = _flat(student_text)
        if not said:
            return False
        for bad in (self.repeat_wrong or []):
            mark = _flat(bad)
            if mark and mark in said:
                return False        # старая ошибка звучит снова
        if self.task_phase == TASK_DRILL:
            return self.says_fix(student_text)
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
        self._remember_asked(self.drill_correct or student_text)
        self.repeat_expected = []
        self.repeat_wrong = []
        self.task_attempts = 0
        self.drill_wrong = ""
        self.drill_correct = ""
        self.drill_phrases = []
        self.drill_pos = 0
        self.drill_tries = 0
        self.drill_why = ""
        if self.all_tasks_done:
            self.task_phase = TASK_DONE
            self.finished = True
        else:
            self.task_phase = TASK_ASK
        return self.state()

    def _remember_asked(self, text: Any) -> None:
        """Запомнить ЭТАЛОН того, что в уроке уже отработано (§70).

        Живой урок city/3.3 (10.11.2026): три задания подряд об одном и том же
        («i bought a hat»), потому что модель не знала, ЧТО она уже дала.
        Держим последние шесть: промпт не должен пухнуть.
        """
        value = str(text or "").strip()
        if not value:
            return
        if value not in self.asked_tasks:
            self.asked_tasks.append(value)
        del self.asked_tasks[:-6]

    def finish_drill(self, clean: bool = True) -> bool:
        """Дрилл пройден — задание НЕ засчитывается: это разминка (§70).

        Ученик 10.11.2026: «за этот урок мы отработали всего лишь одну фразу
        "I bought a hat", одна фраза это не серьёзно». Дрилл занимал первое
        из трёх заданий, и на тему урока оставалось два. Теперь дрилл идёт
        ПЕРЕД заданиями: счёт заданий не сдвигается.
        """
        if not self.is_active or not self.has_tasks:
            return False
        if self.task_phase != TASK_DRILL:
            return False
        self._remember_asked(self.drill_correct)
        self.repeat_expected = []
        self.repeat_wrong = []
        self.task_attempts = 0
        self.drill_wrong = ""
        self.drill_correct = ""
        self.drill_phrases = []
        self.drill_pos = 0
        self.drill_tries = 0
        self.drill_why = ""
        self.task_phase = TASK_ASK       # задание 1 из N ещё НЕ сдано
        return True


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
        # §70: «не проси то же самое второй раз». Эталоны уже
        # отработанного — по ним модель выбирает НОВОЕ задание.
        if self.asked_tasks:
            payload["asked_tasks"] = " · ".join(self.asked_tasks)
            payload["last_task_done"] = self.asked_tasks[-1]
        # §55: в фазе дрилла промпту нужно, ЧТО ученик сказал неправильно
        if self.task_phase == TASK_DRILL and self.drill_wrong:
            payload["drill_wrong"] = self.drill_wrong
        return payload

    # ---------- сцена-диалог (шаг 3, 02.11.2026) ----------
    def start_scene(self, scene_id: Any, counts=None) -> bool:
        """Начать сцену: ШАГИ становятся заданиями урока (6 шагов = 6 заданий).

        Вопросы и карточку роли даёт scenes.py — модель сюда не допускается
        (вариант А: выдумкам неоткуда взяться).
        """
        if not self.is_active:
            return False
        rows = []
        for value in (counts or []):
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                rows.append(number)
        if not str(scene_id or "").strip() or not rows:
            return False
        self.scene_id = str(scene_id).strip()
        self.scene_counts = rows
        self.scene_step = 1
        self.scene_q = 0
        self.scene_tries = 0
        self.scene_answers = 0
        self.scene_skipped = 0
        self.scene_step_skipped = 0
        self.scene_said = []
        self.tasks_total = len(rows)
        self.tasks_done = 0
        self.tasks_marked = 0
        self.task_attempts = 0
        self.task_phase = TASK_SCENE
        return True

    @property
    def is_scene(self) -> bool:
        """Урок идёт как СЦЕНА (диалог по жизненной ситуации)."""
        return bool(self.scene_id)

    @property
    def scene_total_steps(self) -> int:
        """Сколько шагов в сцене."""
        return len(self.scene_counts)

    def scene_check(self, text: Any) -> Dict[str, Any]:
        """Разобрать ответ ученика в сцене (без модели).

        Результаты:
          ok        — ответ на английском принят, идём дальше;
          retry     — пусто/по-русски: вопрос повторяем (SCENE_TRIES раз);
          skip      — осечек больше, чем SCENE_TRIES: вопрос пропускаем.

        Вопрос в ответе — ОБЫЧНЫЙ ответ: ученик мог пытаться сказать фразу и
        ошибиться («are we two persons?»). Знак «?» больше ничего не решает:
        ошибки ищет разбор в конце сцены, а не проверка знака.
        """
        said = _flat(text)
        result = "ok"
        if not said or not _latin_words(text):
            self.scene_tries += 1
            result = "retry" if self.scene_tries <= SCENE_TRIES else "skip"
            if result == "skip":
                # вопрос бросили: шаг засчитаем, но С ОГОВОРКОЙ
                self.scene_skipped += 1
                self.scene_step_skipped += 1
        else:
            self.scene_answers += 1
            self.scene_tries = 0
        return {"result": result, "step": self.scene_step,
                "tries": self.scene_tries}

    def scene_advance(self) -> Dict[str, Any]:
        """Ответ принят: следующий вопрос шага или конец шага.

        Шаг засчитывает ОКНО (_scene_credit), поэтому здесь только позиция.
        """
        rows = self.scene_counts or []
        limit = rows[self.scene_step - 1] if 0 <= self.scene_step - 1 < len(rows) else 0
        if self.scene_q + 1 < limit:
            self.scene_q += 1
            self.scene_tries = 0
            return {"step_done": False, "step": self.scene_step}
        return {"step_done": True, "step": self.scene_step}

    def scene_note(self, question: Any, said: Any) -> bool:
        """Запомнить ответ ученика для разбора В КОНЦЕ сцены (шаг 4).

        Вызывается ДО scene_advance: вопрос ещё текущий. Пустые ответы и
        русские реплики не храним — разбирать там нечего.
        """
        text = str(said or "").strip()
        if not text or not _latin_words(text):
            return False
        self.scene_said.append({"q": str(question or "").strip()[:200],
                                "a": text[:200], "step": self.scene_step})
        return True

    def scene_credit(self, marked: Optional[bool] = None) -> bool:
        """Засчитать ШАГ сцены и встать на первый вопрос следующего.

        marked=None — решает САМ шаг: если в нём был брошенный вопрос, шаг
        идёт с оговоркой (иначе ученик получал бы «чисто» за пропуск).
        """
        if not self.is_active or not self.has_tasks:
            return False
        if marked is None:
            marked = self.scene_step_skipped > 0
        self.tasks_done += 1
        if marked:
            self.tasks_marked += 1
        self.scene_step_skipped = 0
        self.scene_step += 1
        self.scene_q = 0
        self.scene_tries = 0
        if self.all_tasks_done:
            self.task_phase = TASK_DONE
            self.finished = True
        return True

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
            if self.is_scene:
                return "Шаг %d/%d" % (self.task_index, self.tasks_total)
            if self.task_phase == TASK_DRILL:
                return "Разминка"

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
