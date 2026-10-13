# -*- coding: utf-8 -*-
# =========================================================
# TTS.PY — озвучка ответов Джейн (edge-tts → mp3 → pygame)
# =========================================================
# Схема: текст → чистка → РАЗБИЕНИЕ ПО ЯЗЫКУ → синтез куска своим голосом →
# проигрывание. (edge-tts — ОНЛАЙН; звук — sounddevice-поток или pygame.)
#
# Что улучшено против первой версии:
#   * СЕРИАЛИЗАЦИЯ: синтез и проигрывание идут строго по очереди (Lock) —
#     две реплики больше не «наступают» друг на друга на общем микшере;
#   * «последняя реплика важнее»: новая озвучка прерывает текущую (счётчик
#     поколений), а stop() умеет гасить речь вручную;
#   * синтез идёт во ВРЕМЕННЫЙ файл (tempfile), а не в общий response.mp3;
#     временный файл всегда убирается (finally);
#   * КЭШ mp3 в памяти: повторный текст не скачивается второй раз;
#   * таймаут покрывает ТОЛЬКО скачивание; проигрывание прерываемо и не
#     может «подвесить» поток;
#   * pygame.mixer.init() при импорте обёрнут в try/except: отсутствие
#     звуковой карты больше не роняет ИМПОРТ модуля.
#
# Приложение зовёт speak(text) из фонового потока (окно не морозим).
# stop() — по желанию: прервать текущую речь. remove_emojis /
# detect_language оставлены для совместимости.
# =========================================================

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import sys
import tempfile
import threading
import time
import queue
from collections import OrderedDict
from typing import Dict, Optional, Tuple

import edge_tts
import pygame

import config

# Потоковая озвучка: mp3 от edge-tts декодируем на лету (PyAV) и пишем в
# динамик (sounddevice) ещё ДО того, как файл скачается целиком. Если av/
# sounddevice недоступны — стриминг выключен, работает запасной путь
# (mp3 целиком → pygame).
try:
    import av
    import numpy as _np
    import sounddevice as _sd
    _STREAM_OK = True
except Exception as _exc:            # noqa: BLE001 — без них просто нет стриминга
    av = None
    _np = None
    _sd = None
    _STREAM_OK = False

_log = logging.getLogger(__name__)

# edge_tts сам закрывает свой event loop, и потом сборщик мусора пишет в лог
# "RuntimeError: Event loop is closed". Это безобидный шум — глушим только его,
# остальные необработанные исключения по-прежнему попадают в logs\app.log.
_default_unraisablehook = sys.unraisablehook


def _quiet_unraisable(unraisable):
    if "Event loop is closed" in str(getattr(unraisable, "exc_value", "")):
        return
    _default_unraisablehook(unraisable)


sys.unraisablehook = _quiet_unraisable

# Микшер pygame НЕ инициализируем на импорте: пока звучит потоковая озвучка
# (sounddevice), держать аудиоустройство открытым в pygame не нужно — это
# давало конфликт и «пропажу» звука. pygame.mixer.init() делается ЛЕНИВО
# в запасном пути (_play), если поток недоступен. Модуль импортируется всегда.

# Голоса ПО ЯЗЫКАМ. Мультиязычный Ava (en-US) отлично читает английский,
# но на РУССКОМ даёт акцент (проверено: Whisper слышит искажения, напр.
# «Дамиль» → «Доми»). Поэтому русские куски читает русский голос — так
# каждая часть звучит НАТИВНО. Хочешь один голос — VOICE_RU = VOICE_EN
# (тогда русский будет с акцентом).
VOICE_EN = "en-US-AvaMultilingualNeural"
VOICE_RU = "ru-RU-SvetlanaNeural"
VOICE = VOICE_EN                    # голос по умолчанию (совместимость)

