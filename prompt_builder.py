# -*- coding: utf-8 -*-
# =========================================================
# PROMPT_BUILDER.PY — сборка промптов для Gemma
# =========================================================
# Вынесено из gui.py (метод get_dynamic_prompt ~60 строк текста и сборка
# промпта из ask_jane). Теперь это чистые функции: их можно проверить
# без customtkinter и вообще без запуска окна.
#
# ВАЖНО: текст промпта сохранён посимвольно как был — рефакторинг не
# должен менять то, что видит модель.
# =========================================================

import re

import config

# Отступ 4 пробела у продолжений строк — это ЧАСТЬ текста промпта
# (так было в gui.py). Не «выравнивать» автоформаттером.
# Имя преподавателя подставляется в промпт: в профиле ученика может быть своё
# (поле teacher_name), иначе берётся config.TEACHER_NAME («Verbot»).
# Пол при этом НЕ зависит от имени: робот остаётся женщиной, поэтому женские
# формы в русском требуются при любом имени (решение ученика 23.10.2026).
FEMALE_IDENTITY_TEMPLATE = """IMPORTANT: You are {teacher_name}, a female AI assistant. When speaking in Russian, ALWAYS refer to yourself in the FEMININE GENDER:
    - Use "я сказала", "я сделала", "я была", "я преподавательница", "я ответила" instead of masculine forms.
    - Use feminine forms of verbs and adjectives (e.g., "я готова", "я уверена", "я думала", "я хотела").
    - This applies to ALL your responses in Russian, regardless of the mode (lesson or free)."""


def teacher_name(name=None):
    """Имя преподавателя для промпта: своё из профиля или общее из config.

    Пустое/мусорное значение → config.TEACHER_NAME. Одна функция на весь
    проект: имя попадает и в промпт, и в чат, и в заголовок окна.
    """
    name = str(name or "").strip()
    if name:
        return name
    return str(getattr(config, "TEACHER_NAME", "") or "Verbot").strip() or "Verbot"


def female_identity(teacher=None):
    """Блок «ты женщина» с подставленным именем преподавателя."""
    return FEMALE_IDENTITY_TEMPLATE.format(teacher_name=teacher_name(teacher))

EMOJIS = "😊👍❤️🎉🔥💪🤗✨🌟🎯📚💡💬👏🙌💖"

_RUSSIAN_CHARS = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")

FALLBACK_RU = "Извините, я не могу ответить на это."
FALLBACK_EN = "Sorry, I can't respond."


# ---------- учёт уровня ученика (CEFR) ----------
# Добавлено для адаптивного теста уровня (level_test.py).
# ВАЖНО: при level=None ничего не добавляется, поэтому старый вывод
# build_system_prompt не меняется (см. tests/smoke_test.test_prompt_unchanged).
CEFR_GUIDANCE = {
    "A1": "use only the most basic words and Present Simple; very short sentences (3-6 words).",
    "A2": "use everyday vocabulary and basic past/future; short, simple sentences.",
    "B1": "use intermediate vocabulary, common phrasal verbs and mixed tenses.",
    "B2": "use upper-intermediate vocabulary, complex sentences and nuanced grammar.",
    "C1": "use advanced vocabulary, idioms and sophisticated structures.",
}

LEVEL_BLOCK_TEMPLATE = """
\n\U0001F4C8 STUDENT ENGLISH LEVEL: {level}
Match your English to this CEFR level: {guidance}
Keep your Russian (if you use it) simple and clear too.
"""


def _level_block(profile, level):
    """Блок про уровень. Пусто, если уровень не задан (обратная совместимость)."""
    level = str(level or (profile or {}).get("level") or "").strip().upper()
    if level not in CEFR_GUIDANCE:
        return ""
    return LEVEL_BLOCK_TEMPLATE.format(level=level, guidance=CEFR_GUIDANCE[level])


# ---------- «слабые темы» из теста уровня ----------
# Пишет их profile_store.record_level_test (profiles/user_N_progress.json).
# ВАЖНО: пусто, если данных нет — тогда вывод build_system_prompt не меняется
# (см. tests/smoke_test.test_prompt_unchanged).
WEAK_TOPICS_TEMPLATE = """
\U0001F3AF WEAK TOPICS (from the placement test): {topics}
Weave these weak topics into the lesson when it feels natural.
"""


