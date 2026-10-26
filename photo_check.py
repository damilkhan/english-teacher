# -*- coding: utf-8 -*-
# =========================================================
# PHOTO_CHECK.PY — мягкая проверка грамматики в описании фото
# =========================================================
# Задание «опиши фото» проверяет ТОЛЬКО длину и разнообразие слов
# (picture_task.py). Грамматику оно не смотрит, поэтому ученик видел
# «Well done!» даже с ошибками (живой случай 26.10.2026: «they are staying
# near the bus», «waiting when the doors will open»).
#
# Как проверяем (по замерам §18, 23.10.2026):
#   * просим у модели ИСПРАВЛЕННЫЙ ТЕКСТ, а не список правок — так модель
#     почти не выдумывает того, чего не было (0 ложных правок на 6 верных
#     текстах);
#   * изменения считает КОД (difflib по словам), а не модель;
#   * оценку («всё верно» / «вот лучше») ставит тоже код.
# Модуль чистый: ни Tk, ни сети, ни модели — только текст на входе.
# =========================================================

import difflib
import re


MAX_NOTES = 4            # сколько правок показываем списком
MAX_CHANGED_SHARE = 0.50  # больше половины слов изменено → модель переписала
_WORD_RE = re.compile(r"[A-Za-z']+")


def words(text):
    """Слова описания (латиница и апостроф), в нижнем регистре."""
    return _WORD_RE.findall(str(text or "").lower())


def _surface(text):
    """Слова КАК НАПИСАНЫ (для показа правки «staying → standing»)."""
    return _WORD_RE.findall(str(text or ""))


# ---------- промпт модели ----------
CHECK_SYSTEM = (
    "You are a careful English teacher. The student (level {level}) wrote a",
    "short description of a photo. Fix ONLY real mistakes: grammar, word",
    "order, wrong or MISSING words, spelling. You may add a missing word or",
    "two (for example \"It is possible ...\" instead of \"Possible ...\"), but do",
    "NOT add new facts, opinions or details about the photo, and do not add",
    "extra sentences or make the text more beautiful. Keep the student's own",
    "words and level wherever they are acceptable English. If the text is",
    "already correct, return it EXACTLY as it is. Reply with the corrected",
    "text ONLY: no comments, no questions, no quotation marks, no list. "
    "Also fix sentence fragments that are not full sentences: add the missing "
    "subject or verb (for example \"Possible they are waiting\" -> \"It is possible "
    "they are waiting\").",
)


def build_messages(description, level=""):
    """Сообщения для модели: системная просьба + сам текст ученика."""
    system = " ".join(CHECK_SYSTEM).format(level=(str(level or "").strip() or "A2"))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": str(description or "").strip()},
    ]


# ---------- разбор ответа модели ----------
_LABEL_RE = re.compile(
    r"^\s*(corrected(\s+text)?|correction|fixed(\s+text)?|here(\s+is)?|result|output|answer|text)\s*[:\-]\s*",
    re.IGNORECASE)


