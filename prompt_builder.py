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

# Отступ 4 пробела у продолжений строк — это ЧАСТЬ текста промпта
# (так было в gui.py). Не «выравнивать» автоформаттером.
FEMALE_IDENTITY = """IMPORTANT: You are Jane, a female AI assistant. When speaking in Russian, ALWAYS refer to yourself in the FEMININE GENDER:
    - Use "я сказала", "я сделала", "я была", "я преподавательница", "я ответила" instead of masculine forms.
    - Use feminine forms of verbs and adjectives (e.g., "я готова", "я уверена", "я думала", "я хотела").
    - This applies to ALL your responses in Russian, regardless of the mode (lesson or free)."""

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
IMPORTANT: in Russian, NEVER use feminine forms about the student — the feminine forms above describe YOU, Jane, not the student.
Answer the student's question directly. Do not show your reasoning, plans or inner thoughts — reply with the final answer only.
"""


def _student_block(student):
    """Блок про личность ученика (имя и род). Пусто, если данных нет.

    Без этого модель не знает имени ученика и угадывает грамматический род
    (в русском — обычно женский, потому что Джейн женского пола).
    """
    student = student or {}
    name = str(student.get("name") or "").strip()
    gender = str(student.get("gender") or "").strip().lower()
    forms = STUDENT_GENDER_FORMS.get(gender)
    if not name and not forms:
        return ""
    return STUDENT_BLOCK_TEMPLATE.format(
        name=name or "the student",
        gender=gender or "unknown",
        forms=forms or STUDENT_GENDER_FORMS["other"],
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

def build_system_prompt(mode, profile, lang="en", level=None, student=None, context=None, plan=None):
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
    """
    language_rule = language_instruction(lang)

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
        prompt = f"""You are Jane, a helpful AI assistant.
    {language_rule}
    {FEMALE_IDENTITY}
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
        prompt = f"""You are Jane, a friendly AI companion.
    {language_rule}
    {FEMALE_IDENTITY}
    Respond naturally in the same language as the student.
    The student has completed {total_lessons} lessons.
    Be supportive and helpful. Use emojis freely: {EMOJIS}
    """
    return (prompt + _level_block(profile, level)
            + _weak_topics_block(profile) + _student_block(student)
            + _plan_block(plan) + _knowledge_block(context))


def build_conversation_prompt(system_prompt, history, user_text, lang):
    """Собирает полный промпт в формате Gemma: system → диалог → реплика ученика.

    История упаковывается в НАСТОЯЩИЕ тёрны Gemma (<start_of_turn>user/model),
    а не «сырыми» строками «Student:/Assistant:». Так модель видит живую
    беседу и НЕ считает каждую реплику новой сессией — раньше она здоровалась
    в КАЖДОМ ответе («Привет, Дамиль!»).

    Жёсткого «Answer ONLY in English» / «ОТВЕТЬ ТОЛЬКО НА РУССКОМ» тут больше
    нет: язык ответа целиком на усмотрение модели (см. LANGUAGE_POLICY), а
    реплика ученика уходит как есть. Параметр lang сохранён для совместимости.
    """
    prompt = f"<start_of_turn>system\n{system_prompt}<end_of_turn>\n"
    for line in (history or [])[-6:]:
        line = str(line)
        if line.startswith("Student: "):
            prompt += f"<start_of_turn>user\n{line[9:]}<end_of_turn>\n"
        elif line.startswith("Assistant: "):
            prompt += f"<start_of_turn>model\n{line[11:]}<end_of_turn>\n"
    prompt += f"<start_of_turn>user\n{user_text}<end_of_turn>\n<start_of_turn>model\n"
    return prompt


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
    text = text.replace("**", "")
    text = re.sub(r'RU$', '', text).strip()
    return text.strip()


def fallback_response(lang):
    return FALLBACK_RU if lang == "ru" else FALLBACK_EN