def _weak_topics_block(profile):
    """Блок про слабые темы. Пусто, если их нет (обратная совместимость)."""
    topics = (profile or {}).get("weak_topics") or []
    names = []
    for item in topics[:3]:
        name = item.get("topic") if isinstance(item, dict) else item
        name = str(name or "").strip()
        if name:
            names.append(name)
    if not names:
        return ""
    return WEAK_TOPICS_TEMPLATE.format(topics=", ".join(names))

# ---------- личность ученика (имя и род) ----------
# Раньше в промпт попадал только ПРОГРЕСС, а имя/пол — нет, и модель
# угадывала грамматический род ученика (обычно ЖЕНСКИЙ, т.к. сама Джейн —
# женщина): «Чем бы ТЫ хотела заняться?». Теперь, когда личность известна,
# добавляем отдельный блок с именем и родом И ОГРАНИЧИВАЕМ женские формы
# самой Джейн.
# ВАЖНО: при student=None ничего не добавляется — вывод build_system_prompt
# не меняется (см. tests/smoke_test.test_prompt_unchanged).
STUDENT_GENDER_FORMS = {
    "male": "MASCULINE forms about the student in Russian (e.g. «ты хотел», «ты готов», «молодец», «ты справился»)",
    "female": "FEMININE forms about the student in Russian (e.g. «ты хотела», «ты готова», «умница», «ты справилась»)",
    "other": "gender-neutral phrasing — avoid gendered verb/adjective endings for the student, or ask which forms to use",
}

STUDENT_BLOCK_TEMPLATE = """
\U0001F464 STUDENT: {name}
The student's gender is: {gender}. When you address the student or talk about them in Russian, use {forms}.
Address the student by their name when it feels natural.
The student's name has two spellings: «{name}» (Russian) and «{name_latin}» (Latin). Write the Russian form in Russian text and the Latin form in English text. Copy them EXACTLY — a misspelling will be read aloud incorrectly.
Write Russian correctly: proper cases (падежи), gender, number and word agreement.
IMPORTANT: in Russian, NEVER use feminine forms about the student — the feminine forms above describe YOU, {teacher_name}, not the student.
Answer the student's question directly. Do not show your reasoning, plans or inner thoughts — reply with the final answer only.
"""


def _student_block(student, teacher=None):
    """Блок про личность ученика (имя и род). Пусто, если данных нет.

    Без этого модель не знает имени ученика и угадывает грамматический род
    (в русском — обычно женский, потому что преподаватель — женщина).
    teacher — имя преподавателя для строки «эти формы про ТЕБЯ, а не про ученика».
    """
    student = student or {}
    name = str(student.get("name") or "").strip()
    name_latin = str(student.get("name_latin") or "").strip() or name
    gender = str(student.get("gender") or "").strip().lower()
    forms = STUDENT_GENDER_FORMS.get(gender)
    if not name and not forms:
        return ""
    return STUDENT_BLOCK_TEMPLATE.format(
        name=name or "the student",
        name_latin=name_latin or "the student",
        gender=gender or "unknown",
        forms=forms or STUDENT_GENDER_FORMS["other"],
        teacher_name=teacher_name(teacher),
    )


# ---------- план урока (роль-Планировщик) ----------
# Готовый текст плана приходит из ChatController (planner.format_plan).
# ВАЖНО: при plan=None/пусто блок не добавляется — вывод
# build_system_prompt не меняется (обратная совместимость).
LESSON_PLAN_BLOCK_TEMPLATE = """
\n\U0001F4CB TODAY'S LESSON PLAN (follow it, stay flexible):
{plan}
"""


def _plan_block(plan):
    """Блок плана урока. Пусто, если плана нет (обратная совместимость)."""
    plan = str(plan or "").strip()
    if not plan:
        return ""
    return LESSON_PLAN_BLOCK_TEMPLATE.format(plan=plan)