# Тон по голосам. Светлана ниже Авы (замер: ~165 Гц против ~225 Гц), из-за
# чего на смене языка «меняется человек». Поднимаем Светлану (+10 Гц) —
# подобранный вручную сдвиг, чтобы русская речь звучала естественно.
VOICE_PITCH = {
    "en-US-AvaMultilingualNeural": "+0Hz",
    "ru-RU-SvetlanaNeural": "+10Hz",
}


def pitch_for(voice):
    """Сдвиг тона (SSML pitch) для голоса. По умолчанию +0Hz."""
    return VOICE_PITCH.get(voice, "+0Hz")


# Скорость речи по голосам. Темп РАЗНЫЙ для языков (см. config): английский
# чуть медленнее — ученику легче различать слова; русский — быстрее (родной).
VOICE_RATE = {
    "en-US-AvaMultilingualNeural": getattr(config, "TTS_RATE_EN", "+0%"),
    "ru-RU-SvetlanaNeural": getattr(config, "TTS_RATE_RU", "+10%"),
}


def rate_for(voice):
    """Скорость речи (SSML rate) для голоса. По умолчанию RATE."""
    return VOICE_RATE.get(voice, RATE)

RATE = "+10%"                 # скорость речи по умолчанию (если нет в VOICE_RATE)
DOWNLOAD_TIMEOUT = 7.0        # ТОЛЬКО скачивание (проигрывание — отдельно)
PLAYBACK_TICK = 0.05          # шаг опроса get_busy (для прерывания речи)
CACHE_LIMIT = 16              # сколько mp3 держим в памяти

# --- потоковая озвучка ---
STREAM_FORMAT = "mp3"         # edge-tts отдаёт audio-24khz-...-mp3
STREAM_SRC_RATE = 24000       # частота mp3 от edge-tts
STREAM_BLOCKSIZE = 2400       # размер блока вывода (0.1 с при 24 кГц)

# edge-tts (онлайн) иногда отвечает 403 — делаем несколько попыток,
# иначе реплика прозвучит «в тишину».
RETRY_ATTEMPTS = 3
RETRY_DELAY = 0.6             # пауза между попытками, сек

EMOJI_PATTERN = re.compile("["
    u"\U0001F600-\U0001F64F"
    u"\U0001F300-\U0001F5FF"
    u"\U0001F680-\U0001F6FF"
    u"\U0001F700-\U0001F77F"
    u"\U0001F780-\U0001F7FF"
    u"\U0001F800-\U0001F8FF"
    u"\U0001F900-\U0001F9FF"
    u"\U0001FA00-\U0001FA6F"
    u"\U0001FA70-\U0001FAFF"
    u"\U00002702-\U000027B0"
    u"\U000024C2-\U0001F251"
    "]+", flags=re.UNICODE)


def remove_emojis(text):
    return EMOJI_PATTERN.sub('', text).strip()

# ---------------------------------------------------------
# Подготовка текста к озвучке
# ---------------------------------------------------------
_TAG_RE = re.compile(r"<\|.*?\|>|</?\s*[A-Za-z_][A-Za-z0-9_]*\s*/?>", re.DOTALL)
_LINE_MARKER_RE = re.compile(r"(?m)^\s{0,3}(?:#{1,6}\s*|[-*•·]\s+|\d+[.)]\s+)")
_SPEECH_ARTIFACTS_RE = re.compile(r"[*_`~#|]+")
_ARROW_RE = re.compile(r"→|←|⇒|⇐|->|<-")


