# -*- coding: utf-8 -*-
# =========================================================
# EXAM.PY — правила ЭКЗАМЕНА (проверка блока), без модели
# =========================================================
# ЗАЧЕМ. Проверочное занятие в конце блока (lesson.CHECK) = экзамен.
# Договорено с учеником 24.10.2026 (PROJECT_STATE.md, §20):
#   * ровно 10 вопросов;
#   * за ответ 0 / 1 / 2 балла;
#   * итог 0-20 -> делим на 2 -> 0-10, проходной 6 (= 60 %);
#   * обычные уроки за подсказки НЕ наказывают, а на экзамене подсказок
#     нет вообще (решение ученика), поэтому used_hint почти всегда False.
#
# Здесь ТОЛЬКО счёт: ни Tk, ни модели, ни микрофона. Экран и промпт
# берут отсюда готовые числа — так правила проверяются без запуска окна.
# =========================================================

from typing import Any, Dict, List, Optional

# ---------- правила ----------
QUESTIONS = 10              # ровно столько вопросов за экзамен
MAX_PER_ANSWER = 2          # лучший ответ
MAX_TOTAL = QUESTIONS * MAX_PER_ANSWER      # 20
PASS_SCORE = 6              # проходной из 10 (= 60 %, обычная практика оценок)
PASS_TOTAL = PASS_SCORE * 2                 # 12 из 20 (целые числа, без float)
MIN_WORDS = 4               # «по делу»: короче — уже не полный ответ
MAX_ERRORS_FOR_FULL = 1     # 2 ошибки и больше — ответ неполный

_LATIN = set("abcdefghijklmnopqrstuvwxyz")
_CYRILLIC = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")


# =========================================================
# Разбор ответа ученика
# =========================================================
def latin_words(text: Any) -> List[str]:
    """Слова из ЛАТИНСКИХ букв («I like it» -> ['I', 'like', 'it']).

    Цифры, знаки и кириллица в слова не попадают: смешанное слово
    «like!» станет «like», а «привет» — выпадет совсем.
    """
    out: List[str] = []
    word: List[str] = []
    for ch in str(text or ""):
        low = ch.lower()
        if low in _LATIN:
            word.append(ch)
        else:
            if word:
                out.append("".join(word))
                word = []
    if word:
        out.append("".join(word))
    return out


def has_cyrillic(text: Any) -> bool:
    """Есть ли в тексте русские буквы (значит, ответ не по-английски)."""
    return any(ch.lower() in _CYRILLIC for ch in str(text or ""))


def is_english(text: Any) -> bool:
    """Годится ли ответ как английский: есть латиница и нет кириллицы."""
    if has_cyrillic(text):
        return False
    return len(latin_words(text)) > 0


def score_answer(answer: Any, errors: int = 0, used_hint: bool = False) -> int:
    """Балл за ОДИН ответ: 0, 1 или 2 (решение ученика 24.10.2026).

    2 — по-английски, >= 4 слов, без подсказки, <= 1 ошибки;
    1 — по-английски, но короче / с подсказкой / 2+ ошибок;
    0 — пусто, молчание, по-русски (нет латиницы или есть кириллица).
    """
    if not is_english(answer):
        return 0
    try:
        n_err = max(0, int(errors))
    except (TypeError, ValueError):
        n_err = 0
    if len(latin_words(answer)) < MIN_WORDS:
        return 1
    if used_hint:
        return 1
    if n_err > MAX_ERRORS_FOR_FULL:
        return 1
    return MAX_PER_ANSWER


def score_text(score: Any) -> str:
    """«8.5 из 10» — как показывать итог ученику (без хвоста .0)."""
    try:
        val = float(score)
    except (TypeError, ValueError):
        val = 0.0
    if abs(val - round(val)) < 1e-9:
        return "%d из %d" % (int(round(val)), PASS_SCORE + 4)
    return "%.1f из %d" % (val, PASS_SCORE + 4)


def best_of(previous: Any, new: Any) -> float:
    """В профиль идёт ЛУЧШИЙ результат (решение ученика)."""
    vals = []
    for v in (previous, new):
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return max(vals) if vals else 0.0