# ---------- база знаний (RAG) ----------
# Готовые методические заметки приходят сюда ТЕКСТОМ из ChatController
# (rag.build_context). prompt_builder НЕ знает про rag — так модуль
# остаётся чистым и тестируемым без базы знаний.
# ВАЖНО: при context=None/пусто блок не добавляется — вывод
# build_system_prompt не меняется (см. tests/smoke_test.test_prompt_unchanged).
KNOWLEDGE_BLOCK_TEMPLATE = """
\n\U0001F4DA TEACHING NOTES (methodology — guide HOW you teach, do not quote):
{context}
"""


def _knowledge_block(context):
    """Блок методических заметок. Пусто, если контекста нет (обратная совместимость)."""
    context = str(context or "").strip()
    if not context:
        return ""
    return KNOWLEDGE_BLOCK_TEMPLATE.format(context=context)


# ---------- слова ученика в разговоре (этап C) ----------
# Готовые строки вида «ключ — key» собирает vocabulary.prompt_words (по
# профилю ученика). Здесь только текст блока: вплести слово ПО ТЕМЕ, не
# устраивать опрос и не вываливать весь список. ВАЖНО: при words=None/пусто
# блок не добавляется, и промпт остаётся прежним байт-в-байт
# (см. tests/smoke_test.test_prompt_unchanged).
WORDS_BLOCK_TEMPLATE = """
\n\U0001F9E0 WORDS FROM THE STUDENT'S OWN VOCABULARY (use if it fits):
{words}
Pick at most ONE or TWO of these words and use them naturally in your reply,
or ask a short question that invites one of them. Do not dump the whole list
into one answer, do not turn it into a test, and never force all of them in.
Naming one or two words while giving a small task is fine.
If the student asks to practise or remember words, give a tiny task with one or
two of them right away — do not answer with a question about what to practise.
"""


def _words_block(words):
    """Блок «слова ученика». Пусто, если слов нет (обратная совместимость)."""
    items = []
    for item in (words or []):
        text = str(item or "").strip()
        if text:
            items.append("- %s" % text)
    if not items:
        return ""
    return WORDS_BLOCK_TEMPLATE.format(words="\n".join(items))


# ---------- идущее занятие (карта прогресса, lesson.py) ----------
# Готовую подпись урока собирает приложение (ui/app.py) и передаёт словарём
# {"title", "type", "topic"}. ВАЖНО: при lesson=None блок НЕ добавляется —
# вывод build_system_prompt не меняется (обратная совместимость,
# см. tests/smoke_test.test_prompt_unchanged).
LESSON_BLOCK_TEMPLATE = """
\n\U0001F3EB CURRENT LESSON: {title}
The student just started this lesson. Topic: {topic}.
{task_line}Run THIS lesson now: keep the student talking, ask one short question at a time,
let the student answer, and gently correct mistakes. Adapt if the student
struggles, and do not switch to another topic on your own.
"""


def _lesson_block(lesson):
    """Блок «идёт занятие». Пусто, если занятия нет (обратная совместимость)."""
    if not lesson:
        return ""
    task = ""
    if isinstance(lesson, dict):
        title = str(lesson.get("title") or lesson.get("topic") or "").strip()
        topic = str(lesson.get("topic") or lesson.get("title") or "").strip()
        task = str(lesson.get("task") or "").strip()
    else:
        title = topic = str(lesson).strip()
    if not title:
        return ""
    # пустая задача не добавляет ничего — вывод блока не меняется
    task_line = ("Do this first: %s\n" % task) if task else ""
    return LESSON_BLOCK_TEMPLATE.format(title=title, topic=topic or title,
                                        task_line=task_line)


# ---------- дата и время (необязательно) ----------
# Джейн должна знать, какой сегодня день, — иначе она путается в «доброе
# утро / добрый вечер» и не может поговорить о планах. ВАЖНО: при now=None
# блок НЕ добавляется — вывод build_system_prompt не меняется
# (см. tests/smoke_test.test_prompt_unchanged).
NOW_BLOCK_TEMPLATE = """
\n\U0001F552 RIGHT NOW: {text}
Use this only when it matters (greetings, small talk about the day, plans).
Never invent another date or time. Do not state exact minutes unless the
student asks; «today», «this evening» is usually enough.
"""


def _now_block(now=None):
    """Блок «сейчас такое-то время». Пусто, если время не передано."""
    if now is None:
        return ""
    try:
        text = now.strftime("%A, %d %B %Y, %H:%M")
    except Exception:
        return ""
    return NOW_BLOCK_TEMPLATE.format(text=text)


