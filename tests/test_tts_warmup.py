# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_TTS_WARMUP.PY — прогрев соединения и пределы ожидания
# =========================================================
#   python tests\test_tts_warmup.py     (сеть и звук НЕ нужны)
#
# Зачем: ученик услышал «Hello, Damil!» → долгая пауза → остаток фразы.
# Причина (замер, каждый замер в НОВОМ процессе):
#   1-й запрос к edge-tts — 7.01 с (таймаут) или «No audio was received»;
#   2-й — 3.11 с; 3-й — 5.08 с; дальше — 1.0–1.3 с.
# Холодное соединение + три повтора по 7 с = до 26 с тишины.
#
# Что проверяем:
#   1) warmup() делает запросы ЗАРАНЕЕ и запоминает, что связь готова;
#   2) приложение зовёт warmup при старте (иначе прогрева нет);
#   3) _download не тянет повторы дольше бюджета;
#   4) быстрый сбой («No audio») всё равно повторяется;
#   5) ожидание предзагрузки перед куском ограничено SEGMENT_WAIT_MAX;
#   6) неудачная загрузка запускает повторный прогрев (связь протухла).
# =========================================================

import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config        # noqa: E402
import tts           # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def reset_warm_state():
    """Сбросить отметки прогрева, чтобы тест не зависел от других тестов."""
    with tts._warm_lock:
        tts._warm_done = False
        tts._warm_running = False


# =========================================================
# 1. warmup: запросы заранее, повторный вызов ничего не качает
# =========================================================
def test_warmup_once():
    print("\n[1] warmup(): греет связь и не повторяет работу")
    reset_warm_state()
    calls = []
    orig = tts._download_once
    tts._download_once = lambda text, voice, rate=None: (calls.append(voice), b"mp3")[1]
    try:
        ok = tts.warmup(attempts=1)
        check("прогрев удался", ok is True, ok)
        check("греет ОБА голоса (английский и русский)",
              sorted(calls) == sorted([tts.VOICE_EN, tts.VOICE_RU]), calls)
        check("отметка «связь готова» стоит", tts._warm_done is True, tts._warm_done)
        before = len(calls)
        tts.warmup(attempts=1)
        check("повторный вызов не качает заново", len(calls) == before, calls)
    finally:
        tts._download_once = orig
        reset_warm_state()


# =========================================================
# 2. Приложение зовёт прогрев при старте
# =========================================================
def test_app_calls_warmup():
    print("\n[2] ui/app.py прогревает озвучку при старте")
    src = open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8").read()
    check("в app.py есть вызов tts.warmup_async()", "tts.warmup_async()" in src)
    check("прогрев стоит рядом с загрузкой Whisper",
          "self.stt.preload()" in src
          and src.index("self.stt.preload()") < src.index("tts.warmup_async()"))


# =========================================================
# 3. Бюджет повторов загрузки
# =========================================================
def test_download_budget():
    print("\n[3] «Зависшая» загрузка не тянет повторы дольше бюджета")
    orig = tts._download_once
    orig_budget, orig_timeout = tts.DOWNLOAD_BUDGET, tts.DOWNLOAD_TIMEOUT
    calls = []

    def slow(text, voice, rate=None):
        calls.append(text)
        time.sleep(min(1.5, tts.DOWNLOAD_TIMEOUT))   # имитация «висит»
        return None

    tts._download_once = slow
    tts.DOWNLOAD_TIMEOUT = 1.0
    tts.DOWNLOAD_BUDGET = 2.0
    # Здесь проверяется ЛЕСТНИЦА ПОВТОРОВ ПО ОЧЕРЕДИ — фиксируем её режим.
    # Параллельные запросы (config.TTS_PARALLEL_JOBS) — отдельный раздел:
    # tests/test_tts_local_fallback.py (раздел 1).
    orig_parallel = config.TTS_PARALLEL_JOBS
    config.TTS_PARALLEL_JOBS = 1
    with tts._warm_lock:            # не даём фону прогрева мешать счёту
        tts._warm_running = True
    try:
        t0 = time.monotonic()
        data = tts._download("Hello there.", tts.VOICE_EN)
        spent = time.monotonic() - t0
        check("ничего не скачалось", data is None, data)
        check("попыток не больше двух за бюджет (было %d)" % spent,
              len(calls) <= 2, calls)
        check("по времени уложились в бюджет с запасом: %.2f с" % spent,
              spent < tts.DOWNLOAD_BUDGET + tts.DOWNLOAD_TIMEOUT, spent)
    finally:
        tts._download_once = orig
        tts.DOWNLOAD_BUDGET, tts.DOWNLOAD_TIMEOUT = orig_budget, orig_timeout
        config.TTS_PARALLEL_JOBS = orig_parallel
        time.sleep(0.05)
        reset_warm_state()


