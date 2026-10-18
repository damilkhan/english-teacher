# -*- coding: utf-8 -*-
# =========================================================
# PRONUNCIATION.PY — сверка произношения с английской подсказкой
# =========================================================
# Зачем: ученик получает английскую фразу в экспресс-переводчике, произносит
# её в микрофон — и должен узнать, ПОХОЖЕ ли это на подсказку.
#
# Как: БЕЗ модели и БЕЗ сети. Сравниваем слова услышанного текста (Whisper)
# со словами эталона:
#   * нормализация: регистр, пунктуация, сокращения (I'm → i am), числа;
#   * артикли a/an/the и слова-запинки (um, uh) НЕ считаем ошибкой —
#     Whisper их часто теряет, наказывать за это нечестно;
#   * выравнивание слов (difflib), внутри слова — посимвольная близость:
#     think/sink — «почти», а cat/dog — мимо;
#   * если сказано ЯВНО ДРУГОЕ (ученик ответил своими словами) — вердикт
#     "unrelated": подсказку НЕ показываем, пусть идёт обычный диалог.
#
# Модуль чистый: ни Tk, ни потоков, ни звука — тестируется напрямую.
# =========================================================

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import config

# Вердикты
GOOD = "good"              # ✅ похоже
ALMOST = "almost"          # 🟡 почти (есть что поправить)
OFF = "off"                # 🔁 попробуй ещё
UNRELATED = "unrelated"    # ученик сказал своё — молчим

# Пороги (менять в config.py — «строже/мягче» без правки кода)
DEFAULT_GOOD = 0.82
DEFAULT_ALMOST = 0.50
DEFAULT_RELATED = 0.34     # ниже — считаем, что сказано СВОЁ, а не эталон
# Посимвольная близость слова → «почти то же слово» (think/sink = 0.67,
# key/keys = 0.86, cat/dog = 0). Ниже 0.6 — уже другое слово.
CLOSE_WORD = 0.60

# Артикли и запинки: их пропуск/появление ошибкой не считаем
_NOISE = {"a", "an", "the", "um", "uh", "er", "ah", "oh", "hmm", "mm", "eh"}

# Сокращения → полная форма (сравниваем по словам, а не по символам)
_CONTRACTIONS = {
    "i'm": "i am", "i've": "i have", "i'll": "i will", "i'd": "i would",
    "you're": "you are", "you've": "you have", "you'll": "you will",
    "he's": "he is", "she's": "she is", "it's": "it is",
    "we're": "we are", "we've": "we have", "we'll": "we will",
    "they're": "they are", "they've": "they have", "they'll": "they will",
    "that's": "that is", "there's": "there is", "what's": "what is",
    "who's": "who is", "where's": "where is", "let's": "let us",
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "isn't": "is not", "aren't": "are not", "wasn't": "was not",
    "weren't": "were not", "haven't": "have not", "hasn't": "has not",
    "hadn't": "had not", "can't": "can not", "cannot": "can not",
    "won't": "will not", "wouldn't": "would not", "couldn't": "could not",
    "shouldn't": "should not", "mustn't": "must not",
    "gonna": "going to", "wanna": "want to", "gotta": "got to",
    "kinda": "kind of", "sorta": "sort of",
}

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve "
         "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
         60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}

_WORD_RE = re.compile(r"[a-z']+")
_NUM_RE = re.compile(r"\b(\d{1,3})\b")
_CYR_RE = re.compile(r"[\u0400-\u04FF]")


def _number_to_words(value: int) -> str:
    """Число 0..999 словами (нужно для сравнения «2» и «two»)."""
    if value < 20:
        return _ONES[value]
    if value < 100:
        tens, rest = divmod(value, 10)
        head = _TENS.get(tens * 10, "")
        return (head + (" " + _ONES[rest] if rest else "")).strip() or str(value)
    hundreds, rest = divmod(value, 100)
    head = _ONES[hundreds] + " hundred"
    if rest:
        return head + " " + _number_to_words(rest)
    return head


def has_cyrillic(text) -> bool:
    """Есть ли русские буквы (такую речь со сверкой не сравниваем)."""
    return bool(_CYR_RE.search(str(text or "")))


def normalize_words(text) -> List[str]:
    """Текст → список «слов для сравнения» (регистр, сокращения, числа).

    Артикли и запинки ВЫБРАСЫВАЮТСЯ: их потеря/появление не ошибка.
    """
    low = str(text or "").lower().replace("\u2019", "'")
    low = _NUM_RE.sub(lambda m: _number_to_words(int(m.group(1))), low)
    words: List[str] = []
    for token in _WORD_RE.findall(low):
        expanded = _CONTRACTIONS.get(token)
        if expanded is not None:
            parts = expanded.split()
        else:
            parts = [token]
        for part in parts:
            part = part.strip("'")
            if part and part not in _NOISE:
                words.append(part)
    return words


def _word_similarity(reference: str, heard: str) -> float:
    """1.0 — то же слово, ~0.6 — «почти» (think/sink), 0 — разное."""
    if reference == heard:
        return 1.0
    ratio = difflib.SequenceMatcher(None, reference, heard).ratio()
    if ratio >= CLOSE_WORD:
        return 0.6
    return ratio * 0.3


@dataclass
class WordDiff:
    """Расхождение по одному слову: что надо и что прозвучало."""
    reference: Optional[str]
    heard: Optional[str]
    status: str                    # ok | close | miss | missing | extra

    @property
    def fixed(self) -> bool:
        """Слово не требует внимания."""
        return self.status == "ok"