# ---------- разнообразие беседы (необязательно) ----------
# Жалоба ученика: Джейн при каждом знакомстве спрашивает одно и то же
# («что ты ел на завтрак»). Блок прямо запрещает заезженный small talk и
# подсказывает темы. При variety=False блок не добавляется — база промпта
# остаётся прежней (см. tests/smoke_test).
VARIETY_BLOCK_TEMPLATE = """
\n\U0001F501 MAKE THE CONVERSATION FRESH:
- Never ask a question you have already asked in this dialogue.
- Do NOT use the default textbook small talk: breakfast, food you ate,
  "how are you", "what is the weather". Only talk about them if the STUDENT
  starts it.
- Pick a different topic each time and build on what the student just said.
- Use the student's name sometimes, not in every sentence.
Topic ideas: family, friends, school, hobbies, music, films, games, books,
sport, pets, travel, dreams, favourite places, funny stories.
"""


def _variety_block(variety=False):
    """Блок против повторов. Пусто, если не запрошен."""
    return VARIETY_BLOCK_TEMPLATE if variety else ""


# ---------- ответ ТОЛЬКО по-английски (необязательно) ----------
# Голос Джейн на английском звучит заметно лучше русского, поэтому в
# обучении полезно полное погружение. ВАЖНО: блок добавляется только при
# english_only=True — без него промпт прежний (см. tests/smoke_test).
ENGLISH_ONLY_BLOCK = """
\n\U0001F1FA\U0001F1F8 ALWAYS ANSWER IN ENGLISH:
Reply in English ONLY, in every message, even if the student writes in Russian.
If the student switches to Russian, answer in simple English anyway — they
need the English input. If you must clarify something, use very simple English
with a short example the student can repeat. Never explain that you are
speaking English — just speak it.
"""


def _english_only_block(english_only=False):
    """Блок «только по-английски». Пусто, если не запрошен."""
    return ENGLISH_ONLY_BLOCK if english_only else ""


# ---------- американский английский (необязательно) ----------
# Жалоба ученика 20.10.2026: Джейн учила книжным словам (greeting,
# salutation, «it is a warm greeting») и британским формам. Модель по
# умолчанию тянется к учебниковому регистру, поэтому просим прямо:
# американский английский и слова, которые люди реально говорят.
# ВАЖНО: блок добавляется только при american=True — без него промпт
# остаётся прежним байт-в-байт (правило §10, см. tests/smoke_test).
AMERICAN_ENGLISH_BLOCK = """
\n\U0001F1FA\U0001F1F8 USE AMERICAN ENGLISH (US):
Spell and speak American English, never British: color, favorite, traveling,
organize, apartment, elevator, movie, vacation, store, soccer, fall, math,
"at the doctor". Never «colour», «favourite», «travelling», «film», «shop»,
«holiday», «practise».
Use the words people really say in the US today. Never bookish or
dictionary-style words: greeting, salutation, commence, purchase, assist.
Teach the everyday word first: "hi" (not "greetings"), "say hello" (not
"exchange greetings"), "thanks" (not "I am grateful").
When you teach a new word, give ONE natural word plus a short example the
student could really say, not a list of synonyms.
"""


def _american_block(american=False):
    """Блок про американский английский. Пусто, если не запрошен."""
    return AMERICAN_ENGLISH_BLOCK if american else ""

# ---------- экзамен: ровно 10 вопросов (необязательно) ----------
# Проверочное занятие блока (lesson.CHECK) = экзамен. Решения ученика
# 24.10.2026 (PROJECT_STATE.md §20): ровно 10 вопросов, ответ 0/1/2,
# проходной 6 из 10. ВАЖНО: блок добавляется только при exam=True —
# без него промпт остаётся прежним байт-в-байт (правило §10, smoke_test).
EXAM_BLOCK_TEMPLATE = """
\n\U0001F3AF EXAM MODE - CHECK OF THIS BLOCK:
This is an exam, not a lesson. Ask EXACTLY {questions} questions in total,
one short question at a time, and wait for the answer before the next one.
ONE QUESTION PER REPLY: put exactly one question mark in each reply.
If you want to give options, keep them inside that single question
(for example: "Do you meet them on Saturday or on Sunday?"). Never ask
two questions in one reply and never add a follow-up question.
Ask only about what this block covered. Do not teach, do not explain, and
do not give hints or translations - even if the student asks for them.
Never say the answer or finish the student's sentence for them.
Do not correct mistakes out loud during the exam: remember them silently.
If the student is silent or answers in Russian, move on to the next question.
"""



