# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_TTS.PY — проверка tts.py (без сети и без звука)
# =========================================================
#   python tests\test_tts.py
#
# edge-tts и pygame подменяются заглушками, поэтому тест:
#   * не ходит в интернет и не издаёт звук;
#   * проверяет логику: языки, эмодзи, кэш, временные файлы, сериализацию,
#     «последняя реплика важнее», прерывание, безопасные дефолты.
# =========================================================

import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# консоль Windows по умолчанию cp1251 — без этого падаем на эмодзи
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import tts  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


# ---------- заглушки pygame ----------
class FakeMusic:
    def __init__(self):
        self.loaded = None
        self.existed_at_load = False
        self.played = 0
        self.stopped = 0
        self._ticks = 0

    def load(self, path):
        self.loaded = path
        self.existed_at_load = os.path.exists(path)
        self._ticks = 1                     # «играем» ровно один тик

    def play(self):
        self.played += 1

    def get_busy(self):
        if self._ticks > 0:
            self._ticks -= 1
            return True
        return False

    def stop(self):
        self.stopped += 1
        self._ticks = 0


class FakeMixer:
    def __init__(self):
        self.music = FakeMusic()

    def get_init(self):
        return True

    def init(self):
        pass

    def quit(self):
        pass


class FakePygame:
    def __init__(self):
        self.mixer = FakeMixer()


class restore_tts:
    """Сохранить/вернуть глобальные точки подмены в tts."""

    def __enter__(self):
        self.pygame = tts.pygame
        self.synth = tts._synthesize
        self.play = tts._play
        self.download = tts._download
        self.stream_play = tts._stream_play
        self.segments_play = tts._stream_play_segments
        tts._cache.clear()
        tts._stop.clear()
        tts._gen = 0
        # по умолчанию сегментный и потоковый пути «не срабатывают» → тесты
        # гоняют запасной путь (mp3 целиком → pygame), как раньше
        tts._stream_play_segments = lambda *a, **k: False
        tts._stream_play = lambda *a, **k: False
        return self

    def __exit__(self, *exc):
        tts.pygame = self.pygame
        tts._synthesize = self.synth
        tts._play = self.play
        tts._download = self.download
        tts._stream_play = self.stream_play
        tts._stream_play_segments = self.segments_play
        tts._cache.clear()
        tts._stop.clear()
        tts._gen = 0


# =========================================================
# 1. Чистые функции
# =========================================================
def test_pure():
    print("\n[1] Эмодзи и определение языка")
    out = tts.remove_emojis("Привет 😊 мир!")
    check("эмодзи удалены", "😊" not in out and "Привет" in out and "мир" in out, repr(out))
    check("строка из одного эмодзи → пусто", tts.remove_emojis("🙂") == "")
    check("detect_language: русский", tts.detect_language("привет") == "ru")
    check("detect_language: английский", tts.detect_language("hello there") == "en")
    check("voice_for: ru→русский, en→английский",
          tts.voice_for("ru") == tts.VOICE_RU and tts.voice_for("en") == tts.VOICE_EN,
          (tts.VOICE_RU, tts.VOICE_EN))
    check("тон: Светлана поднята (+10Hz), Ava без сдвига",
          tts.pitch_for(tts.VOICE_RU) == "+10Hz" and tts.pitch_for(tts.VOICE_EN) == "+0Hz",
          (tts.pitch_for(tts.VOICE_RU), tts.pitch_for(tts.VOICE_EN)))
    check("скорость: у Светланы +10%",
          tts.rate_for(tts.VOICE_RU) == "+10%", tts.rate_for(tts.VOICE_RU))


def test_voice_per_language():
    print("\n[1c] Голос по языку: русский текст — русским голосом")
    with restore_tts():
        used = []
        tts._download = lambda text, voice: (used.append(voice), b"x")[1]
        tts._play = lambda data, gen: None
        tts.speak("Hello, my friend")     # английский
        tts.speak("Привет, друг мой")     # русский
        check("EN → VOICE_EN, RU → VOICE_RU",
              used == [tts.VOICE_EN, tts.VOICE_RU], used)


