"""Работа над ошибками (§80): правила сессии и процент усвоения.

Идея ученика 15.11.2026: вместо экзамена в конце блока — петля «работа над
ошибками». Урок идёт, пока правила не усвоены; в списке уроков напротив него
— прогресс-бар с процентом (красный → зелёный) и метка порога прохождения.

Здесь ТОЛЬКО счёт, без окна и без модели:
  * какие правила брать в сессию (самые частые пробелы, не больше лимита);
  * сколько процентов усвоено и пройден ли порог.

Почему считаем по УЧЕНИКУ, а не по блоку: поле lesson у записей ошибок пустое
(§55, перемер 15.11.2026 — 94 записи, ни у одной нет lesson), поэтому привязать
ошибку к блоку нечем. Значит «работа над ошибками» одна на ученика, а в каждом
блоке — контрольная точка на том же наборе правил.
"""

import gaps
import stats_store

# Порог прохождения (метка на прогрессе). 80 % — правило можно закрыть не
# до конца: одна незакрытая «серия» из трёх не мешает пройти точку.
PASS_PERCENT = 80

# Сколько правил тянет одна сессия. «Сколько необходимо» — но не больше трёх
# за заход: с шестью правилами до 80 % за одно занятие не дойти, а растягивать
# урок на 40 заданий — не обучение.
MAX_RULES = 3

# Сколько верных фраз подряд делает правило усвоенным (как в stats_store).
NEED_STREAK = getattr(stats_store, "DRILL_MASTER_STREAK", 3)


def session_rules(rows=None, limit=MAX_RULES):
    """Правила для работы над ошибками: пробелы, самые частые первыми."""
    buckets = [b for b in gaps.aggregate(rows) if b.get("is_gap")]
    buckets.sort(key=lambda b: (-int(b.get("count") or 0), str(b.get("rule"))))
    if limit and limit > 0:
        return buckets[:int(limit)]
    return buckets


def rule_percent(rule, state=None, need=None):
    """0…100 для одного правила.

    Усвоено (отметка mastered) → 100. Иначе — серия из NEED_STREAK верных
    подряд, переведённая в проценты: 1 верная из 3 → 33.

    Усвоенные пары библиотеки (a2.lay_lie) здесь НЕ учитываем: они и так
    выпадают из счёта в gaps.aggregate, и «одна пара усвоена» не значит
    «правило word_choice закрыто».
    """
    need = int(need or NEED_STREAK) or 3
    item = (state or {}).get(str(rule)) or {}
    if item.get("mastered_at"):
        return 100
    streak = int(item.get("streak") or 0)
    if streak <= 0:
        return 0
    return max(1, min(100, int(round(100.0 * min(streak, need) / need))))


def progress(rows=None, state=None, buckets=None, limit=MAX_RULES,
             pass_percent=None, need=None):
    """Сколько усвоено: {"percent", "pass", "rules", "has_rules", "pass_percent"}.

    rows — записи ошибок (None → читаем базу), state — drill_state
    ({правило: {"streak", "mastered_at"}}). Оба можно передать готовыми:
    тогда функция чистая и проверяется без базы.
    """
    if rows is None:
        rows = stats_store.rows()
    if state is None:
        state = stats_store.drill_state()
    items = session_rules(rows, limit=limit) if buckets is None else list(buckets)
    pass_percent = int(PASS_PERCENT if pass_percent is None else pass_percent)
    out_rules = []
    total = 0
    for bucket in items:
        rule = str(bucket.get("rule") or "")
        pct = rule_percent(rule, state, need)
        total += pct
        out_rules.append({
            "rule": rule,
            "label": bucket.get("label") or gaps.RULE_RU.get(rule, rule),
            "count": int(bucket.get("count") or 0),
            "percent": pct,
        })
    if not out_rules:
        # Отрабатывать нечего — точку считаем пройденной, а не «нулём».
        return {"percent": 100, "pass": True, "rules": [], "has_rules": False,
                "pass_percent": pass_percent}
    percent = int(round(float(total) / len(out_rules)))
    return {"percent": percent, "pass": percent >= pass_percent,
            "rules": out_rules, "has_rules": True,
            "pass_percent": pass_percent}


def color(percent, pass_percent=None):
    """Цвет бара от красного к зелёному: (r, g, b) 0…255.

    Красный — 0 %, жёлтый — половина порога, зелёный — порог и выше. Выше
    порога цвет не «темнеет»: дальше 100 % уже некуда.
    """
    pct = max(0.0, min(100.0, float(percent or 0)))
    edge = float(pass_percent or PASS_PERCENT) or 1.0
    share = min(1.0, pct / edge)
    if share < 0.5:                     # красный → жёлтый
        k = share / 0.5
        return (int(round(239 + (250 - 239) * k)),
                int(round(68 + (204 - 68) * k)),
                int(round(68 + (21 - 68) * k)))
    k = (share - 0.5) / 0.5             # жёлтый → зелёный
    return (int(round(250 + (34 - 250) * k)),
            int(round(204 + (197 - 204) * k)),
            int(round(21 + (94 - 21) * k)))


def to_hex(rgb):
    """(r, g, b) → "#rrggbb" для CustomTkinter."""
    r, g, b = [max(0, min(255, int(v))) for v in (rgb or (0, 0, 0))]
    return "#%02X%02X%02X" % (r, g, b)