# Счётчик вопросов. Живой прогон 25.10.2026 (logs/exam_live_run.txt) показал:
# правило «ровно 10 вопросов» модель НЕ считает — на 8-м ответе сама закрыла
# экзамен, а потом спросила ещё раз. Поэтому на каждый ход подставляем номер:
# «уже спрошено N из 10, спрашивай вопрос N+1». Без числа блок прежний.
EXAM_COUNTER_TEMPLATE = """
PROGRESS: the student has already answered {asked} of {questions} questions.
Ask question {nxt} of {questions} now - one question, nothing else. Do not
summarise, do not say goodbye and do not end the exam before question {questions}.
"""

EXAM_COUNTER_LAST = """
PROGRESS: the student has answered all {questions} questions. The exam is over:
ask NOTHING more. Give one short warm summary of the block and stop.
"""


def _exam_block(exam=False, questions=None, asked=None):
    """Блок «идёт экзамен». Пусто, если экзамена нет (обратная совместимость).

    asked — сколько вопросов уже задано (None = счётчик не подставляем,
    текст блока остаётся прежним байт-в-байт для старых проверок).
    """
    if not exam:
        return ""
    try:
        qty = max(1, int(questions))
    except (TypeError, ValueError):
        qty = 10
    text = EXAM_BLOCK_TEMPLATE.format(questions=qty)
    if asked is None:
        return text
    try:
        done = max(0, int(asked))
    except (TypeError, ValueError):
        return text
    # модель не считает сама: 0 вопросов уже задано (затравка) — спроси первый
    if done <= 0:
        return text + EXAM_COUNTER_TEMPLATE.format(asked=0, nxt=1,
                                                   questions=qty)
    if done >= qty:
        return text + EXAM_COUNTER_LAST.format(questions=qty)
    return text + EXAM_COUNTER_TEMPLATE.format(asked=done, nxt=done + 1,
                                               questions=qty)


def detect_language(text):
    """Есть кириллица → 'ru', иначе 'en'."""
    return "ru" if any(c in _RUSSIAN_CHARS for c in (text or "").lower()) else "en"


# ---------- язык ответа: выбирает САМА модель ----------
# Раньше в промпте стоял ЖЁСТКИЙ приказ языка («Answer ONLY in English» /
# «Ответь на русском…»). Из-за него язык «залипал» (одного русского вопроса
# хватало, чтобы Джейн отвечала по-русски до конца сессии, даже на английские
# реплики), а ещё Джейн вслух проговаривала саму инструкцию («ты попросил
# ответить только на русском»). Теперь политика МЯГКАЯ: Джейн зеркалит язык
# собеседника, как живой преподаватель, и НЕ объявляет, на каком языке говорит.
LANGUAGE_POLICY = (
    "Reply in the same language the student is using right now: English for English, "
    "Russian for Russian; if they mix languages, follow the language of their latest "
    "sentence. Keep it short and natural. As a teacher you may gently encourage "
    "English, but never announce, explain or lecture about which language you use."
)


def language_instruction(lang):
    """Политика языка ответа. Язык выбирает МОДЕЛЬ (мягкое зеркалирование).

    Параметр lang сохранён для совместимости, но политика от него не зависит:
    живой преподаватель подстраивается под собеседника, а не под флаг.
    """
    return LANGUAGE_POLICY




def _mistake_line(err):
    """Строка «недавней ошибки» для промпта.

    После роли-Аналитика у ошибки есть поля wrong/correct/note — показываем
    именно их («go → went»). Раньше использовался jane_response, и в промпт
    попадал ОТВЕТ САМОЙ Джейн (в т.ч. её фолбэк «Извините, я не могу
    ответить на это.») как будто это ошибка ученика — промпт засорялся.
    Старые записи (без wrong/correct) читаются как раньше — по jane_response.
    """
    if not isinstance(err, dict):
        return ""
    wrong = str(err.get("wrong") or "").strip()
    correct = str(err.get("correct") or "").strip()
    if wrong or correct:
        text = ("%s → %s" % (wrong, correct)) if (wrong and correct) else (wrong or correct)
    else:
        text = str(err.get("jane_response") or "")
    return text[:50]

