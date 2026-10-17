# -*- coding: utf-8 -*-
# =========================================================
# MOOD.PY — настроение текста Джейн (для «актёрской игры» лица)
# =========================================================
# Зачем: робот должен реагировать не только на реплики ученика, но и на то,
# ЧТО ОН САМ ГОВОРИТ. «Сначала было весело, потом грустно» — лицо должно
# меняться по ходу рассказа.
#
# Как это делается БЕЗ модели и БЕЗ задержек (уровень 1 «просто»):
#   * режем ответ на предложения;
#   * у каждого предложения считаем «очки» настроения по трём признакам:
#       - эмодзи (Джейн просят их использовать — значит текст уже размечен!),
#       - ключевые слова (en + ru),
#       - пунктуация (!! ! ? …);
#   * переводим очки в настроение; при сомнении — НЕЙТРАЛЬНО
#     (нейтральное лицо никогда не выглядит глупо, а «неправильная грусть» — да);
#   * склеиваем соседние одинаковые настроения и ограничиваем число смен,
#     чтобы робот не дёргался.
#
# Синхронизация с озвучкой — по ДЛИНЕ текста (символы / скорость речи).
# Точные колбэки из tts.py — на потом: они точнее, но трогают потоковую логику.
#
# Модуль чистый: ни Tk, ни потоков, ни сети — тестируется напрямую.
# =========================================================

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

# ---------------------------------------------------------
# Настроения (совпадают по смыслу с состояниями лица)
# ---------------------------------------------------------
NEUTRAL = "neutral"
HAPPY = "happy"
SAD = "sad"
SURPRISED = "surprised"
THINKING = "thinking"

ALL_MOODS = (NEUTRAL, HAPPY, SAD, SURPRISED, THINKING)

# ---------------------------------------------------------
# Признаки
# ---------------------------------------------------------
HAPPY_EMOJI = set("😊😃😄😁🙂😉🎉🔥💪✨🌟👏🙌❤💖🤗😍🥳😎👍")
SAD_EMOJI = set("😢😔😞💔😟🙁☹😥😓🥺")
SURPRISE_EMOJI = set("😮😲🤯😯😱")
THINK_EMOJI = set("🤔💭🧐")

HAPPY_WORDS = (
    "great", "excellent", "wonderful", "awesome", "perfect", "well done",
    "nice work", "happy", "glad", "love", "fun", "enjoy", "congratulations",
    "отлично", "прекрасно", "здорово", "молодец", "радост", "класс", "супер",
    "весело", "нравится", "люблю", "поздравляю", "ура",
)
SAD_WORDS = (
    "sad", "sorry", "unfortunately", "unhappy", "cry", "lost", "lonely",
    "difficult", "bad news", "upset", "miss you",
    "грустно", "жаль", "печально", "плохо", "потерял", "одиноко",
    "трудно", "расстроен", "сожалею", "увы",
)
SURPRISE_WORDS = (
    "wow", "amazing", "unbelievable", "surprise", "really?",
    "вау", "удивительно", "невероятно", "неужели", "правда?",
)
THINK_WORDS = (
    "hmm", "maybe", "perhaps", "let me think", "i wonder", "probably",
    "думаю", "может быть", "наверное", "возможно", "хм",
)

# Насколько «уверенно» предложение выражает настроение, чтобы его применить
MOOD_THRESHOLD = 2.0

# Скорость речи для оценки длительности (символов в секунду).
# Замер по нашему edge-tts: en ~13-15, ru ~16-18. Берём среднее.
DEFAULT_CPS = 15.0
MIN_SEGMENT_SECONDS = 1.0     # минимум, чтобы не мельтешило
MAX_CHANGES = 3               # не больше стольких смен настроения за реплику

_SENTENCE_RE = re.compile(r"[^.!?…]+[.!?…]*", re.UNICODE)


# ---------------------------------------------------------
# Данные
# ---------------------------------------------------------
@dataclass
class Segment:
    """Кусок реплики с одним настроением."""
    mood: str
    text: str
    seconds: float

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass
class MoodPlan:
    """План «актёрской игры» на одну реплику Джейн."""
    segments: List[Segment] = field(default_factory=list)
    story: bool = False          # рассказ/повествование (взгляд гуляет)

    @property
    def total_seconds(self) -> float:
        return sum(s.seconds for s in self.segments)

    def segment_at(self, seconds: float) -> Optional[Segment]:
        """Какой кусок звучит на секунде seconds."""
        if not self.segments:
            return None
        left = max(0.0, float(seconds))
        for seg in self.segments:
            if left < seg.seconds:
                return seg
            left -= seg.seconds
        return self.segments[-1]

    def mood_at(self, seconds: float) -> str:
        seg = self.segment_at(seconds)
        return seg.mood if seg else NEUTRAL

    def moods(self) -> List[str]:
        return [s.mood for s in self.segments]


# ---------------------------------------------------------
# Оценка настроения предложения
# ---------------------------------------------------------
def _has_any_emoji(text: str, chars: set) -> int:
    return sum(1 for ch in text if ch in chars)


