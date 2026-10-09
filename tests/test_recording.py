# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_RECORDING.PY — запись «на удержание» (push-to-talk)
# =========================================================
#   python tests\test_recording.py
#
# Запись идёт, ПОКА держишь кнопку «Запись»; остановка — по отпусканию
# (или страховочным пределом времени). Тишина больше НЕ обрывает фразу:
# ученику нужно время подумать.
# =========================================================

import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import audio_vad                                     # noqa: E402
from controllers.recording_controller import RecordingController  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def wait_until(pred, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return pred()


class FakeVAD:
    """Заглушка микрофона: без sounddevice, колбэк отдаём вручную."""

    def __init__(self, audio=None):
        self.is_recording = False
        self.stop_callback = None
        self.started = 0
        self.stopped = 0
        self.audio = b"\x00" * 16000 if audio is None else audio

    def set_stop_callback(self, callback):
        self.stop_callback = callback

    def start_recording(self):
        self.is_recording = True
        self.started += 1

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        self.stopped += 1
        if self.stop_callback:
            self.stop_callback(self.audio)


class FakeSTT:
    def __init__(self, result=("hello", "en")):
        self.result = result
        self.calls = 0

    def recognize(self, audio_data):
        self.calls += 1
        return self.result


def test_vad_hold():
    print("\n[1] audio_vad: удержание и страховка по времени")

    v = audio_vad.AudioVAD(max_seconds=0.2, stop_on_silence=False)
    done = []
    v.set_stop_callback(lambda a: done.append(a))
    v.is_recording = True
    v._start_time = time.time()
    t = threading.Thread(target=v._monitor, daemon=True)
    t.start()
    t.join(2.0)
    check("предел по времени останавливает запись", (not v.is_recording) and bool(done),
          "recording=%s done=%s" % (v.is_recording, len(done)))

    v2 = audio_vad.AudioVAD(max_seconds=10, stop_on_silence=False)
    v2.set_stop_callback(lambda a: None)
    v2.is_recording = True
    v2._start_time = time.time()
    v2.silence_counter = 999            # «очень много тишины»
    threading.Thread(target=v2._monitor, daemon=True).start()
    time.sleep(0.5)
    check("тишина не режет запись в режиме удержания", v2.is_recording, v2.is_recording)
    v2.is_recording = False

    v3 = audio_vad.AudioVAD(silence_limit=0.3, stop_on_silence=True)
    done3 = []
    v3.set_stop_callback(lambda a: done3.append(a))
    v3.is_recording = True
    v3._start_time = time.time()
    v3.silence_counter = 1.0
    t3 = threading.Thread(target=v3._monitor, daemon=True)
    t3.start()
    t3.join(2.0)
    check("stop_on_silence=True режет по тишине", (not v3.is_recording) and bool(done3))


def test_controller_flow():
    print("\n[2] RecordingController: старт/стоп, статус, распознавание")
    vad = FakeVAD()
    stt = FakeSTT()
    events, recognized, statuses = [], [], []

    rc = RecordingController(
        vad=vad, stt=stt, dispatch=lambda fn: fn(),
        on_status=lambda text, color: statuses.append((text, color)),
        on_recording_changed=lambda rec: events.append(rec),
        on_recognized=lambda text, lang: recognized.append((text, lang)),
    )

    rc.start()
    check("старт: VAD запущен", vad.started == 1 and vad.is_recording)
    check("старт: событие «запись»", events[:1] == [True], events)
    check("старт: статус про удержание",
          any("отпусти" in t.lower() for t, _ in statuses), statuses)

    rc.stop()
    check("стоп: VAD остановлен", vad.stopped == 1 and not vad.is_recording)
    wait_until(lambda: bool(recognized), 2.0)
    check("стоп: событие «не пишу»", events[-1] is False, events)
    check("распознанный текст отдан наружу", recognized[-1] == ("hello", "en"), recognized)
    check("распознавание вызвано один раз", stt.calls == 1, stt.calls)

    rc.stop()   # повторный стоп — без эффекта
    check("повторный стоп ничего не ломает", vad.stopped == 1 and rc.is_recording is False)


def test_too_short():
    print("\n[3] Короткая запись не уходит в распознавание")
    vad = FakeVAD(audio=b"\x00" * 100)     # 100 байт — короче минимума
    stt = FakeSTT()
    statuses = []
    rc = RecordingController(
        vad=vad, stt=stt, dispatch=lambda fn: fn(),
        on_status=lambda text, color: statuses.append(text),
    )
    rc.start()
    vad.stop_callback(vad.audio)           # как будто VAD сам остановился
    check("распознавание не вызвано", stt.calls == 0, stt.calls)
    check("статус «Слишком коротко»", any("коротко" in t.lower() for t in statuses), statuses)


def test_toggle_compat():
    print("\n[4] toggle(): старт/стоп по вызову")
    vad = FakeVAD()
    rc = RecordingController(vad=vad, stt=FakeSTT(), dispatch=lambda fn: fn())
    rc.toggle()
    check("первый toggle — запись", vad.started == 1 and rc.is_recording)
    rc.toggle()
    check("второй toggle — стоп", vad.stopped == 1 and not rc.is_recording)


def main():
    print("=" * 60)
    print("Проверка записи «на удержание» (push-to-talk)")
    print("=" * 60)

    test_vad_hold()
    test_controller_flow()
    test_too_short()
    test_toggle_compat()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