def test_split_by_language():
    print("\n[1f] split_by_language: разбиение смешанного текста")
    s = tts.split_by_language
    check("чистый английский → один кусок", s("Hello there") == [("en", "Hello there")], s("Hello there"))
    check("чистый русский → один кусок", s("Привет друг") == [("ru", "Привет друг")], s("Привет друг"))
    mixed = s("Please choose three topics. Какой выбор ты сделаешь, Дамиль?")
    check("смешанный → сначала en, затем ru",
          len(mixed) == 2 and mixed[0][0] == "en" and mixed[1][0] == "ru", mixed)
    check("русский кусок сохранён", mixed[1][1] == "Какой выбор ты сделаешь, Дамиль?", mixed)
    check("пустой/None → []", s("") == [] and s(None) == [])
    check("только цифры → [] (нет букв)", s("123 456") == [], s("123 456"))
    inline = s("глагол train значит поезд")
    check("инлайновое EN-слово выделено отдельным куском",
          any(l == "en" and w == "train" for l, w in inline), inline)


# =========================================================
# 2. Кэш
# =========================================================
def test_speech_clean():
    print("\n[1b] clean_for_speech: разметка и символы не озвучиваются")
    cases = [
        ('**"She is preparing for competitions."**', '"She is preparing for competitions."'),
        ("\u0422\u044b \u043c\u043e\u0436\u0435\u0448\u044c \u0441\u043a\u0430\u0437\u0430\u0442\u044c: **She trains.** \U0001F4AA",
         "\u0422\u044b \u043c\u043e\u0436\u0435\u0448\u044c \u0441\u043a\u0430\u0437\u0430\u0442\u044c: She trains."),
        ("\u0413\u043e\u0442\u043e\u0432\u043e <end_turn>", "\u0413\u043e\u0442\u043e\u0432\u043e"),
        ("- \u043f\u0443\u043d\u043a\u0442 \u043e\u0434\u0438\u043d\n- \u043f\u0443\u043d\u043a\u0442 \u0434\u0432\u0430",
         "\u043f\u0443\u043d\u043a\u0442 \u043e\u0434\u0438\u043d \u043f\u0443\u043d\u043a\u0442 \u0434\u0432\u0430"),
        ("\u041e\u0442\u0432\u0435\u0442 \u0441 `\u043a\u043e\u0434\u043e\u043c` \u0438 _\u043a\u0443\u0440\u0441\u0438\u0432\u043e\u043c_",
         "\u041e\u0442\u0432\u0435\u0442 \u0441 \u043a\u043e\u0434\u043e\u043c \u0438 \u043a\u0443\u0440\u0441\u0438\u0432\u043e\u043c"),
        ("a \u2192 b", "a b"),
        ("\U0001F60A", ""),
        ("", ""),
        (None, ""),
    ]
    for raw, expected in cases:
        got = tts.clean_for_speech(raw)
        check("clean_for_speech(%r)" % (raw,), got == expected,
              "\u043f\u043e\u043b\u0443\u0447\u0435\u043d\u043e %r, \u0436\u0434\u0430\u043b\u0438 %r" % (got, expected))


def test_streaming_path():
    print("\n[1d] Потоковая озвучка: поток первым, откат при неудаче")
    with restore_tts():
        called = {"stream": 0, "synth": 0, "play": 0}
        tts._synthesize = lambda text, voice: (called.__setitem__("synth", called["synth"] + 1), b"x")[1]
        tts._play = lambda data, gen: called.__setitem__("play", called["play"] + 1)

        def stream_ok(text, voice, gen):
            called["stream"] += 1
            return True

        tts._stream_play = stream_ok
        tts.speak("Hello there")
        check("при успешном потоке откат не вызывается",
              called["stream"] == 1 and called["play"] == 0 and called["synth"] == 0, called)

        called = {"stream": 0, "synth": 0, "play": 0}
        tts._stream_play = lambda *a: (called.__setitem__("stream", called["stream"] + 1), False)[1]
        tts.speak("Hello there")
        check("если поток не вышло — играем запасным путём",
              called["stream"] == 1 and called["play"] == 1 and called["synth"] == 1, called)