def clean_for_speech(text):
    """Готовит ответ к озвучке: без эмодзи, markdown и служебных символов.

    Модель отвечает с разметкой («**жирный**»), списками и иногда тегами
    (<end_turn>); читать это вслух нельзя — слышно «звёздочка, звёздочка».
    Эмодзи убираем отдельно (remove_emojis), затем снимаем разметку и
    одиночные символы, которые не должны звучать.
    """
    if not text:
        return ""
    text = remove_emojis(str(text))
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"`+", "", text)                      # обратные кавычки
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)        # *курсив*
    text = _LINE_MARKER_RE.sub("", text)                 # «- », «1. », «# »
    text = _SPEECH_ARTIFACTS_RE.sub(" ", text)          # остатки ** _ ` ~ # |
    text = _ARROW_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_language(text):
    """'ru', если кириллических букв больше, чем латинских, иначе 'en'."""
    russian_chars = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
    ru_count = sum(1 for c in text.lower() if c in russian_chars)
    en_count = sum(1 for c in text.lower() if c.isalpha() and c not in russian_chars)
    return "ru" if ru_count > en_count else "en"


def voice_for(lang):
    """Голос для языка куска: 'ru' → русский, иначе английский."""
    return VOICE_RU if lang == "ru" else VOICE_EN


def _apply_name(chunk, lang, name, name_latin):
    """Подставить имя НА ЯЗЫКЕ куска: ru → кириллица, en → латиница.

    Так в русском куске имя читает Светлана (по-русски), в английском — Ava.
    Смешанную фразу разбиваем заранее, поэтому каждый кусок получает свою
    форму имени (а не «как вся фраза»).
    """
    name = str(name or "").strip()
    name_latin = str(name_latin or "").strip()
    if not name or not name_latin or name == name_latin:
        return chunk
    if lang == "ru":
        return chunk.replace(name_latin, name)     # Damil → Дамиль
    return chunk.replace(name, name_latin)         # Дамиль → Damil


# Разбиение по языку (кириллица vs латиница). Нужно для СМЕШАННОГО текста:
# иначе голос берёт один акцент на всю фразу и русские слова звучат
# по-английски (и наоборот). Каждый кусок синтезируем своим голосом.
_TOKEN_RE = re.compile(r"[A-Za-z]+|[А-Яа-яЁё]+|[^A-Za-zА-Яа-яЁё]+")
_CYR_RE = re.compile(r"[А-Яа-яЁё]+")


def split_by_language(text):
    """Разбить текст на куски одного языка: [('ru'|'en', кусок), ...].

    Пунктуация/пробелы приклеиваются к предыдущему куску. Если язык
    один — вернётся один кусок (поведение не меняется).
    """
    segs = []      # [[lang, chunk], ...]
    for tok in _TOKEN_RE.findall(text or ""):
        if re.fullmatch(r"[A-Za-z]+", tok):
            lang = "en"
        elif _CYR_RE.fullmatch(tok):
            lang = "ru"
        else:
            lang = None                     # цифры/пунктуация/пробелы
        if lang is None:
            if segs:
                segs[-1][1] += tok
            continue
        if segs and segs[-1][0] == lang:
            segs[-1][1] += tok
        else:
            segs.append([lang, tok])
    return [(lang, chunk.strip()) for lang, chunk in segs if chunk.strip()]


# ---------------------------------------------------------
# Состояние (модуль-уровень: сериализация, прерывание, кэш)
# ---------------------------------------------------------
_lock = threading.Lock()            # один синтез + одно проигрывание за раз
_stop = threading.Event()           # запрос прервать текущее проигрывание
_gen = 0                            # номер последней ЗАПРОШЕННОЙ озвучки
_gen_lock = threading.Lock()        # защита счётчика поколений
_cache: "OrderedDict[Tuple[str, str, str], bytes]" = OrderedDict()


def _bump_generation() -> int:
    """Новый номер поколения: каждая новая реплика отменяет предыдущую."""
    global _gen
    with _gen_lock:
        _gen += 1
        return _gen


def _current_generation() -> int:
    return _gen


def stop() -> None:
    """Прервать текущее озвучивание.

    Безопасно вызывать из любого потока и в любой момент (в т.ч. когда
    ничего не играет и когда звуковая карта недоступна).
    """
    _stop.set()
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:                          # noqa: BLE001 — прерывание не должно падать
        pass