def clean_corrected(raw):
    """Вытащить из ответа модели сам исправленный текст.

    Модель любит добавлять «Corrected:», кавычки, звёздочки и пояснения
    после текста. Берём первую содержательную строку (или абзац), снимаем
    метку и обрамляющие кавычки.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    # блок ```...``` — берём его содержимое
    fence = re.search(r"```[a-zA-Z]*\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    line = lines[0]
    line = _LABEL_RE.sub("", line)
    line = line.strip().strip("*_`'\"\u00ab\u00bb").strip()
    line = line.strip()
    for pair in (('"', '"'), ("'", "'"), ("\u201c", "\u201d"), ("\u00ab", "\u00bb")):
        if len(line) > 1 and line.startswith(pair[0]) and line.endswith(pair[1]):
            line = line[1:-1].strip()
    return re.sub(r"\s+", " ", line).strip()


# ---------- сравнение «как было / как стало» ----------
def is_sane(original, corrected):
    """Похоже ли, что модель ИСПРАВИЛА текст, а не написала свой.

    Если ответ пустой, втрое длиннее или короче, или изменено больше
    половины слов — проверку не показываем: лучше промолчать, чем выдать
    чужой текст за исправление (правило §13: лучше тишина, чем враньё).
    """
    before = words(original)
    after = words(corrected)
    if not after or not before:
        return False
    if not (0.6 <= len(after) / float(len(before)) <= 1.6):
        return False
    return changed_share(original, corrected) <= MAX_CHANGED_SHARE


MERGE_GAP = 0        # склеиваем только СОСЕДНИЕ правки (вставка+удаление)
SHOW_WORDS = 8       # длинную правку обрезаем при показе


def word_changes(original, corrected):
    """Список правок [{"wrong": ..., "right": ...}] по словам.

    Сравнение БЕЗ учёта регистра: «i» → «I» и заглавная буква в начале
    фразы правкой не считаются (Whisper и так ставит их как получится).

    Куски склеиваются: соседние вставка+удаление и недлинные общие слова
    между ними дают ОДНУ правку. Иначе «in this photo a bus station» →
    «a bus stop in this photo» печаталось двумя строками («add a bus stop»
    и «remove a bus station») — ученик видел бессмыслицу.
    """
    before, after = words(original), words(corrected)
    shown_before, shown_after = _surface(original), _surface(corrected)
    ops = difflib.SequenceMatcher(None, before, after,
                                   autojunk=False).get_opcodes()
    spans = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        if spans and i1 - spans[-1][1] <= MERGE_GAP:
            spans[-1][1], spans[-1][3] = i2, j2
            spans[-1][4] = 0        # между правками были общие слова
        else:
            spans.append([i1, i2, j1, j2, 1])
    changes = []
    for i1, i2, j1, j2, _ in spans:
        wrong = " ".join(shown_before[i1:i2]).strip()
        right = " ".join(shown_after[j1:j2]).strip()
        if not wrong and not right:
            continue
        if before[i1:i2] == after[j1:j2]:      # только регистр/знаки
            continue
        changes.append({"wrong": wrong, "right": right})
    return changes


def _short(text, words_limit=None):
    """Обрезать длинную правку для показа (в словах)."""
    limit = SHOW_WORDS if words_limit is None else words_limit
    items = str(text or "").split()
    if len(items) <= limit:
        return str(text or "")
    return " ".join(items[:limit]) + " \u2026"

def changed_share(original, corrected):
    """Доля изменённых слов (0.0 … 1.0) — для проверки «модель переписала»."""
    before = words(original)
    if not before:
        return 0.0
    number = 0
    for item in word_changes(original, corrected):
        number += max(len(item["wrong"].split()), len(item["right"].split()))
    return min(1.0, number / float(len(before)))


# ---------- что показать ученику ----------
GOOD_NOTE = "\u2705 No grammar mistakes in your description \u2014 nice English!"
SPOKEN_GOOD = "No grammar mistakes in your description. Nice English!"


def spans_for_changes(text, changes):
    """Где в ТЕКСТЕ УЧЕНИКА стояли неверные куски → [(начало, конец, "err")].

    Нужно, чтобы подсветить ошибки прямо в его реплике (красным). Ищем по
    СЛОВАМ, без учёта регистра: «Staying» и «staying» — одно и то же.
    Каждый следующий кусок ищем ПОСЛЕ предыдущего, иначе одинаковые слова
    красились бы дважды в одном месте.
    """
    items = [(m.start(), m.end(), m.group(0).lower())
             for m in _WORD_RE.finditer(str(text or ""))]
    if not items:
        return []
    spans = []
    after = 0
    for change in (changes or ()):
        target = str((change or {}).get("wrong") or "").strip().lower().split()
        if not target:
            continue
        found = _find_run(items, target, after)
        if found is None:
            continue
        first, last = found
        spans.append((items[first][0], items[last][1], "err"))
        after = last + 1
    return spans


def _find_run(items, target, after):
    """Первое вхождение последовательности слов начиная с номера after."""
    width = len(target)
    for start in range(max(0, after), len(items) - width + 1):
        if all(items[start + k][2] == target[k] for k in range(width)):
            return start, start + width - 1
    return None


def chat_message(data):
    """Готовое сообщение для чата: {"text", "lines", "spans", "spoken"}.

    Текст БЕЗ эмодзи в начале: раскраска считается по смещениям, а эмодзи в
    облачке — картинка и в индексах tk.Text занимает один символ. Цвет и
    так бросается в глаза, поэтому «\u270f» здесь не нужен.

    spans: исправленный текст — зелёный ("ok"), неверные куски — красный
    ("err"), верные — зелёный. spoken — что произнести голосом.
    """
    data = data or {}
    empty = {"text": "", "lines": [], "spans": [], "spoken": ""}
    if not data.get("ok"):
        return dict(empty)
    corrected = str(data.get("corrected") or "").strip()
    changes = data.get("changes") or []
    if not corrected:
        return dict(empty)
    if not changes:
        return {"text": GOOD_NOTE, "lines": [GOOD_NOTE], "spans": [],
                "spoken": SPOKEN_GOOD}
    prefix = "Better: "
    lines = [prefix + corrected]
    spans = [(len(prefix), len(prefix) + len(corrected), "ok")]
    shown = 0
    for item in changes:
        if shown >= MAX_NOTES:
            break
        wrong = _short(item.get("wrong") or "")
        right = _short(item.get("right") or "")
        if wrong and right:
            line = "\u00b7 %s \u2192 %s" % (wrong, right)
        elif right:
            line = "\u00b7 add \u00ab%s\u00bb" % right
        else:
            line = "\u00b7 remove \u00ab%s\u00bb" % wrong
        base = sum(len(x) + 1 for x in lines)
        lines.append(line)
        if wrong and right:
            spans.append((base + 2, base + 2 + len(wrong), "err"))
            tail_at = base + 2 + len(wrong) + len(" \u2192 ")
            spans.append((tail_at, tail_at + len(right), "ok"))
        elif right:
            at = line.index("\u00ab") + 1
            spans.append((base + at, base + at + len(right), "ok"))
        elif wrong:
            at = line.index("\u00ab") + 1
            spans.append((base + at, base + at + len(wrong), "err"))
        shown += 1
    rest = len(changes) - shown
    if rest > 0:
        lines.append("\u00b7 +%d more" % rest)
    text = "\n".join(lines)
    return {"text": text, "lines": lines, "spans": spans,
            "spoken": "Better. %s" % corrected}


def report(original, corrected):
    """Готовый разбор для чата: ok / corrected / changes / text / spans.

    ok=False — проверку показывать нельзя (модель ответила странно).
    """
    corrected = clean_corrected(corrected)
    if not is_sane(original, corrected):
        return {"ok": False, "corrected": corrected, "changes": [],
                "text": "", "lines": [], "spans": [], "spoken": ""}
    changes = word_changes(original, corrected)
    data = {"ok": True, "corrected": corrected, "changes": changes}
    data.update(chat_message(data))
    return data

def analysis_from(report_data):
    """Правки в виде разбора Аналитика — чтобы они попали в профиль.

    Формат тот же, что у roles.analyst: {"errors": [{"type", "wrong",
    "correct", "note"}]}. Тогда ошибки из описания фото копятся там же, где
    ошибки из разговора (profile_store.record_analysis) — это заодно
    заготовка будущей карты пробелов.
    """
    data = report_data or {}
    errors = []
    for item in (data.get("changes") or []):
        wrong, right = item.get("wrong") or "", item.get("right") or ""
        if not wrong or not right:
            continue
        errors.append({
            "type": "grammar",
            "wrong": wrong[:80],
            "correct": right[:80],
            "note": "photo description"[:80],
        })
    return {"move_type": "A", "move_status": "A", "errors": errors,
            "topics": [], "note": "", "photo": True}