# =========================================================
# 4. Быстрый сбой повторяется
# =========================================================
def test_fast_failure_retried():
    print("\n[4] Быстрый сбой («No audio») повторяется")
    orig = tts._download_once
    calls = []
    tts._download_once = lambda text, voice, rate=None: (calls.append(1), None)[1]
    reset_warm_state()
    with tts._warm_lock:                # фон прогрева не должен попадать в счёт
        tts._warm_running = True
    try:
        data = tts._download("Hello there.", tts.VOICE_EN)
        check("ничего не скачалось", data is None, data)
        check("сделано RETRY_ATTEMPTS попыток (%d)" % tts.RETRY_ATTEMPTS,
              len(calls) == tts.RETRY_ATTEMPTS, len(calls))
    finally:
        tts._download_once = orig
        reset_warm_state()


# =========================================================
# 5. Ожидание куска ограничено
# =========================================================
class FakeOut:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, arr):
        pass


class FakeSD:
    def query_devices(self, kind=None):
        return {"default_samplerate": 24000, "max_output_channels": 2}

    def OutputStream(self, **kw):
        return FakeOut()


def test_wait_bounded():
    print("\n[5] Застрявшая предзагрузка не держит ученика в тишине")
    print("    (проверяем потолок ожидания: %.1f с)" % tts.SEGMENT_WAIT_MAX)
    orig = (tts._Prefetch, tts._decode_into, tts._decode_stream_into,
            tts._sd, tts._download, tts._STREAM_OK, config.TTS_PREFETCH_ALL)
    waits = []
    state = {"played": 0}

    class HangingPref:            # предзагрузка, которая «висит»
        def __init__(self, text, voice, rate=None):
            self.text = text

        def wait(self, timeout=None):
            t0 = time.monotonic()
            time.sleep(min(0.4, timeout if timeout else 0.4))
            waits.append(timeout)
            return None

    tts._Prefetch = HangingPref
    tts._sd = FakeSD()
    tts._STREAM_OK = True
    tts._decode_into = lambda out, blob, sr, ch, gen: True
    tts._decode_stream_into = lambda out, text, voice, sr, ch, gen, rate=None: (
        state.__setitem__("played", state["played"] + 1), True)[1]
    tts._download = lambda text, voice, rate=None: b"a" * 8
    config.TTS_PREFETCH_ALL = True
    try:
        segs = [(0, "en", "Hello, Damil!"),
                (1, "en", "I am ready to help you today."),
                (2, "en", "Can you say hello to me?")]
        t0 = time.monotonic()
        tts._stream_play_segments(segs, tts._bump_generation())
        spent = time.monotonic() - t0
        check("ожидание ограничено сверху (timeout передан)",
              waits and all(w == tts.SEGMENT_WAIT_MAX for w in waits), waits)
        check("все куски всё равно сыграны", state["played"] == len(segs),
              state["played"])
        check("ответ не «висит»: %.2f с на 3 куска" % spent,
              spent < len(segs) * (tts.SEGMENT_WAIT_MAX + 0.5), spent)
    finally:
        (tts._Prefetch, tts._decode_into, tts._decode_stream_into,
         tts._sd, tts._download, tts._STREAM_OK, config.TTS_PREFETCH_ALL) = orig


# =========================================================
# 6. После неудачи прогрев запускается заново
# =========================================================
def test_rewarm_after_failure():
    print("\n[6] Неудачная загрузка → повторный прогрев в фоне")
    reset_warm_state()
    orig = (tts._download_once, tts.RETRY_DELAY, tts.warmup_async)
    tts._download_once = lambda text, voice, rate=None: None
    tts.RETRY_DELAY = 0.01
    called = []
    tts.warmup_async = lambda: called.append(1)
    try:
        tts._download("Hello there.", tts.VOICE_EN)
        check("отметка «связь готова» сброшена", tts._warm_done is False,
              tts._warm_done)
        check("прогрев запущен повторно (в фоне)", len(called) == 1, called)
    finally:
        tts._download_once, tts.RETRY_DELAY, tts.warmup_async = orig
        reset_warm_state()


def main():
    print("=" * 60)
    print("Проверка прогрева озвучки и пределов ожидания")
    print("=" * 60)
    try:
        test_warmup_once()
        test_app_calls_warmup()
        test_download_budget()
        test_fast_failure_retried()
        test_wait_bounded()
        test_rewarm_after_failure()
    finally:
        reset_warm_state()

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