def clear_cache() -> None:
    """Очистить кэш озвучки (например, при смене голосов/настроек)."""
    _cache.clear()


# ---------------------------------------------------------
# Публичный вход
# ---------------------------------------------------------
def speak(text: str, name=None, name_latin=None) -> None:
    """Озвучить текст. Блокирующая: вызывать из фонового потока.

    name / name_latin: имя ученика в двух формах. Для КАЖДОГО куска имя
    подставляется НА ЯЗЫКЕ куска (ru → кириллица, en → латиница): в русском
    тексте имя звучит по-русски, в английском — по-английски.

    Смешанный текст разбивается ПО ЯЗЫКУ: русские куски читает русский
    голос, английские — английский. Новая реплика важнее текущей.
    """
    if not text or not str(text).strip():
        return
    clean_text = clean_for_speech(str(text))
    if not clean_text:
        return

    segments = split_by_language(clean_text)
    if not segments:                       # только цифры/знаки
        segments = [(detect_language(clean_text), clean_text)]
    # имя — на языке КАЖДОГО куска (русский кусок → кириллица, англ. → латиница)
    segments = [(lang, _apply_name(chunk, lang, name, name_latin))
                for lang, chunk in segments]

    my_gen = _bump_generation()
    stop()                                     # новая реплика прерывает старую
    with _lock:
        _stop.clear()
        # Основной путь: СЕГМЕНТНЫЙ поток — один звуковой выход на всю реплику
        # и предзагрузка кусков. Между языками нет пауз (раньше каждый кусок
        # открывал свой поток и качался по очереди — отсюда «задумчивость»).
        if _streaming_enabled():
            try:
                if _stream_play_segments(segments, my_gen):
                    return
            except Exception as exc:           # noqa: BLE001 — вернёмся к запасному
                _log.warning("TTS: сегментный путь не сработал (%s)", exc)
        # Запасной путь: по кускам (поток/скачивание, с повторами).
        for lang, chunk in segments:
            if _stop.is_set() or my_gen != _current_generation():
                return                         # прервали / пришла более новая
            _speak_chunk(chunk, voice_for(lang), my_gen)


def _speak_chunk(text: str, voice: str, my_gen: int) -> None:
    """Озвучить ОДИН кусок: сначала потоком, при неудаче — запасным путём."""
    print(f"🔊 Озвучка: {voice} — {text[:48]!r}")
    # Основной путь: ПОТОК (звучим по первым байтам; повторы — внутри).
    if _streaming_enabled():
        try:
            if _stream_play(text, voice, my_gen):
                return
        except Exception as exc:               # noqa: BLE001 — вернёмся к запасному
            _log.warning("TTS: потоковый путь не сработал (%s)", exc)
    if _stop.is_set() or my_gen != _current_generation():
        return
    # Запасной путь: скачать mp3 целиком и проиграть (pygame; повторы внутри).
    try:
        data = _synthesize(text, voice)
    except Exception as exc:                   # noqa: BLE001 — синтез не должен ронять поток
        print(f"⚠️ TTS ошибка синтеза: {exc}")
        data = None
    if not data or my_gen != _current_generation():
        return                                 # синтез устарел/не удался — не играем
    _play(data, my_gen)


# ---------------------------------------------------------
# Синтез и кэш
# ---------------------------------------------------------
def _synthesize(text: str, voice: str) -> Optional[bytes]:
    """mp3-байты для (text, voice): из кэша или скачиванием. None при ошибке."""
    key = (voice, rate_for(voice), text)
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached

    data = _download(text, voice)
    if data:
        _cache[key] = data
        _cache.move_to_end(key)
        while len(_cache) > CACHE_LIMIT:
            _cache.popitem(last=False)
    return data