# ---------- запинки в речи (ученик говорит вслух) ----------
# ЗАМЕР 25.10.2026 (фраза «the park in the park», урок city/1.1, A2, с историей):
# БЕЗ правила учитель исправлял запинку 5 раз из 10, С правилом — 0 из 10.
# Решения ученика: запинку НЕ склеивать, на всех уровнях НЕ замечать.
HESITATION_BLOCK = """
\n\u26A0\uFE0F SPEECH HESITATIONS: the student talks aloud, so they often repeat a word
or a phrase ("the park in the park", "I I think"). This is a natural hesitation,
NOT a mistake: do not correct it, do not mention it, do not explain it. Answer
the meaning of the LAST version of what they said.
"""


def _hesitation_block(flag):
    """Блок про запинки. Пусто, если выключен (промпт прежний байт-в-байт)."""
    return HESITATION_BLOCK if flag else ""


# ---------- значения и формы слов при исправлении (26.10.2026) ----------
# Живой случай: ученик написал «I go to lie down» (лечь), а память подсказала
# ему «lie — лгать» — и он решил, что исправление неверное. Ответ был верен,
# но объяснения не было. Решение ученика: правило ОБЩЕЕ для всех слов
# (lie/lay, left, bank, watch…), а не только про lie.
# ВАЖНО: блок включается флагом (как запинки) — без флага вывод
# build_system_prompt остаётся прежним байт-в-байт (tests/smoke_test).
WORD_FORMS_BLOCK = """
\n\U0001F4D6 WORD MEANINGS AND WORD FORMS - BE EXACT:
One English word can have several meanings (lie = to be flat / to say
something untrue; lay = to put down; left = direction / went away; right,
bank, bear, book, watch, date, spring, can, light). Before you correct a
word, make sure YOUR meaning is the same as the meaning the student had.
- If the word also means something else, name the meaning you mean in ONE
  short line: "lie down = to get into a flat position (a lie = something
  untrue)".
- Never replace the student's word with a word that means something else.
- When a verb form is wrong, show the forms: lie - lay - lain (to be flat),
  lie - lied - lied (to say something untrue).
- If the standard and the colloquial form differ (lie down / lay down), say
  in one line which one is standard, and do not repeat that correction in
  later replies.
Then go on with the lesson: one short sentence, not a grammar lecture.
"""


def _word_forms_block(flag):
    """Блок «значения и формы слов». Пусто, если выключен (промпт прежний)."""
    return WORD_FORMS_BLOCK if flag else ""

# ---------- вопросы «по жизни»: не спрашивать бессмыслицу (26.10.2026) ----------
# Живой случай: Вербот в уроке про dentist спросил «Do you watch a movie?»
# (в кабинете стоматолога кино не смотрят), а на поправку ученика ответил
# двумя извинениями и новой выдумкой «before / after the dentist».
# Модель маленькая (4B): совсем убрать такие сбои нельзя, но блок сильно
# уменьшает их — правило простое и проверяемое на каждом вопросе.
# ВАЖНО: блок включается флагом (как запинки и значения слов) — без флага
# вывод build_system_prompt прежний байт-в-байт (tests/smoke_test).
LOGIC_BLOCK = """
\n\U0001F9E0 THINK BEFORE YOU ASK - A QUESTION MUST MAKE SENSE:
- Before you ask, check the question against real life and against what the
  student already said. If the situation is impossible or the answer is
  obvious, do not ask it - ask something else.
- Never invent facts about a place or a situation and then ask about them.
  A dentist's office is not a cinema: "Do you watch a movie at the dentist?"
  is a bad question.
- Ask about the student's own life: what they do, how often, with whom, why,
  how they feel. Never ask about something they cannot know.
- Build the question on the student's own words: take one word from their
  answer and go one step further ("I go once a month" - "Who goes with
  you?"). If you have nothing to build on, ask about their day or plans.
- ONE question per reply, at the end. Never two questions in a row and never
  a question inside a question.
- If the student says your question is silly or wrong: agree in ONE short
  line ("You're right, that was a silly question."), then ask a better
  question that follows from what they just said. Do not apologize twice, do
  not defend the question, do not explain why you asked it.
"""