# =========================================================
# Сессия экзамена
# =========================================================
class ExamSession:
    """Одна сдача экзамена (проверка блока): ровно QUESTIONS ответов.

    Считает баллы, сумму и итог 0-10. Ученику по ходу баллы НЕ показываем
    (как и счётчики обычного занятия) — только в конце (решение ученика).

    Подсказок на экзамене нет вообще, поэтому поле hints всегда 0:
    оно нужно лишь чтобы итог занятия собирался одинаково.
    """

    def __init__(self, lesson_id: str = "", point_id: Optional[str] = None,
                 questions: Optional[int] = None) -> None:
        self.lesson_id = str(lesson_id or "").strip()
        self.point_id = str(point_id or "").strip() or None
        try:
            qty = int(questions) if questions is not None else QUESTIONS
        except (TypeError, ValueError):
            qty = QUESTIONS
        self.questions = max(1, qty)
        self.scores: List[int] = []
        self.hints = 0          # на экзамене подсказок нет (см. докстроку)
        self.mistakes = 0       # сумма ошибок Аналитика за экзамен
        self.aborted = False

    # ---------- свойства ----------
    @property
    def answered(self) -> int:
        """Сколько вопросов уже отвечено."""
        return len(self.scores)

    @property
    def total(self) -> int:
        """Сумма баллов 0..20."""
        return sum(self.scores)

    @property
    def score(self) -> float:
        """Итог 0..10 (сумма делённая на 2)."""
        return self.total / float(MAX_PER_ANSWER)

    @property
    def passed(self) -> bool:
        """Сдал ли: итог >= 6 (= 12 из 20). Считаем целыми, без float."""
        return self.total >= PASS_TOTAL

    @property
    def is_active(self) -> bool:
        """Экзамен идёт (не все вопросы и не прерван)."""
        return not self.aborted and self.answered < self.questions

    @property
    def progress_text(self) -> str:
        """«3/10» — сколько вопросов пройдено."""
        return "%d/%d" % (self.answered, self.questions)

    # ---------- ход экзамена ----------
    def answer(self, text: Any, errors: int = 0,
               used_hint: bool = False) -> Dict[str, Any]:
        """Учесть ОДИН ответ. Возвращает снимок последнего ответа."""
        result = {
            "index": self.answered + 1,
            "score": 0,
            "total": self.total,
            "finished": False,
            "accepted": False,
        }
        if not self.is_active:
            result["finished"] = True
            return result
        pts = score_answer(text, errors=errors, used_hint=used_hint)
        self.scores.append(pts)
        try:
            self.mistakes += max(0, int(errors))
        except (TypeError, ValueError):
            pass
        result.update({
            "score": pts,
            "total": self.total,
            "finished": self.answered >= self.questions,
            "accepted": True,
        })
        return result

    def abort(self) -> None:
        """Прервать экзамен (ученик вышел). НЕ засчитывается."""
        self.aborted = True

    # ---------- итог ----------
    def result(self) -> Dict[str, Any]:
        """Итог для сообщения ученику и записи в профиль."""
        return {
            "lesson_id": self.lesson_id,
            "point_id": self.point_id,
            "questions": self.questions,
            "answers": list(self.scores),
            "correct_full": sum(1 for x in self.scores if x == MAX_PER_ANSWER),
            "total": self.total,
            "max_total": self.questions * MAX_PER_ANSWER,
            "score": round(self.score, 1),
            "max_score": self.questions * MAX_PER_ANSWER / float(MAX_PER_ANSWER),
            "pass_score": PASS_SCORE,
            "passed": self.passed,
            "mistakes": self.mistakes,
            "hints": self.hints,
            "aborted": self.aborted,
            "finished": self.answered >= self.questions and not self.aborted,
        }

    def state(self) -> Dict[str, Any]:
        """Короткий снимок (для колбэков и тестов)."""
        return {
            "lesson_id": self.lesson_id,
            "point_id": self.point_id,
            "answered": self.answered,
            "questions": self.questions,
            "total": self.total,
            "score": round(self.score, 1),
            "passed": self.passed,
            "active": self.is_active,
            "aborted": self.aborted,
        }