def _download(text: str, voice: str) -> Optional[bytes]:
    """Скачивает mp3 С ПОВТОРАМИ (403/сеть) во временный файл. Файл убираем."""
    for _attempt in range(RETRY_ATTEMPTS):
        data = _download_once(text, voice)
        if data:
            return data
        time.sleep(RETRY_DELAY)
    return None


def _download_once(text: str, voice: str) -> Optional[bytes]:
    """Одно скачивание mp3 во временный файл. Файл всегда убираем."""
    handle, path = tempfile.mkstemp(prefix="jane_tts_", suffix=".mp3")
    os.close(handle)

    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate=rate_for(voice),
                                           pitch=pitch_for(voice))
        await communicate.save(path)

    try:
        asyncio.run(asyncio.wait_for(_run(), timeout=DOWNLOAD_TIMEOUT))
    except asyncio.TimeoutError:
        print("⚠️ TTS: таймаут скачивания")
        _safe_remove(path)
        return None
    except Exception as exc:                   # noqa: BLE001 — сеть/сервис любые
        print(f"⚠️ TTS ошибка: {exc}")
        _safe_remove(path)
        return None

    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        print(f"⚠️ TTS: файл не прочитан ({exc})")
        return None
    finally:
        _safe_remove(path)


# ---------------------------------------------------------
# Проигрывание
# ---------------------------------------------------------
def _play(data: bytes, my_gen: int) -> None:
    """Проигрывает mp3 из временного файла. Прерываемо (stop/новая реплика)."""
    handle, path = tempfile.mkstemp(prefix="jane_tts_", suffix=".mp3")
    os.close(handle)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            # прерывание вручную или запрос более новой реплики
            if _stop.is_set() or my_gen != _current_generation():
                pygame.mixer.music.stop()
                break
            time.sleep(PLAYBACK_TICK)
    except Exception as exc:                   # noqa: BLE001 — воспроизведение некритично
        print(f"⚠️ TTS воспроизведение ошибка: {exc}")
    finally:
        _safe_remove(path)


# ---------------------------------------------------------
# Потоковая озвучка (mp3 → PCM на лету → динамик)
# ---------------------------------------------------------
class _ByteStream:
    """Файл-объект для PyAV: блокирующее чтение mp3-чанков из очереди."""

    def __init__(self, chunks) -> None:
        self._q = chunks
        self._buf = b""
        self._eof = False

    def read(self, size=-1):
        if self._eof:
            return b""
        while not self._buf:
            item = self._q.get()
            if item is None:
                self._eof = True
                return b""
            self._buf += item
        if size is None or size < 0:
            out, self._buf = self._buf, b""
            return out
        out, self._buf = self._buf[:size], self._buf[size:]
        return out

    def readable(self):
        return True

    def seekable(self):
        return False


def _streaming_enabled() -> bool:
    """Поток включён в настройках И есть av/sounddevice."""
    return bool(_STREAM_OK and getattr(config, "TTS_STREAMING", True))


def _output_params():
    """(частота, число каналов) устройства вывода по умолчанию."""
    sr, ch = STREAM_SRC_RATE, 2
    try:
        info = _sd.query_devices(kind="output")
        sr = int(info.get("default_samplerate") or STREAM_SRC_RATE)
        ch = 2 if int(info.get("max_output_channels") or 2) >= 2 else 1
    except Exception:
        pass
    return sr, ch


def _edge_stream(text: str, voice: str, chunks) -> None:
    """Качает mp3-чанки edge-tts в очередь и кладёт None в конце."""
    async def _go():
        async for chunk in edge_tts.Communicate(text, voice, rate=rate_for(voice),
                                                     pitch=pitch_for(voice)).stream():
            if chunk.get("type") == "audio":
                chunks.put(chunk["data"])
    try:
        asyncio.run(_go())
    except Exception as exc:                   # noqa: BLE001 — сбой сети/сервиса
        _log.warning("TTS поток: %s", exc)
    finally:
        chunks.put(None)