def _word_hits(low: str, words: Tuple[str, ...]) -> int:
    hits = 0
    for word in words:
        if word in low:
            hits += 1
    return hits


def score_sentence(text: str) -> Dict[str, float]:
    """Очки по каждому настроению для одного предложения."""
    text = str(text or "")
    low = text.lower()

    happy = 2.0 * _has_any_emoji(text, HAPPY_EMOJI) + _word_hits(low, HAPPY_WORDS)
    sad = 2.0 * _has_any_emoji(text, SAD_EMOJI) + _word_hits(low, SAD_WORDS)
    surprise = 2.0 * _has_any_emoji(text, SURPRISE_EMOJI) + _word_hits(low, SURPRISE_WORDS)
    thinking = 2.0 * _has_any_emoji(text, THINK_EMOJI) + _word_hits(low, THINK_WORDS)

    # пунктуация: восклицание — энергия, многоточие — раздумье
    if "!" in text:
        happy += 0.6
    if "‼" in text or "!!" in text:
        happy += 0.5
    if "…" in text or "..." in text:
        thinking += 0.6
    if "?" in text:
        surprise += 0.3

    return {HAPPY: happy, SAD: sad, SURPRISED: surprise, THINKING: thinking}


def sentence_mood(text: str) -> str:
    """Настроение одного предложения (или нейтрально, если неясно)."""
    scores = score_sentence(text)
    best_mood, best_score = NEUTRAL, MOOD_THRESHOLD
    for mood, value in scores.items():
        if value >= best_score:
            best_mood, best_score = mood, value
    return best_mood


# ---------------------------------------------------------
# План на всю реплику
# ---------------------------------------------------------
def split_sentences(text: str) -> List[str]:
    """Разбить текст на предложения (сохраняя знаки)."""
    text = str(text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_RE.findall(text)]
    return [p for p in parts if p]


def _estimate_seconds(text: str, cps: float) -> float:
    """Оценка длительности озвучки куска по числу символов."""
    cps = cps if cps and cps > 0 else DEFAULT_CPS
    # паузы на знаках препинания тоже занимают время — добавляем по чуть-чуть
    pauses = text.count(",") * 0.06 + text.count(".") * 0.14 \
        + text.count("!") * 0.14 + text.count("?") * 0.14 + text.count("…") * 0.2
    return max(MIN_SEGMENT_SECONDS, len(text) / cps + pauses)


def _merge_neighbours(segments: List[Segment]) -> List[Segment]:
    """Склеить соседние куски с одинаковым настроением."""
    out: List[Segment] = []
    for seg in segments:
        if out and out[-1].mood == seg.mood:
            out[-1].text = (out[-1].text + " " + seg.text).strip()
            out[-1].seconds += seg.seconds
        else:
            out.append(seg)
    return out


def _limit_changes(segments: List[Segment], max_changes: int) -> List[Segment]:
    """Не больше max_changes смен: самые короткие куски вливаем в предыдущий."""
    while len(segments) > max_changes + 1:
        # ищем самый короткий кусок НЕ первый
        idx = min(range(1, len(segments)), key=lambda i: segments[i].seconds)
        seg = segments.pop(idx)
        prev = segments[idx - 1]
        prev.text = (prev.text + " " + seg.text).strip()
        prev.seconds += seg.seconds
        segments = _merge_neighbours(segments)
        if len(segments) == 1:
            break
    return segments


def plan_reply(text: str, cps: float = DEFAULT_CPS,
               max_changes: int = MAX_CHANGES) -> MoodPlan:
    """Построить план эмоций на реплику Джейн.

    Возвращает куски по предложениям с настроением и оценкой длительности.
    Пустой текст → пустой план (лицо просто останется нейтральным).
    """
    sentences = split_sentences(text)
    if not sentences:
        return MoodPlan(segments=[], story=False)

    segments: List[Segment] = []
    for sentence in sentences:
        mood = sentence_mood(sentence)
        segments.append(Segment(mood=mood, text=sentence,
                                seconds=_estimate_seconds(sentence, cps)))

    # короткие куски приклеиваем к предыдущему — иначе лицо «моргает» смыслом
    cleaned: List[Segment] = []
    for seg in segments:
        if cleaned and seg.seconds < MIN_SEGMENT_SECONDS:
            cleaned[-1].text = (cleaned[-1].text + " " + seg.text).strip()
            cleaned[-1].seconds += seg.seconds
        else:
            cleaned.append(seg)
    segments = _merge_neighbours(cleaned)
    segments = _limit_changes(segments, max_changes)

    # «рассказ»: длинная реплика из нескольких предложений — включаем
    # «гуляющий взгляд» во время речи (эффект живого повествования)
    story = len(sentences) >= 4 and len(str(text)) >= 180

    _log.debug("mood: %s (story=%s, %.1f с)",
               segments and [s.mood for s in segments], story,
               sum(s.seconds for s in segments))
    return MoodPlan(segments=segments, story=story)
