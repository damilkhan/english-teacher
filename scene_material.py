"""§91.7 (22.11.2026): вопрос учителя должен быть ПРО материал урока.

Живой урок city/4.3: модель спросила «What color was the other phone?» —
цвета второй трубки в сцене НЕТ (есть только «I will take the black one»).
Ученик ответил на этот вопрос и получил «Ответ не на вопрос» (§91.2 судил
уже честно, но урок всё равно стал бессмысленным).

Правило ученика (22.11.2026): режем ТОЛЬКО вопрос, которого нет в материале.
Вопрос про материал оставляем, даже если его нет в списке ask: живой
уточняющий вопрос модели — не мусор.

Как решаем без модели (дёшево и предсказуемо):
  * берём часть реплики, которая является вопросом (после последней точки);
  * выкидываем служебные и «школьные» слова (STOP);
  * выкидываем имена собственные (слово с заглавной НЕ в начале фразы);
  * материал — все слова сцены, вопросов ask, слов урока и названия;
  * если в вопросе осталось слово, которого в материале НЕТ — вопрос вне
    материала, и в нём возвращается это слово (для лога).
"""

# Служебные слова и «школьный обиход»: они не факт о сцене, поэтому не
# считаются выдумкой. Список длинный намеренно: лучше пропустить чужой
# вопрос, чем отрезать верный.
STOP = set("""
a an the and or but so if then than because of in on at to for from with about
by as into over under after before during out off up down back away here there
i you he she it we they me him her us them my your his its our their this that
these those am is are was were be been being do does did done have has had
will would shall should can could may might must not no yes ok okay
what which who whom whose where when why how
very too also just only even still already again ever never always
some any all both each every few little much many more most less least other
another same such own
hello hi hey dear good great nice fine well perfect excellent right sure
please thanks thank sorry
job work done ready try think know mean understand remember forget
say said tell talk speak repeat ask answer question word words sentence
english russian student teacher name lesson task example correct wrong
one ones
""".split())


def _tokens(text):
    """Слова текста: [(слово_в_нижнем_регистре, было_с_заглавной)]."""
    out = []
    buf = []
    upper = False
    for ch in str(text or "") + " ":
        if ch.isalpha() or ch == "'":
            if not buf:
                upper = ch.isupper()
            buf.append(ch)
        else:
            if buf:
                out.append(("".join(buf).lower().replace("'", ""), upper))
                buf = []
    return out


def material_words(lesson):
    """Слова материала урока: сцена, вопросы, слова темы, название, тема."""
    if not isinstance(lesson, dict):
        return set()
    chunks = []
    for row in (lesson.get("scene") or ()):
        if isinstance(row, dict):
            chunks.append(row.get("en") or "")
        else:
            chunks.append(str(row or ""))
    for key in ("ask", "words"):
        for item in (lesson.get(key) or ()):
            chunks.append(str(item or ""))
    chunks.append(str(lesson.get("title") or ""))
    chunks.append(str(lesson.get("topic") or ""))
    # фразы урока, если приложение их положило в payload
    for row in (lesson.get("phrases") or ()):
        if isinstance(row, dict):
            chunks.append(str(row.get("en") or ""))
    bag = set()
    for chunk in chunks:
        for word, _upper in _tokens(chunk):
            if word:
                bag.add(word)
    return bag


def question_only(text):
    """Часть реплики, которая является вопросом (после последней точки).

    «Good job, Damil. What is worse about the small phone?» -> «What is worse
    about the small phone?». Похвала не должна считаться материалом вопроса.
    Нет «?» — вернём весь текст (проверка решит сама).
    """
    body = str(text or "")
    q = body.find("?")
    if q < 0:
        return body
    head = body[:q]
    cut = max(head.rfind("."), head.rfind("!"), head.rfind(";"))
    return body[cut + 1:q + 1] if cut >= 0 else body[:q + 1]


def outside_material(question, lesson):
    """Вопрос вне материала? -> (True/False, слово-виновник или "").

    True, если в вопросе есть слово, которого нет ни в материале, ни в STOP.
    """
    bag = material_words(lesson)
    part = question_only(question)
    suspects = []
    for index, (word, upper) in enumerate(_tokens(part)):
        if not word or len(word) < 3:
            continue
        if word in STOP or word in bag:
            continue
        if index > 0 and upper:
            continue          # имя собственное: Ann, Damil, English
        suspects.append(word)
    if suspects:
        return True, suspects[0]
    return False, ""


def without_question(text):
    """Реплика БЕЗ хвостового вопроса — часть до начала вопроса.

    `prompt_builder.strip_trailing_question` для этого НЕ годится: когда перед
    «?» нет точки, она режет ПО «?» и возвращает сам вопрос без знака —
    получается «What color is it Which phone did Ann take?».

    «That is a good choice. What color was it?» -> «That is a good choice.»
    «What color is it?» -> «» (кроме вопроса в реплике ничего нет).
    """
    body = str(text or "")
    q = body.find("?")
    if q < 0:
        return body.strip()
    head = body[:q]
    cut = max(head.rfind("."), head.rfind("!"), head.rfind(";"))
    if cut < 0:
        return ""
    return body[:cut + 1].strip()

def next_question(lesson):
    """Вопрос из файла урока, который сейчас на очереди (или "")."""
    if not isinstance(lesson, dict):
        return ""
    ask = [str(item).strip() for item in (lesson.get("ask") or ())
           if str(item).strip()]
    if not ask:
        return ""
    try:
        done = int(lesson.get("ask_done") or 0)
    except (TypeError, ValueError):
        done = 0
    done = max(0, min(len(ask) - 1, done))
    return ask[done]
