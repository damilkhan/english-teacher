# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_TTS_PREFETCH.PY — предзагрузка кусков реплики
# =========================================================
#   python tests\test_tts_prefetch.py   (сеть и звук НЕ нужны)
#
# Зачем: ученик жаловался, что Джейн «задумывается» посреди смешанной фразы
# (переключение голоса = отдельный запрос к edge-tts). Решение: качать ВСЕ
# куски сразу, пока звучит первый, и НИ ОДНО слово не терять.
#
# Проверяем:
#   1) при TTS_PREFETCH_ALL=True все куски качаются ДО первого звука;
#   2) при False — прежний режим (два куска вперёд);
#   3) неудачная предзагрузка не съедает слово: есть вторая попытка;
#   4) смешанная фраза звучит ЦЕЛИКОМ и по порядку, русское — русским голосом;
#   5) одновременных запросов не больше 6 (ограничитель).
# =========================================================

import os
import sys

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


# ---------- заглушки вывода и предзагрузки ----------
class FakeOut:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, arr):
        pass


class FakeSD:
    def __init__(self, probe):
        self.probe = probe

    def OutputStream(self, **kw):
        self.probe()                  # сколько кусков готово К НАЧАЛУ звука
        return FakeOut()


class patch_tts:
    """Подменить сеть/звук и вернуть всё как было."""

    def __init__(self, prefetch_data="auto"):
        self.prefetch_data = prefetch_data

    def __enter__(self):
        self.orig = (tts._Prefetch, tts._decode_into, tts._decode_stream_into,
                     tts._sd, tts._STREAM_OK, tts._download, config.TTS_PREFETCH_ALL)
        self.state = {"prefetches": [], "played": [], "streams": [], "downloads": []}
        state = self.state
        data = self.prefetch_data

        class FakePref:
            def __init__(self, text, voice, rate=None):
                state["prefetches"].append((text, voice))
                self.text, self.voice = text, voice

            def wait(self, timeout=None):
                if data in ("none", "fail_stream"):   # предзагрузка «не удалась»
                    return None
                if callable(data):
                    return data(self.text)
                return ("P:" + self.text).encode("utf-8")

        tts._Prefetch = FakePref
        tts._sd = FakeSD(lambda: state.__setitem__(
            "ready_at_start", len(state["prefetches"])))
        tts._STREAM_OK = True
        tts._decode_into = lambda out, blob, sr, ch, gen: (
            state["played"].append(blob.decode("utf-8")), True)[1]
        tts._decode_stream_into = lambda out, text, voice, sr, ch, gen, rate=None: (
            state["streams"].append((text, voice)), data != "fail_stream")[1]
        tts._download = lambda text, voice, rate=None: (
            state["downloads"].append((text, voice)),
            ("DL:" + text).encode("utf-8"))[1]
        tts._stop.clear()
        return self

    def __exit__(self, *exc):
        (tts._Prefetch, tts._decode_into, tts._decode_stream_into,
         tts._sd, tts._STREAM_OK, tts._download, config.TTS_PREFETCH_ALL) = self.orig


MIXED = [(0, "en", "Great job, Damil!"), (1, "ru", "ключ"),
         (2, "en", "Now open the door and tell me what you see."),
         (3, "ru", "молодец"),
         (4, "en", "Can you name three more things in that room?")]


# =========================================================
# 1. Все куски качаются заранее
# =========================================================
def test_all_prefetched():
    print("\n[1] TTS_PREFETCH_ALL=True: все куски готовы к началу звука")
    config.TTS_PREFETCH_ALL = True
    with patch_tts() as ctx:
        ok = tts._stream_play_segments(MIXED, tts._bump_generation())
        st = ctx.state
        check("куски сыграны", ok is True, ok)
        check("предзагружены ВСЕ, кроме первого (он идёт потоком)",
              len(st["prefetches"]) == len(MIXED) - 1,
              st["prefetches"])
        check("к началу звука готовы все: %d" % (len(MIXED) - 1),
              st.get("ready_at_start") == len(MIXED) - 1, st.get("ready_at_start"))
        check("первый кусок — потоком (не из предзагрузки)",
              st["streams"] and st["streams"][0][0] == MIXED[0][2], st["streams"])


