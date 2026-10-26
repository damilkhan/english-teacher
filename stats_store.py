# -*- coding: utf-8 -*-
# =========================================================
# STATS_STORE.PY — ошибки ученика ТАБЛИЦЕЙ в SQLite (карта пробелов, §46)
# =========================================================
# Зачем: в JSON-профиле ошибки лежат списками, и каждый тип обрезается до
# MAX_ERRORS_PER_TYPE = 20 — старая история стирается. Карте пробелов нужна
# история БЕЗ лимита, поэтому рядом с JSON живёт маленькая база:
#     profiles/stats_<user_id>.db   (у legacy-профиля — stats_student.db)
#
# Решение ученика 26.10.2026: JSON остаётся ГЛАВНЫМ, SQLite — придатком.
# Пишем в оба места из ОДНОЙ точки — profile_store.record_analysis.
# Весь профиль в SQL НЕ переводим: на словаре profile построены десятки
# мест и тестов.
#
# Никакого Tk и никакой модели тут нет: чистый sqlite3 (встроен в Python).
# =========================================================

import os
import sqlite3
import threading
from datetime import datetime

import user_manager

# Запасной файл: активного пользователя нет (тесты, legacy-профиль).
LEGACY_DB_NAME = "stats_student.db"

# Замок: писать может и главный поток (описание фото), и поток Аналитика.
_LOCK = threading.Lock()

# Кто уже перенёс старые записи из JSON (путь к базе → True).
# Без этого COUNT(*) считался бы на каждой реплике.
_migrated = set()

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS mistakes ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " date TEXT NOT NULL DEFAULT '',"
    " wrong TEXT NOT NULL DEFAULT '',"
    " correct TEXT NOT NULL DEFAULT '',"
    " note TEXT NOT NULL DEFAULT '',"
    " type TEXT NOT NULL DEFAULT 'grammar',"
    " rule TEXT NOT NULL DEFAULT 'other',"
    " source TEXT NOT NULL DEFAULT 'chat',"
    " lesson TEXT NOT NULL DEFAULT '')",
    "CREATE INDEX IF NOT EXISTS idx_mistakes_rule ON mistakes(rule)",
    "CREATE INDEX IF NOT EXISTS idx_mistakes_date ON mistakes(date)",
)

COLUMNS = ("date", "wrong", "correct", "note", "type", "rule", "source", "lesson")


def db_path(user_id=None):
    """profiles/stats_<id>.db. Без активного ученика — запасной файл."""
    if user_id is None:
        try:
            user_id = user_manager.get_last_user_id()
        except Exception:
            user_id = None
    if user_id is None:
        return os.path.join(user_manager.PROFILES_DIR, LEGACY_DB_NAME)
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return os.path.join(user_manager.PROFILES_DIR, LEGACY_DB_NAME)
    return os.path.join(user_manager.PROFILES_DIR, "stats_%d.db" % user_id)


def _connect(user_id=None):
    """Соединение с готовой схемой (файл и папка создаются сами)."""
    path = db_path(user_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    for sql in _SCHEMA:
        conn.execute(sql)
    conn.commit()
    return conn


def _row(item, now):
    """Одна запись из словаря любого вида (Аналитик, фото, JSON-профиль)."""
    return (str(item.get("date") or now)[:40],
            str(item.get("wrong") or "")[:80],
            str(item.get("correct") or "")[:80],
            str(item.get("note") or "")[:80],
            str(item.get("type") or "grammar")[:16],
            str(item.get("rule") or "other")[:24],
            str(item.get("source") or "chat")[:16],
            str(item.get("lesson") or "")[:40])


def add_mistakes(items, user_id=None):
    """Дописать ошибки в базу. Возвращает число записанных строк."""
    rows = [it for it in (items or [])
            if isinstance(it, dict) and (it.get("wrong") or it.get("correct"))]
    if not rows:
        return 0
    now = datetime.now().isoformat()
    with _LOCK:
        try:
            conn = _connect(user_id)
        except Exception as exc:
            print("Статистика: база недоступна (%s)" % exc)
            return 0
        try:
            conn.executemany(
                "INSERT INTO mistakes (%s) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                % ", ".join(COLUMNS),
                [_row(it, now) for it in rows])
            conn.commit()
        except Exception as exc:
            print("Статистика: запись не удалась (%s)" % exc)
            return 0
        finally:
            conn.close()
    return len(rows)


def rows(user_id=None, newest_first=True):
    """Все ошибки из базы (свежие первыми). Ошибка чтения → пустой список."""
    order = "date DESC, id DESC" if newest_first else "date ASC, id ASC"
    with _LOCK:
        try:
            conn = _connect(user_id)
        except Exception as exc:
            print("Статистика: база недоступна (%s)" % exc)
            return []
        try:
            cur = conn.execute("SELECT %s FROM mistakes ORDER BY %s"
                               % (", ".join(COLUMNS), order))
            out = [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            print("Статистика: чтение не удалось (%s)" % exc)
            out = []
        finally:
            conn.close()
    return out


def count(user_id=None):
    """Сколько всего ошибок в базе."""
    with _LOCK:
        try:
            conn = _connect(user_id)
        except Exception:
            return 0
        try:
            return int(conn.execute("SELECT COUNT(*) FROM mistakes").fetchone()[0])
        except Exception:
            return 0
        finally:
            conn.close()


def clear(user_id=None):
    """Очистить базу (тесты и «начать статистику заново»)."""
    with _LOCK:
        try:
            conn = _connect(user_id)
        except Exception:
            return False
        try:
            conn.execute("DELETE FROM mistakes")
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()


def ensure_migrated(profile, user_id=None):
    """Первый запуск: перенести ошибки из JSON-профиля в таблицу (§46).

    Только если база ПУСТАЯ — иначе получились бы дубли при каждом занятии.
    Правила у старых записей нет, поэтому берём ДОГАДКУ gaps.guess_rule
    (импорт локальный: gaps сам импортирует stats_store).
    """
    path = db_path(user_id)
    if path in _migrated:
        return 0
    _migrated.add(path)
    if count(user_id):
        return 0
    mistakes = (profile or {}).get("mistakes") or {}
    items = []
    for etype, cards in mistakes.items():
        if not isinstance(cards, list):
            continue
        for card in cards:
            if not isinstance(card, dict):
                continue
            if not (card.get("wrong") or card.get("correct")):
                continue
            items.append({
                "date": card.get("date") or "",
                "wrong": card.get("wrong") or "",
                "correct": card.get("correct") or "",
                "note": card.get("note") or "",
                "type": etype,
                "source": "chat",
            })
    if not items:
        return 0
    try:
        import gaps
        for item in items:
            item["rule"] = gaps.guess_rule(item["wrong"], item["correct"])
    except Exception as exc:
        print("Статистика: правила старых записей не угаданы (%s)" % exc)
        for item in items:
            item["rule"] = "other"
    return add_mistakes(items, user_id)


def forget_migrated():
    """Забыть, кто уже переносился (нужно тестам и смене ученика)."""
    _migrated.clear()