def _logic_block(flag):
    """Блок «вопрос должен иметь смысл». Пусто, если выключен (промпт прежний)."""
    return LOGIC_BLOCK if flag else ""


def build_system_prompt(mode, profile, lang="en", level=None, student=None, context=None, plan=None, lesson=None, now=None, variety=False, english_only=False, words=None, american=False, teacher=None, exam=False, exam_questions=None, hesitation=False, exam_asked=None, word_forms=False, logic=False):
    """Собирает system-промпт (персона + профиль ученика).

    mode:    'lesson' | 'free'
    profile: словарь из profile_store
    lang:    'ru' | 'en' — на каком языке отвечать
    student: личность из user_manager (name/gender) — необязательно;
             None → блок не добавляется (обратная совместимость)
    context: методические заметки (RAG) — необязательно;
             None/пусто → блок не добавляется (обратная совместимость)
    plan:    текст плана урока (Планировщик) — необязательно;
             None/пусто → блок не добавляется (обратная совместимость)
    lesson:  словарь идущего занятия {"title","type","topic"} — необязательно;
             None/пусто → блок не добавляется (обратная совместимость)
    now:     datetime «сейчас» — необязательно; None → блок не добавляется
    variety: True → добавить блок против повторов в беседе
    english_only: True → отвечать ТОЛЬКО по-английски (полное погружение)
    words:   слова ученика для вплетения в разговор ["ключ — key", …] —
             необязательно; None/пусто → блок не добавляется
    american: True → американский английский (слова и написание), False →
             блок не добавляется (промпт прежний байт-в-байт)
    teacher: как зовут преподавателя у ЭТОГО ученика (поле профиля
             teacher_name). None → config.TEACHER_NAME («Verbot»).
    exam:    True → занятие идёт как ЭКЗАМЕН (ровно exam_questions вопросов,
             без подсказок и разбора по ходу); False → блок НЕ добавляется
             (промпт прежний байт-в-байт, потому что аргумент в конце).
    exam_questions: сколько вопросов на экзамене (по умолчанию 10).
    exam_asked: сколько вопросов экзамена уже задано. None → счётчик не
             подставляем (блок прежний байт-в-байт для smoke_test и старых
             проверок); число → «спрашивай вопрос N+1 из 10».
    hesitation: True → блок про запинки в речи (ученик говорит вслух, повтор — не
             ошибка). False → блок НЕ добавляется (промпт прежний байт-в-байт,
             его сверяет smoke_test).
    logic:   True → блок «вопрос должен иметь смысл» (не спрашивать
             бессмыслицу, не выдумывать факты о ситуации). False → блок НЕ
             добавляется (промпт прежний байт-в-байт, его сверяет smoke_test).
    """
    language_rule = language_instruction(lang)
    # имя преподавателя — одно на весь промпт (персона + строка про ученика)
    name = teacher_name(teacher)

    grammar_mistakes = profile.get("mistakes", {}).get("grammar", [])
    vocab_mistakes = profile.get("mistakes", {}).get("vocabulary", [])

    recent_grammar = [_mistake_line(err) for err in grammar_mistakes[-5:]]
    recent_vocab = [_mistake_line(err) for err in vocab_mistakes[-5:]]

    strengths = profile.get("strengths", [])[-3:]
    strengths_text = "\n".join([f"- {s.get('jane_response', '')[:50]}" for s in strengths]) if strengths else "Not enough data yet."

    topics_passed = profile.get("topics_passed", [])
    topics_str = ", ".join(topics_passed[-5:]) if topics_passed else "None yet."

    total_lessons = profile.get("total_lessons", 0)

    if mode == "lesson":
        prompt = f"""You are {name}, a helpful AI assistant.
    {language_rule}
    {female_identity(teacher)}
    The student is Russian-speaking, but respond in the language they use.

    📊 STUDENT PROGRESS PROFILE:
    Topics covered: {topics_str}
    Recent grammar mistakes: {', '.join(recent_grammar) if recent_grammar else 'None'}
    Recent vocabulary issues: {', '.join(recent_vocab) if recent_vocab else 'None'}
    Strengths: {strengths_text}
    Total lessons: {total_lessons}

    Your task: help the student improve their English. If they speak Russian, answer in Russian. If they speak English, answer in English.
    Keep responses short (2-3 sentences). Use colorful emojis to make conversation more engaging and friendly (like in messengers): {EMOJIS}
    Do NOT use thought tags (like <|thought|>).
    """
    else:
        prompt = f"""You are {name}, a friendly AI companion.
    {language_rule}
    {female_identity(teacher)}
    Respond naturally in the same language as the student.
    The student has completed {total_lessons} lessons.
    Be supportive and helpful. Use emojis freely: {EMOJIS}
    """
    return (prompt + _level_block(profile, level)
            + _weak_topics_block(profile) + _student_block(student, teacher)
            + _lesson_block(lesson) + _now_block(now)
            + _variety_block(variety) + _english_only_block(english_only)
            + _american_block(american)
            + _plan_block(plan) + _knowledge_block(context)
            + _hesitation_block(hesitation)
            + _word_forms_block(word_forms)
            + _logic_block(logic)
            + _words_block(words)
            + _exam_block(exam, exam_questions, exam_asked))