# =========================================================
# 2. Старый режим по выключателю
# =========================================================
def test_switch_off():
    print("\n[2] TTS_PREFETCH_ALL=False: прежний режим (два куска вперёд)")
    config.TTS_PREFETCH_ALL = False
    try:
        with patch_tts() as ctx:
            ok = tts._stream_play_segments(MIXED, tts._bump_generation())
            st = ctx.state
            check("куски сыграны", ok is True, ok)
            check("к началу звука готовы ровно 2 куска",
                  st.get("ready_at_start") == 2, st.get("ready_at_start"))
            check("остальные всё равно докачались", len(st["prefetches"]) == 4,
                  st["prefetches"])
    finally:
        config.TTS_PREFETCH_ALL = True


# =========================================================
# 3. Неудачная предзагрузка не съедает слово
# =========================================================
def test_failed_prefetch_keeps_word():
    print("\n[3] Предзагрузка не удалась → слово всё равно звучит")
    config.TTS_PREFETCH_ALL = True
    with patch_tts(prefetch_data="none") as ctx:
        ok = tts._stream_play_segments(MIXED, tts._bump_generation())
        st = ctx.state
        texts = [t for t, _ in st["streams"]]
        check("куски сыграны", ok is True, ok)
        check("русское слово не пропало: ушло в поток",
              "ключ" in texts and "молодец" in texts, texts)
        check("английские тоже", MIXED[2][2] in texts and MIXED[4][2] in texts, texts)
        check("порядок сохранён",
              texts == [seg[2] for seg in MIXED], texts)

    print("\n[3b] И поток, и предзагрузка не удались → последняя попытка загрузкой")
    with patch_tts(prefetch_data="fail_stream") as ctx:
        ok = tts._stream_play_segments(MIXED, tts._bump_generation())
        st = ctx.state
        dl = [t for t, _ in st["downloads"]]
        check("куски сыграны", ok is True, ok)
        check("по каждому куску есть повторная загрузка",
              [seg[2] for seg in MIXED] == dl, dl)
        check("все куски сыграны из загруженного (DL:…)",
              len(st["played"]) == len(MIXED)
              and all(p.startswith("DL:") for p in st["played"]),
              st["played"])


# =========================================================
# 4. Смешанная фраза целиком и в правильном голосе
# =========================================================
def test_mixed_whole():
    print("\n[4] Смешанная фраза звучит ЦЕЛИКОМ, русское — русским голосом")
    config.TTS_PREFETCH_ALL = True
    with patch_tts() as ctx:
        tts._stream_play_segments(MIXED, tts._bump_generation())
        st = ctx.state
        pref = dict((t, v) for t, v in st["prefetches"])
        check("русское слово синтезировано русским голосом",
              pref.get("ключ") == tts.VOICE_RU and pref.get("молодец") == tts.VOICE_RU,
              pref)
        check("английские — английским",
              pref.get(MIXED[2][2]) == tts.VOICE_EN and pref.get(MIXED[4][2]) == tts.VOICE_EN,
              pref)
        total = len(st["streams"]) + len(st["played"])
        check("сыграно ровно 5 кусков (ничего не потеряно)",
              total == len(MIXED) and len(st["played"]) == len(MIXED) - 1,
              (total, st["played"]))


# =========================================================
# 5. Ограничитель одновременных запросов
# =========================================================
def test_slots():
    print("\n[5] Одновременных запросов не больше 6")
    value = tts._PREFETCH_SLOTS._value
    check("ограничитель равен 6", value == 6, value)
    check("_Prefetch берёт слот внутри загрузки",
          "_PREFETCH_SLOTS" in open(os.path.join(ROOT, "tts.py"),
                                    encoding="utf-8").read())


def main():
    print("=" * 60)
    print("Проверка предзагрузки кусков озвучки")
    print("=" * 60)
    try:
        test_all_prefetched()
        test_switch_off()
        test_failed_prefetch_keeps_word()
        test_mixed_whole()
        test_slots()
    finally:
        config.TTS_PREFETCH_ALL = True

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