def _stream_play(text: str, voice: str, my_gen: int) -> bool:
    """Потоковая озвучка С ПОВТОРАМИ (edge-tts иногда отвечает 403).

    True — что-то прозвучало; False — не вышло (переходим к запасному пути).
    """
    if not _STREAM_OK:
        return False
    for _attempt in range(RETRY_ATTEMPTS):
        if _stop.is_set() or my_gen != _current_generation():
            return False
        if _stream_once(text, voice, my_gen):
            return True
        time.sleep(RETRY_DELAY)
    return False


def _stream_once(text: str, voice: str, my_gen: int) -> bool:
    """Одна попытка потоковой озвучки. True — что-то проиграли."""
    if not _STREAM_OK:
        return False
    chunks = queue.Queue()
    reader = _ByteStream(chunks)
    threading.Thread(target=_edge_stream, args=(text, voice, chunks),
                     daemon=True).start()
    try:
        container = av.open(reader, format=STREAM_FORMAT)
    except Exception as exc:                   # noqa: BLE001 — пустой/битый поток
        _log.warning("TTS поток: не открылся (%s)", exc)
        return False

    samplerate, channels = _output_params()
    resampler = av.audio.resampler.AudioResampler(
        format="s16", layout="mono", rate=samplerate)
    played = False

    def _write(out, frame):
        nonlocal played
        if frame is not None:          # None — сброс ресемплера (не кадр)
            frame.pts = None
        for rframe in resampler.resample(frame):
            arr = rframe.to_ndarray().reshape(-1).astype("int16")
            if channels == 2:
                arr = _np.column_stack([arr, arr])
            out.write(_np.ascontiguousarray(arr))
            played = True
            if _stop.is_set() or my_gen != _current_generation():
                return False
        return True

    try:
        with _sd.OutputStream(samplerate=samplerate, channels=channels,
                              dtype="int16", blocksize=STREAM_BLOCKSIZE) as out:
            for frame in container.decode(audio=0):
                if _stop.is_set() or my_gen != _current_generation():
                    break
                if not _write(out, frame):
                    break
            else:
                # поток закончился — сбрасываем остаток из ресемплера
                _write(out, None)
    except Exception as exc:                   # noqa: BLE001 — звук некритичен
        _log.warning("TTS поток: воспроизведение (%s)", exc)
        return played
    finally:
        try:
            container.close()
        except Exception:
            pass
    return played


# ---------------------------------------------------------
# Сегментная озвучка: один выход + предзагрузка кусков
# ---------------------------------------------------------
class _Prefetch:
    """Фоновая загрузка mp3 одного куска (играем текущий — качаем следующий)."""

    def __init__(self, text: str, voice: str) -> None:
        self.text = text
        self.voice = voice
        self._data = None
        self._event = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            self._data = _download(self.text, self.voice)
        except Exception:                      # noqa: BLE001 — сбой загрузки не критичен
            self._data = None
        finally:
            self._event.set()

    def wait(self, timeout=None):
        self._event.wait(timeout)
        return self._data


def _decode_into(out, data, samplerate, channels, my_gen) -> bool:
    """Декодирует mp3-байты (в памяти) и пишет PCM в ОБЩИЙ поток вывода."""
    try:
        container = av.open(io.BytesIO(data), format=STREAM_FORMAT)
    except Exception as exc:                   # noqa: BLE001 — битый кусок
        _log.warning("TTS: кусок не декодировался (%s)", exc)
        return False
    resampler = av.audio.resampler.AudioResampler(
        format="s16", layout="mono", rate=samplerate)
    played = False

    def _write(frame):
        nonlocal played
        if frame is not None:
            frame.pts = None
        for rframe in resampler.resample(frame):
            arr = rframe.to_ndarray().reshape(-1).astype("int16")
            if channels == 2:
                arr = _np.column_stack([arr, arr])
            out.write(_np.ascontiguousarray(arr))
            played = True

    try:
        for frame in container.decode(audio=0):
            if _stop.is_set() or my_gen != _current_generation():
                break
            _write(frame)
        else:
            _write(None)                        # сброс остатка ресемплера
    except Exception as exc:                   # noqa: BLE001 — звук некритичен
        _log.warning("TTS: воспроизведение куска (%s)", exc)
    finally:
        try:
            container.close()
        except Exception:
            pass
    return played