def build_messages(system_prompt, history, user_text):
    """Собирает СПИСОК сообщений (OpenAI-формат) для нашего llm_client.

    Возвращает [{"role": "system", ...}, {"role": "user"/"assistant", ...}, …,
    {"role": "user", "content": user_text}]. Разметку под конкретную модель
    (<start_of_turn>… и т.п.) применяет САМ сервер llama.cpp, поэтому теги
    вручную НЕ расставляем.

    История у нас хранится строками «Student: …» / «Assistant: …» (так было и
    раньше) — здесь превращаем их в роли user/assistant. Так модель видит
    живую беседу и НЕ считает каждую реплику новой сессией.
    """
    messages = [{"role": "system", "content": system_prompt}]
    for line in (history or [])[-6:]:
        line = str(line)
        if line.startswith("Student: "):
            messages.append({"role": "user", "content": line[9:]})
        elif line.startswith("Assistant: "):
            messages.append({"role": "assistant", "content": line[11:]})
    messages.append({"role": "user", "content": user_text})
    return messages


def clean_response(text):
    """Убирает служебные теги Gemma из ответа модели."""
    if not text:
        return ""
    # «Канал размышлений» Gemma: <|channel>thought ... <channel|> (или до
    # конца). Модель «думает вслух», и этот блок ученику показывать нельзя.
    text = re.sub(r"<\|channel>\s*\w*\s*.*?(<channel\|>|<end_of_turn>|$)",
                  "", text, flags=re.DOTALL)
    text = text.replace("<channel|>", "")
    text = re.sub(r'<\|thought\|>.*?(\n|$)', '', text, flags=re.DOTALL)
    text = re.sub(r'<\|.*?\|>', '', text)
    text = re.sub(r'<end_of_turn>.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'<end_of_turn>', '', text)
    # Вариант тега без «of»: <end_turn>, <start_of_turn>, </s>… Модель пишет
    # и так — раньше тег «протекал» и в чат, и в озвучку.
    text = re.sub(r"</?\s*(?:start_of_turn|end_of_turn|end_turn|turn|eot|im_end|s)\s*>",
                  "", text, flags=re.IGNORECASE)
    # Markdown-разметка: в этом чате она не рендерится, поэтому «**» ученик
    # видит как звёздочки и слышит их же в озвучке — снимаем.
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*•]\s+", "", text)
    # Курсив ОДНОЙ звёздочкой: модель пишет «*before* you go», и ученик
    # видел звёздочки в чате (живой скриншот 26.10.2026). В озвучке они
    # уже снимались (tts._SPEECH_ARTIFACTS_RE), а в тексте — нет.
    # Берём только пару вокруг слова: «2*3*4» не трогаем.
    text = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r'RU$', '', text).strip()
    return text.strip()


def fallback_response(lang):
    return FALLBACK_RU if lang == "ru" else FALLBACK_EN
