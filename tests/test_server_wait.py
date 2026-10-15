# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_SERVER_WAIT.PY — терпеливое ожидание LLM-сервера
# =========================================================
#   python tests\test_server_wait.py   (окно НЕ создаётся)
#
# Проверяем controllers/server_waiter.py:
#   1) сервер сразу отвечает → READY;
#   2) сначала ждём МОЛЧА (никаких сообщений);
#   3) потом показываем «ожидание» — ровно ОДИН раз;
#   4) если сервер молчит слишком долго → TIMEOUT («не отвечает»);
#   5) после итога ожидание не продолжается;
#   6) сервер очнулся во время ожидания → READY (действие можно выполнять);
#   7) reset() начинает заново; мусорные настройки не ломают логику.
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from controllers.server_waiter import (ServerWaiter, READY, ANNOUNCE,      # noqa: E402
                                       PENDING, TIMEOUT)

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("=" * 60)
    print("Проверка ожидания LLM-сервера (ServerWaiter)")
    print("=" * 60)

    # ---------- 1. Сервер сразу готов ----------
    print("\n[1] Сервер отвечает сразу")
    w = ServerWaiter(wait_seconds=10, poll_ms=500, announce_after=1.0)
    check("первый шаг при готовом сервере → READY", w.step(True) == READY)
    check("ожидание не тратило время", w.elapsed == 0.0, w.elapsed)
    check("сообщение «ожидание» не показывалось", w.announced is False)
    check("повторный шаг тоже READY", w.step(True) == READY)

    # ---------- 2. Молчим, пока сервер «задумался» ----------
    print("\n[2] Короткая заминка — никаких сообщений")
    w = ServerWaiter(wait_seconds=10, poll_ms=500, announce_after=2.0)
    check("1-й шаг молчит", w.step(False) == PENDING)
    check("2-й шаг (1.0 с) молчит", w.step(False) == PENDING)
    check("3-й шаг (1.5 с) молчит", w.step(False) == PENDING)
    check("прошло 1.5 с", abs(w.elapsed - 1.5) < 1e-6, w.elapsed)

    # ---------- 3. «Ожидание» показывается один раз ----------
    print("\n[3] Заминка затянулась — показываем «ожидание»")
    check("на 2.0 с → ANNOUNCE", w.step(False) == ANNOUNCE)
    check("флаг announced выставлен", w.announced is True)
    check("дальше — снова молчание (без повторов)",
          w.step(False) == PENDING and w.step(False) == PENDING)

    # ---------- 4. Слишком долго — «не отвечает» ----------
    print("\n[4] Сервер молчит слишком долго → TIMEOUT")
    w = ServerWaiter(wait_seconds=3.0, poll_ms=1000, announce_after=2.0)
    steps = [w.step(False) for _ in range(4)]
    check("последовательность: молчание → ожидание → таймаут",
          steps == [PENDING, ANNOUNCE, TIMEOUT, TIMEOUT], steps)
    check("после таймаута ожидание закончено", w.finished is True)
    check("is_timeout() True", w.is_timeout() is True)

    # ---------- 5. Сервер очнулся во время ожидания ----------
    print("\n[5] Сервер очнулся — можно действовать")
    w = ServerWaiter(wait_seconds=10, poll_ms=500, announce_after=1.0)
    check("сначала ждём", w.step(False) == PENDING)
    check("показали ожидание", w.step(False) == ANNOUNCE)
    check("сервер ответил → READY", w.step(True) == READY)
    check("после READY ожидание завершено", w.finished is True)
    check("is_timeout() False", w.is_timeout() is False)

    # ---------- 6. reset ----------
    print("\n[6] reset() начинает ожидание заново")
    w = ServerWaiter(wait_seconds=2.0, poll_ms=1000, announce_after=1.0)
    w.step(False); w.step(False); w.step(False)      # до таймаута
    check("до reset — таймаут", w.finished is True)
    w.reset()
    check("после reset время сброшено", w.elapsed == 0.0 and w.finished is False)
    check("после reset ожидание начинается заново (снова «ожидание»)",
          w.step(False) == ANNOUNCE, w.elapsed)
    check("и снова можно дождаться сервера", w.step(True) == READY)

    # ---------- 7. Мусорные настройки ----------
    print("\n[7] Безопасные значения")
    z = ServerWaiter(wait_seconds="abc", poll_ms="xyz", announce_after=None)
    check("плохой wait_seconds → дефолт", z.wait_seconds > 0, z.wait_seconds)
    check("плохой poll_ms → дефолт", z.poll_ms > 0, z.poll_ms)
    check("wait_seconds=0 → сработает сразу", 
          ServerWaiter(wait_seconds=0, poll_ms=1000, announce_after=0).step(False) == TIMEOUT)
    check("отрицательный wait не ломает",
          ServerWaiter(wait_seconds=-5, poll_ms=1000).step(False) == TIMEOUT)
    check("poll_ms не меньше 50", ServerWaiter(poll_ms=1).poll_ms >= 50,
          ServerWaiter(poll_ms=1).poll_ms)

    # ---------- 8. Реальные настройки приложения ----------
    print("\n[8] Значения из config")
    import config
    w = ServerWaiter(getattr(config, "SERVER_WAIT_SECONDS", 15.0),
                     getattr(config, "SERVER_WAIT_POLL_MS", 800))
    check("ожидание из config положительное", w.wait_seconds > 0, w.wait_seconds)
    check("опрос из config положительный", w.poll_ms > 0, w.poll_ms)
    check("сначала молчание (ученик не видит ошибку сразу)", w.step(False) == PENDING)
    # прогоняем до конца — таймаут обязан наступить
    status = None
    for _ in range(10000):
        status = w.step(False)
        if status == TIMEOUT:
            break
    check("в конце обязательно TIMEOUT", status == TIMEOUT, status)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
