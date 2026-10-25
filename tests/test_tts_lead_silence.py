# =========================================================
# TESTS/TEST_TTS_LEAD_SILENCE.PY — тишина перед первой репликой
# =========================================================
#   python tests\test_tts_lead_silence.py
#
# ЗАЧЕМ (жалоба 25.10.2026): «Hi, Damil» теряло слово «Hi». Замер:
# наш код отдаёт mp3 целиком с начала (в mp3 перед «Hi» 114 мс тишины),
# значит первые ~100-200 мс съедает звуковое устройство на старте.
# Лечение: 200 мс тишины в начале — устройство просыпается на ней.
# Здесь проверяем ЧИСЛА (сколько сэмплов и в каком порядке), без звука.
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

import config                                                    # noqa: E402
import tts                                                       # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class RecOut:
    """Выход-заглушка: запоминает, что в него писали."""

    def __init__(self, log=None):
        self.writes = []
        self.log = log if log is not None else []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, arr):
        self.writes.append(arr)
        self.log.append("write:%d" % (len(arr) if hasattr(arr, "__len__") else -1))
        return None


# =========================================================
# 1. _write_silence: сколько сэмплов и какие
# =========================================================
def test_write_silence():
    print("\n[1] _write_silence: 200 мс нулей нужной формы")
    out = RecOut()
    ok = tts._write_silence(out, 24000, 1, 200)
    check("вернула True", ok is True, ok)
    check("одна запись", len(out.writes) == 1, len(out.writes))
    arr = out.writes[0]
    check("сэмплов = 0.2 с × 24000 = 4800", len(arr) == 4800, len(arr))
    check("всё нули", bool((arr == 0).all()), "есть ненулевые")
    check("один канал — одномерный массив", getattr(arr, "ndim", None) == 1,
          getattr(arr, "shape", None))

    out2 = RecOut()
    tts._write_silence(out2, 24000, 2, 100)
    arr2 = out2.writes[0]
    check("два канала — форма (N, 2)", getattr(arr2, "shape", None) == (2400, 2),
          getattr(arr2, "shape", None))
    check("стерео тоже нули", bool((arr2 == 0).all()), "есть ненулевые")

    out3 = RecOut()
    check("0 мс → ничего не пишем", tts._write_silence(out3, 24000, 1, 0) is False
          and out3.writes == [], out3.writes)
    check("мусор в частоте — не падаем",
          tts._write_silence(RecOut(), "ой", 1, 200) is False, True)
    check("по умолчанию 200 мс", tts.LEAD_SILENCE_MS == 200,
          tts.LEAD_SILENCE_MS)


# =========================================================
# 2. Порядок: тишина ДО первого куска
# =========================================================
def test_order_in_segments():
    print("\n[2] _stream_play_segments: тишина раньше первого куска")
    log = []
    out = RecOut(log)

    class FakeSD:
        def OutputStream(self, **kw):
            return out

    class FakePref:
        def __init__(self, text, voice, rate=None):
            self.text = text

        def wait(self, timeout=None):
            return b"data"

    orig = (tts._sd, tts._STREAM_OK, tts._Prefetch, tts._decode_stream_into,
            tts._decode_into)
    try:
        tts._sd = FakeSD()
        tts._STREAM_OK = True
        tts._Prefetch = FakePref
        tts._decode_stream_into = (lambda o, text, voice, sr, ch, gen, rate=None:
                                   (log.append("stream:" + text), True)[1])
        tts._decode_into = (lambda o, data, sr, ch, gen:
                            (log.append("file"), True)[1])
        ok = tts._stream_play_segments([(0, "en", "Hi, Damil")],
                                       tts._bump_generation())
    finally:
        (tts._sd, tts._STREAM_OK, tts._Prefetch, tts._decode_stream_into,
         tts._decode_into) = orig
    check("проиграно", ok is True, ok)
    check("первая запись в звук — тишина",
          log and log[0].startswith("write:"), log)
    check("потом уже речь", log and log[-1] == "stream:Hi, Damil", log)
    check("тишина ровно одна", sum(1 for x in log if x.startswith("write:")) == 1,
          log)


def main():
    test_write_silence()
    test_order_in_segments()
    print("\n" + ("ИТОГ: все проверки пройдены" if not FAILED
                  else "ИТОГ: провалов %d — %s" % (len(FAILED), ", ".join(FAILED))))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