def test_byte_stream():
    print("\n[1e] _ByteStream: блокирующее чтение чанков")
    import queue as _q
    q = _q.Queue()
    for piece in (b"abc", b"de", b"f"):
        q.put(piece)
    q.put(None)
    r = tts._ByteStream(q)
    first = r.read(2)
    parts = []
    while True:
        chunk = r.read(2)
        if not chunk:
            break
        parts.append(chunk)
    check("read(2) отдаёт ровно 2 байта", first == b"ab", first)
    check("поток отдаётся целиком по кускам",
          first + b"".join(parts) == b"abcdef", (first, parts))
    check("после EOF read -> b'' и поток не seekable",
          r.read(2) == b"" and r.seekable() is False and r.readable() is True)


def test_substitutions():
    print("\n[1g] Подстановка перед озвучкой (кириллица → латиница)")
    with restore_tts():
        used = []
        tts._stream_play = lambda text, voice, gen: (used.append((voice, text)), True)[1]
        tts.speak("Привет, Дамиль!", substitutions={"Дамиль": "Damil"})
        joined = " ".join(t for _v, t in used)
        check("подстановка применилась", "Damil" in joined and "Дамиль" not in joined, used)
        check("имя ушло английскому голосу", any(v == tts.VOICE_EN and "Damil" in t for v, t in used), used)


def test_segments_pipeline():
    print("\n[1h] Сегментный поток: один выход, куски качаются заранее")
    orig = (tts._Prefetch, tts._decode_into, tts._sd, tts._STREAM_OK)
    opens = {"n": 0}
    decoded = []

    class FakePref:
        def __init__(self, text, voice):
            self.text, self.voice = text, voice
        def wait(self, timeout=None):
            return ("b:" + self.text).encode("utf-8")

    class FakeOut:
        def __enter__(self):
            opens["n"] += 1
            return self
        def __exit__(self, *a):
            return False
        def write(self, arr):
            pass

    class FakeSD:
        def OutputStream(self, **kw):
            return FakeOut()

    try:
        tts._Prefetch = FakePref
        tts._sd = FakeSD()
        tts._decode_into = lambda out, data, sr, ch, gen: (decoded.append(data), True)[1]
        tts._STREAM_OK = True
        ok = tts._stream_play_segments([("en", "Hello"), ("ru", "Привет"), ("en", "OK")],
                                       tts._bump_generation())
        check("куски проиграны", ok is True, ok)
        check("звук открыт ОДИН раз (не на каждый кусок)", opens["n"] == 1, opens)
        check("все куски декодированы по порядку", len(decoded) == 3 and decoded[0] == b"b:Hello"
              and decoded[2] == b"b:OK", decoded)
    finally:
        tts._Prefetch, tts._decode_into, tts._sd, tts._STREAM_OK = orig


def test_cache():
    print("\n[2] Кэш синтеза")
    with restore_tts():
        calls = {"n": 0}
        tts._download = lambda text, voice: (calls.__setitem__("n", calls["n"] + 1), b"data-" + text.encode("utf-8"))[1]
        a = tts._synthesize("hello", tts.VOICE_EN)
        b = tts._synthesize("hello", tts.VOICE_EN)
        c = tts._synthesize("другой", tts.VOICE_RU)
        check("повторный текст скачивается один раз", calls["n"] == 2, calls["n"])
        check("кэш вернул те же байты", a == b and a is not None)
        check("другой текст — отдельное скачивание", c != a)
        tts.clear_cache()
        check("clear_cache очищает кэш", len(tts._cache) == 0)


# =========================================================
# 3. speak: временный файл, не response.mp3
# =========================================================
def test_tempfile_playback():
    print("\n[3] speak использует временный файл (не response.mp3)")
    with restore_tts():
        fp = FakePygame()
        tts.pygame = fp
        tts._download = lambda text, voice: b"MP3DATA"
        tts.speak("Hello there")
        m = fp.mixer.music
        check("mp3 проигран", m.played == 1, m.played)
        base = os.path.basename(m.loaded or "")
        check("использован временный файл jane_tts_*.mp3",
              "jane_tts_" in base and base.endswith(".mp3") and base != "response.mp3", m.loaded)
        check("файл существовал в момент загрузки", m.existed_at_load)
        check("временный файл удалён после проигрывания", not os.path.exists(m.loaded))
        check("response.mp3 в cwd не создаётся", not os.path.exists("response.mp3"))