@dataclass
class Report:
    """Итог сверки одной реплики с подсказкой."""
    verdict: str = UNRELATED
    score: float = 0.0
    reference: str = ""
    heard: str = ""
    diffs: List[WordDiff] = field(default_factory=list)

    @property
    def show(self) -> bool:
        """Показывать ли вердикт ученику (своя фраза — не показываем)."""
        return self.verdict != UNRELATED

    def mistakes(self, limit: int = 3) -> List[WordDiff]:
        """Слова, о которых стоит сказать (по одному разу каждое)."""
        out: List[WordDiff] = []
        seen = set()
        for diff in self.diffs:
            if diff.fixed:
                continue
            key = (diff.reference, diff.heard)
            if key in seen:
                continue
            seen.add(key)
            out.append(diff)
            if len(out) >= limit:
                break
        return out

    @property
    def message(self) -> str:
        """Готовая строка для полосы подсказки (пустая — молчим)."""
        if not self.show:
            return ""
        if self.verdict == GOOD:
            return "✅ Похоже!"
        pairs = []
        for diff in self.mistakes():
            if diff.reference and diff.heard:
                pairs.append("«%s» вместо «%s»" % (diff.heard, diff.reference))
            elif diff.reference:
                pairs.append("пропустил «%s»" % diff.reference)
            elif diff.heard:
                pairs.append("лишнее «%s»" % diff.heard)
        detail = (": " + ", ".join(pairs)) if pairs else ""
        if self.verdict == ALMOST:
            return "🟡 Почти" + detail
        return "🔁 Попробуй ещё" + detail


def _threshold(name: str, default: float) -> float:
    """Порог из config.py (если его там нет — разумное значение по умолчанию)."""
    try:
        return float(getattr(config, name, default))
    except (TypeError, ValueError):
        return default


def _align(reference: List[str], heard: List[str]) -> List[WordDiff]:
    """Выровнять слова эталона и услышанного → список расхождений."""
    matcher = difflib.SequenceMatcher(None, reference, heard, autojunk=False)
    diffs: List[WordDiff] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for word in reference[i1:i2]:
                diffs.append(WordDiff(word, word, "ok"))
            continue
        ref_part = reference[i1:i2]
        heard_part = heard[j1:j2]
        for index in range(max(len(ref_part), len(heard_part))):
            ref_word = ref_part[index] if index < len(ref_part) else None
            heard_word = heard_part[index] if index < len(heard_part) else None
            if ref_word and heard_word:
                sim = _word_similarity(ref_word, heard_word)
                status = "close" if sim >= 0.6 else "miss"
                diffs.append(WordDiff(ref_word, heard_word, status))
            elif ref_word:
                diffs.append(WordDiff(ref_word, None, "missing"))
            else:
                diffs.append(WordDiff(None, heard_word, "extra"))
    return diffs


def compare(reference, heard) -> Report:
    """Сверить услышанное с английской подсказкой.

    reference — эталон (например, фраза из переводчика);
    heard — текст, распознанный Whisper.

    Вердикты: good (похоже), almost (почти), off (попробуй ещё),
    unrelated (сказано СВОЁ — вердикт не показываем).
    """
    report = Report(reference=str(reference or ""), heard=str(heard or ""))
    if not report.reference.strip() or not report.heard.strip():
        return report

    ref_words = normalize_words(report.reference)
    if not ref_words:
        return report

    # русская речь — это не попытка произнести английскую фразу
    if has_cyrillic(report.heard):
        return report

    heard_words = normalize_words(report.heard)
    if not heard_words:
        return report

    diffs = _align(ref_words, heard_words)
    report.diffs = diffs

    total = sum(1.0 if d.status == "ok" else
                0.6 if d.status == "close" else
                (_word_similarity(d.reference, d.heard) * 0.3 if d.reference and d.heard else 0.0)
                for d in diffs)
    scale = max(len(ref_words), len(heard_words)) or 1
    report.score = max(0.0, min(1.0, total / scale))

    in_ref = [d for d in diffs if d.reference]
    related = sum(1 for d in in_ref if d.status in ("ok", "close")) / (len(in_ref) or 1)

    good = _threshold("PRON_GOOD", DEFAULT_GOOD)
    almost = _threshold("PRON_ALMOST", DEFAULT_ALMOST)
    related_min = _threshold("PRON_RELATED", DEFAULT_RELATED)

    # «сказано своё»: слов заметно больше/меньше и совпадений мало
    if related < related_min or report.score < almost * 0.6:
        report.verdict = UNRELATED
        return report
    if report.score >= good and all(d.fixed for d in diffs):
        report.verdict = GOOD
    elif report.score >= almost:
        report.verdict = ALMOST
    else:
        report.verdict = OFF
    return report


def reference_from_hint(english, single=False) -> str:
    """Какой текст из подсказки считать эталоном.

    Фраза → сама фраза. Одно слово → строка вида
    «key — Open the door with this key.»: эталоном берём ПРИМЕР (после «—»),
    потому что ученик произносит фразу целиком, а не слово-ключ.
    """
    text = str(english or "").strip()
    if not text:
        return ""
    if not single:
        return text
    for dash in ("\u2014", "-", ":"):
        if dash in text:
            tail = text.split(dash, 1)[1].strip()
            if tail:
                return tail
    return text
