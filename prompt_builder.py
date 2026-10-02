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


def detect_language(text):
    """Есть кириллица → 'ru', иначе 'en'."""
    return "ru" if any(c in _RUSSIAN_CHARS for c in (text or "").lower()) else "en"


def language_instruction(lang):
    if lang == "ru":
        return "Ответь на русском языке, кратко."
    return "Answer in English, keep responses short."


def build_system_prompt(mode, profile, lang="en", level=None):
    """Собирает system-промпт (персона + профиль ученика).

    mode:    'lesson' | 'free'
    profile: словарь из profile_store
    lang:    'ru' | 'en' — на каком языке отвечать
    """
    language_rule = language_instruction(lang)

    grammar_mistakes = profile.get("mistakes", {}).get("grammar", [])
    vocab_mistakes = profile.get("mistakes", {}).get("vocabulary", [])

    recent_grammar = [err.get("jane_response", "")[:50] for err in grammar_mistakes[-5:]]
    recent_vocab = [err.get("jane_response", "")[:50] for err in vocab_mistakes[-5:]]

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
    return prompt + _level_block(profile, level) + _weak_topics_block(profile)


def build_conversation_prompt(system_prompt, history, user_text, lang):
    """Собирает полный промпт в формате Gemma: system → история → user → model."""
    if lang == "ru":
        user_prompt = f"{user_text}\n\nОТВЕТЬ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ. НЕ ИСПОЛЬЗУЙ АНГЛИЙСКИЙ."
    else:
        user_prompt = f"{user_text}\n\nAnswer ONLY in English. Do NOT use Russian."

    prompt = f"<start_of_turn>system\n{system_prompt}<end_of_turn>\n"
    if history:
        history_str = "\n".join(history[-6:]) + "\n"
        prompt += history_str
    prompt += f"<start_of_turn>user\n{user_prompt}<end_of_turn>\n<start_of_turn>model\n"
    return prompt


def clean_response(text):
    """Убирает служебные теги Gemma из ответа модели."""
    if not text:
        return ""
    text = re.sub(r'<\|thought\|>.*?(\n|$)', '', text, flags=re.DOTALL)
    text = re.sub(r'<\|.*?\|>', '', text)
    text = re.sub(r'<end_of_turn>.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'<end_of_turn>', '', text)
    text = re.sub(r'RU$', '', text).strip()
    return text.strip()


def fallback_response(lang):
    return FALLBACK_RU if lang == "ru" else FALLBACK_EN