def _decode_stream_into(out, text, voice, samplerate, channels, my_gen) -> bool:
    """Декодирует mp3-ПОТОК edge-tts прямо в общий выход (старт по первым байтам)."""
    chunks = queue.Queue()
    threading.Thread(target=_edge_stream, args=(text, voice, chunks),
                     daemon=True).start()
    try:
        container = av.open(_ByteStream(chunks), format=STREAM_FORMAT)
    except Exception as exc:                   # noqa: BLE001 — битый/пустой поток
        _log.warning("TTS: поток куска не открылся (%s)", exc)
        return False
    resampler = av.audio.resampler.AudioResampler(
        format="s16", layout="mono", rate=samplerate)
    played = False

    def _write(frame):
        nonlocal played
        if frame is not None:
            frame.pts = None
        for rframe in resampler.resample(frame):
            arr = rframe.to_ndarray().reshape(-1).astype("int16")
            if channels == 2:
                arr = _np.column_stack([arr, arr])
            out.write(_np.ascontiguousarray(arr))
            played = True

    try:
        for frame in container.decode(audio=0):
            if _stop.is_set() or my_gen != _current_generation():
                break
            _write(frame)
        else:
            _write(None)
    except Exception as exc:                   # noqa: BLE001 — звук некритичен
        _log.warning("TTS: поток куска, воспроизведение (%s)", exc)
    finally:
        try:
            container.close()
        except Exception:
            pass
    return played


def _stream_play_segments(segments, my_gen) -> bool:
    """Проиграть все куски ЧЕРЕЗ ОДИН звуковой выход.

    Первый кусок читаем ПОТОКОМ (звук — как только пришли первые байты, не
    дожидаясь полной загрузки), остальные качаются заранее (пока играет
    текущий — грузится следующий). Выход открывается ОДИН раз → нет пауз
    между языками и быстрый старт даже для длинного первого куска.
    """
    if not _STREAM_OK or not segments:
        return False
    samplerate, channels = _output_params()
    prefs = [None] * len(segments)

    def _start(i):
        if 0 <= i < len(segments) and prefs[i] is None:
            lang, chunk = segments[i]
            prefs[i] = _Prefetch(chunk, voice_for(lang))

    _start(1)                                  # пока играет кусок 0 — качаем 1 и 2
    _start(2)
    played = False
    try:
        with _sd.OutputStream(samplerate=samplerate, channels=channels,
                              dtype="int16", blocksize=STREAM_BLOCKSIZE) as out:
            # кусок 0 — ПОТОКОМ (быстрый старт, не ждём полной загрузки)
            lang0, chunk0 = segments[0]
            if _decode_stream_into(out, chunk0, voice_for(lang0),
                                   samplerate, channels, my_gen):
                played = True
            else:
                data = _download(chunk0, voice_for(lang0))
                if data and _decode_into(out, data, samplerate, channels, my_gen):
                    played = True
            # остальные куски — из предзагрузки (без пауз между языками)
            for i in range(1, len(segments)):
                if _stop.is_set() or my_gen != _current_generation():
                    break
                data = prefs[i].wait() if prefs[i] is not None else None
                if data and _decode_into(out, data, samplerate, channels, my_gen):
                    played = True
                _start(i + 2)
    except Exception as exc:                   # noqa: BLE001 — звук некритичен
        _log.warning("TTS: сегментный поток (%s)", exc)
    return played


def _safe_remove(path: str) -> None:
    """Удалить файл, не падая, если он занят/уже удалён."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