# =========================================================
# 4. Пустой текст
# =========================================================
def test_empty():
    print("\n[4] Пустой текст ничего не делает")
    with restore_tts():
        calls = {"n": 0}

        def dl(text, voice):
            calls["n"] += 1
            return b"x"

        tts._download = dl
        tts.speak("")
        tts.speak("   ")
        tts.speak(None)
        check("пустой текст не запускает скачивание", calls["n"] == 0, calls["n"])


# =========================================================
# 5. stop()
# =========================================================
def test_stop():
    print("\n[5] stop()")
    with restore_tts():
        fp = FakePygame()
        tts.pygame = fp
        tts._stop.clear()
        tts.stop()
        check("stop() поднимает флаг прерывания", tts._stop.is_set())
        check("stop() дёргает микшер", fp.mixer.music.stopped == 1, fp.mixer.music.stopped)
        tts._stop.clear()

        tts.pygame = None            # микшер недоступен
        try:
            tts.stop()
            ok = True
        except Exception as exc:     # noqa: BLE001
            ok = False
        check("stop() не падает без микшера", ok)


# =========================================================
# 6. Сериализация (реплики не наступают друг на друга)
# =========================================================
def test_serialized():
    print("\n[6] Проигрывание сериализовано")
    with restore_tts():
        tts.pygame = FakePygame()
        tts._synthesize = lambda text, voice: b"x"
        state = {"active": 0, "max": 0, "count": 0}

        def fake_play(data, gen):
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
            state["count"] += 1
            time.sleep(0.12)
            state["active"] -= 1

        tts._play = fake_play
        t1 = threading.Thread(target=tts.speak, args=("one",))
        t1.start()
        time.sleep(0.05)             # первая уже играет
        t2 = threading.Thread(target=tts.speak, args=("two",))
        t2.start()
        t1.join(3)
        t2.join(3)
        check("два проигрывания не пересекаются (max=1)", state["max"] == 1, state)
        check("обе реплики доиграны (последовательно)", state["count"] == 2, state)


# =========================================================
# 7. Устаревший синтез не играем («последняя важнее»)
# =========================================================
def test_last_wins():
    print("\n[7] Устаревший синтез отбрасывается")
    with restore_tts():
        tts.pygame = FakePygame()
        played = []
        gate = threading.Event()
        calls = {"n": 0}

        def slow_synth(text, voice):
            calls["n"] += 1
            if calls["n"] == 1:
                gate.wait(2.0)       # первая реплика «висит» в синтезе
            return b"y"

        tts._synthesize = slow_synth
        tts._play = lambda data, gen: played.append(gen)

        ta = threading.Thread(target=tts.speak, args=("first",))
        ta.start()
        time.sleep(0.1)              # A внутри synth (поколение 1)
        tb = threading.Thread(target=tts.speak, args=("second",))
        tb.start()
        time.sleep(0.05)             # B подняла поколение 2 и ждёт лок
        gate.set()
        ta.join(3)
        tb.join(3)
        check("сыграла только новая реплика (gen=2)",
              played == [2], played)


# =========================================================
# 8. Безопасные дефолты при сбое скачивания
# =========================================================
def test_download_failure():
    print("\n[8] Сбой скачивания → тишина, без исключений")
    with restore_tts():
        fp = FakePygame()
        tts.pygame = fp

        def boom(text, voice):
            raise RuntimeError("нет сети")

        tts._download = boom
        try:
            tts.speak("Hello")
            ok = True
        except Exception:            # noqa: BLE001
            ok = False
        check("падение скачивания не роняет speak", ok)
        check("ничего не проиграно", fp.mixer.music.played == 0)


def main():
    print("=" * 60)
    print("Проверка tts.py (edge-tts/pygame — заглушки)")
    print("=" * 60)

    test_pure()
    test_voice_per_language()
    test_split_by_language()
    test_speech_clean()
    test_streaming_path()
    test_substitutions()
    test_segments_pipeline()
    test_byte_stream()
    test_cache()
    test_tempfile_playback()
    test_empty()
    test_stop()
    test_serialized()
    test_last_wins()
    test_download_failure()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
