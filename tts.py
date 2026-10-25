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
import wave
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


def _say(message: str) -> None:
    """Печать, которая НЕ роняет озвучку: в консоли cp1251 эмодзи падают.

    Замер 25.10.2026: `print("⏱ …")` внутри сегментного пути давал
    UnicodeEncodeError, и звук молча уходил в запасной путь.
    """
    try:
        print(message)
    except Exception:                  # noqa: BLE001 — печать не важнее звука
        pass


def _quiet_unraisable(unraisable):
    if "Event loop is closed" in str(getattr(unraisable, "exc_value", "")):
        return
    _default_unraisablehook(unraisable)


sys.unraisablehook = _quiet_unraisable

# Микшер pygame НЕ инициализируем на импорте: пока звучит потоковая озвучка
# (sounddevice), держать аудиоустройство открытым в pygame не нужно — это
# давало конфликт и «пропажу» звука. pygame.mixer.init() делается ЛЕНИВО
# в запасном пути (_play), если поток недоступен. Модуль импортируется всегда.

# Голоса ПО ЯЗЫКАМ. Emma (en-US) читает английский, а мультиязычный Ava
# терял «h» в связке «Hi, Damil» — ученик слышал «И, Дамил» (замер и A/B
# вслепую 25.10.2026: Emma и Ana говорят «Хай», Ava — нет).
# но на РУССКОМ даёт акцент (проверено: Whisper слышит искажения, напр.
# «Дамиль» → «Доми»). Поэтому русские куски читает русский голос — так
# каждая часть звучит НАТИВНО. Хочешь один голос — VOICE_RU = VOICE_EN
# (тогда русский будет с акцентом).
VOICE_EN = "en-US-EmmaNeural"
VOICE_RU = "ru-RU-SvetlanaNeural"
VOICE = VOICE_EN                    # голос по умолчанию (совместимость)

# Тон по голосам. Светлана ниже Авы (замер: ~165 Гц против ~225 Гц), из-за
# чего на смене языка «меняется человек». Поднимаем Светлану (+10 Гц) —
# подобранный вручную сдвиг, чтобы русская речь звучала естественно.
VOICE_PITCH = {
    "en-US-EmmaNeural": "+0Hz",
    "ru-RU-SvetlanaNeural": "+10Hz",
}


def pitch_for(voice):
    """Сдвиг тона (SSML pitch) для голоса. По умолчанию +0Hz."""
    return VOICE_PITCH.get(voice, "+0Hz")


# Скорость речи по голосам. Темп РАЗНЫЙ для языков (см. config): английский
# чуть медленнее — ученику легче различать слова; русский — быстрее (родной).
VOICE_RATE = {
    "en-US-EmmaNeural": getattr(config, "TTS_RATE_EN", "+0%"),
    "ru-RU-SvetlanaNeural": getattr(config, "TTS_RATE_RU", "+10%"),
}


def rate_for(voice, rate=None):
    """Скорость речи (SSML rate): своя для голоса или заданная явно.

    rate — необязательная скорость НА ОДИН запрос (например, "-50%" для
    медленного повтора слова из подсказки, 25.10.2026). None — прежнее
    поведение: скорость голоса из VOICE_RATE.
    """
    if rate:
        return rate
    return VOICE_RATE.get(voice, RATE)

RATE = "+10%"                 # скорость речи по умолчанию (если нет в VOICE_RATE)
WORD_SLOW_RATE = "-50%"       # медленный повтор слова в подсказке (полтемпа)
# Тишина ПЕРЕД первым звуком реплики. Звуковое устройство на старте
# выбрасывает первые ~100-200 мс, а первое слово короткое («Hi») —
# поэтому оно и пропадало в начале разговора (замер 25.10.2026).
LEAD_SILENCE_MS = 200
DOWNLOAD_TIMEOUT = 5.0        # ТОЛЬКО скачивание (проигрывание — отдельно)
DOWNLOAD_BUDGET = 7.0         # общий предел на ВСЕ повторы одного куска
PLAYBACK_TICK = 0.05          # шаг опроса get_busy (для прерывания речи)
CACHE_LIMIT = 16              # сколько mp3 держим в памяти
SEGMENT_WAIT_MAX = 1.5        # сколько ждём предзагрузку ПЕРЕД началом куска
STREAM_DEADLINE = 15.0        # страховка: поток одного куска не дольше, сек
WARMUP_TEXT = "Hello there! Let's start."

# --- потоковая озвучка ---
STREAM_FORMAT = "mp3"         # edge-tts отдаёт audio-24khz-...-mp3
STREAM_SRC_RATE = 24000       # частота mp3 от edge-tts
STREAM_BLOCKSIZE = 2400       # размер блока вывода (0.1 с при 24 кГц)

# edge-tts (онлайн) иногда отвечает 403 — делаем несколько попыток,
# иначе реплика прозвучит «в тишину».
RETRY_ATTEMPTS = 3
RETRY_DELAY = 0.3             # пауза между попытками, сек

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
# Части реплики (точная синхронизация лица с озвучкой)
# ---------------------------------------------------------
def _build_segments(parts, name=None, name_latin=None):
    """Куски для озвучки: [(номер части, язык, текст), ...].

    parts — части реплики (например, куски настроения из mood.plan_reply).
    Каждая часть режется ПО ЯЗЫКУ, чтобы русское читал русский голос, а
    английское — английский. Номер части нужен лицу робота: оно меняет
    эмоцию ровно на начале звука этой части, а не по оценке «символы ÷ скорость».
    Пустые части (только эмодзи/разметка) пропускаются.
    """
    out = []
    for index, part in enumerate(parts or []):
        clean_text = clean_for_speech(str(part or ""))
        if not clean_text:
            continue
        chunks = split_by_language(clean_text) or [
            (detect_language(clean_text), clean_text)]
        for lang, chunk in chunks:
            out.append((index, lang, _apply_name(chunk, lang, name, name_latin)))
    return out


class _PartTracker:
    """Сообщать о начале звучания новой ЧАСТИ реплики (один раз на часть).

    Колбэк зовётся из потока озвучки — внутри него нельзя трогать Tk
    (приложение отправляет вызов в главный поток через dispatcher).
    Ошибка колбэка не должна ломать звук, поэтому всё в try/except.
    """

    def __init__(self, callback=None) -> None:
        self.callback = callback
        self.last = None

    def start(self, index) -> None:
        if self.callback is None or index == self.last:
            return
        self.last = index
        try:
            self.callback(index)
        except Exception as exc:               # noqa: BLE001 — звук важнее
            _log.warning("TTS: колбэк части (%s)", exc)


# ---------------------------------------------------------
# Состояние (модуль-уровень: сериализация, прерывание, кэш)
# ---------------------------------------------------------
# --- уровень громкости для «эквалайзера» и рта робота ---
# Пишется из потока озвучки, читается из главного потока (простая переменная:
# гонки здесь безобидны — значение живёт миллисекунды).
_level = 0.0                 # 0..100
_level_at = 0.0              # время последнего обновления (monotonic)

# Последний сбой озвучки: "" — всё хорошо, иначе короткая причина для UI.
# Нужен, чтобы «Джейн молчит» не было загадкой: интерфейс может показать
# подсказку (edge-tts иногда отвечает 403 — это внешняя проблема сервиса).
last_failure = ""
LEVEL_STALE = 0.25           # дольше — считаем, что звука нет


def _report_level(mean_abs: float) -> None:
    """Обновить уровень по средней амплитуде буфера (int16)."""
    global _level, _level_at
    try:
        # средняя амплитуда речи ~1500..4000 → 37..100 по шкале 0..100
        _level = max(0.0, min(100.0, float(mean_abs) / 40.0))
    except (TypeError, ValueError):
        _level = 0.0
    _level_at = time.monotonic()


def get_level() -> float:
    """Текущая громкость озвучки 0..100 (0.0, если звука нет)."""
    if time.monotonic() - _level_at > LEVEL_STALE:
        return 0.0
    return _level


def _reset_level() -> None:
    global _level
    _level = 0.0


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
    _reset_level()
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:                          # noqa: BLE001 — прерывание не должно падать
        pass


def clear_cache() -> None:
    """Очистить кэш озвучки (например, при смене голосов/настроек)."""
    _cache.clear()


# ---------------------------------------------------------
# Прогрев соединения с edge-tts
# ---------------------------------------------------------
# Замер на живой сети (каждый замер — НОВЫЙ процесс, как запуск приложения):
#   1-й запрос  — 7.01 с (таймаут) или «No audio was received»;
#   2-й         — 3.11 с;
#   3-й         — 5.08 с;
#   4-й и далее — 1.0–1.3 с.
# То есть первые секунды после запуска соединение «холодное». Первая реплика
# урока приходится ровно на это время, и ученик слышал: «Hello, Damil!» →
# долгая пауза → остаток фразы. Прогрев делает эти запросы ЗАРАНЕЕ, пока
# ученик ещё читает приветствие.
_warm_lock = threading.Lock()
_warm_done = False
_warm_running = False
_warm_last = 0.0             # когда последний раз пытались греть (monotonic)
WARMUP_RETRY_SECONDS = 20.0  # не чаще раза в 20 с (иначе при обрыве сети
                             # каждая неудачная загрузка плодила бы поток)


def warmup(attempts: int = 4) -> bool:
    """Один (или несколько) БЕЗЗВУЧНЫХ запросов к edge-tts — «разогреть» связь.

    True — соединение готово. Ошибки глушим: без сети озвучка всё равно не
    заработает, падать из-за прогрева нельзя.
    """
    global _warm_done, _warm_running, _warm_last
    with _warm_lock:
        if _warm_done:
            return True
        if _warm_running:
            return False
        _warm_running = True
        _warm_last = time.monotonic()
    ok = False
    try:
        for _attempt in range(max(1, int(attempts))):
            for voice in (VOICE_EN, VOICE_RU):
                try:
                    if _download_once(WARMUP_TEXT, voice):
                        ok = True
                except Exception:              # noqa: BLE001 — прогрев не критичен
                    pass
            if ok:
                break
    finally:
        with _warm_lock:
            _warm_done = ok
            _warm_running = False
    _log.info("TTS: прогрев %s", "готов" if ok else "не удался")
    return ok


def warmup_async() -> None:
    """Запустить прогрев в ФОНЕ (вызывается при старте приложения)."""
    if _warm_done or _warm_running:
        return
    # Вторая попытка не сразу: при обрыве сети каждая неудачная загрузка
    # звала бы прогрев, и потоки копились бы.
    if time.monotonic() - _warm_last < WARMUP_RETRY_SECONDS:
        return
    threading.Thread(target=warmup, daemon=True).start()


def _schedule_rewarm() -> None:
    """Сбросить отметку прогрева и разогреть связь заново (в фоне)."""
    global _warm_done
    with _warm_lock:
        if _warm_running:
            return
        _warm_done = False
    warmup_async()               # сам не чаще WARMUP_RETRY_SECONDS


# ---------------------------------------------------------
# Публичный вход
# ---------------------------------------------------------
def speak(text: str, name=None, name_latin=None, parts=None, on_part=None,
          rate=None) -> bool:
    """Озвучить текст. Блокирующая: вызывать из фонового потока.

    Возвращает True, если что-то прозвучало (False — не удалось озвучить,
    например edge-tts ответил 403; причина остаётся в tts.last_failure).

    name / name_latin: имя ученика в двух формах. Для КАЖДОГО куска имя
    подставляется НА ЯЗЫКЕ куска (ru → кириллица, en → латиница): в русском
    тексте имя звучит по-русски, в английском — по-английски.

    parts / on_part: НЕОБЯЗАТЕЛЬНО. parts — части реплики (например, куски
    настроения). Тогда текст режется по ним, а on_part(номер) вызывается в
    момент, когда начинается звук этой части. Так лицо робота меняет эмоцию
    РОВНО вместе со звуком. Без parts всё работает как раньше (одна часть).

    Смешанный текст разбивается ПО ЯЗЫКУ: русские куски читает русский
    голос, английские — английский. Новая реплика важнее текущей.

    rate — НЕОБЯЗАТЕЛЬНО: скорость на эту реплику ("-50%" — вдвое медленнее).
    Нужно для медленного повтора слова по клику (25.10.2026).
    """
    if not text or not str(text).strip():
        return False
    clean_text = clean_for_speech(str(text))
    if not clean_text:
        return False

    # части реплики (по умолчанию одна) → куски по языку, с номером части
    segments = _build_segments([clean_text] if parts is None else parts,
                               name, name_latin)
    if not segments:                       # только цифры/знаки/эмодзи
        return False

    global last_failure
    my_gen = _bump_generation()
    stop()                                     # новая реплика прерывает старую
    with _lock:
        _stop.clear()
        tracker = _PartTracker(on_part)
        # Основной путь: СЕГМЕНТНЫЙ поток — один звуковой выход на всю реплику
        # и предзагрузка кусков. Между языками нет пауз (раньше каждый кусок
        # открывал свой поток и качался по очереди — отсюда «задумчивость»).
        played = False
        if _streaming_enabled():
            try:
                if _stream_play_segments(segments, my_gen, tracker, rate=rate):
                    _reset_level()
                    last_failure = ""
                    return True
            except Exception as exc:           # noqa: BLE001 — вернёмся к запасному
                _log.warning("TTS: сегментный путь не сработал (%s)", exc)
        # Запасной путь: по кускам (поток/скачивание, с повторами).
        for index, lang, chunk in segments:
            if _stop.is_set() or my_gen != _current_generation():
                return played                  # прервали / пришла более новая
            tracker.start(index)
            if _speak_chunk(chunk, voice_for(lang), my_gen, rate):
                played = True
        last_failure = "" if played else "edge-tts не ответил (проверь интернет)"
        return played


def _speak_chunk(text: str, voice: str, my_gen: int, rate=None) -> bool:
    """Озвучить ОДИН кусок. True — что-то прозвучало."""
    _say(f"🔊 Озвучка: {voice} — {text[:48]!r}")
    # Основной путь: ПОТОК (звучим по первым байтам; повторы — внутри).
    if _streaming_enabled():
        try:
            if _stream_play(text, voice, my_gen, rate):
                return True
        except Exception as exc:               # noqa: BLE001 — вернёмся к запасному
            _log.warning("TTS: потоковый путь не сработал (%s)", exc)
    if _stop.is_set() or my_gen != _current_generation():
        return False
    # Запасной путь: скачать mp3 целиком и проиграть (pygame; повторы внутри).
    try:
        data = _synthesize(text, voice, rate)
    except Exception as exc:                   # noqa: BLE001 — синтез не должен ронять поток
        _say(f"⚠️ TTS ошибка синтеза: {exc}")
        data = None
    if not data:
        # Сети нет — последний рубеж: локальный голос (только английский).
        if my_gen != _current_generation():
            return False
        wav = piper_synth(text) if voice != VOICE_RU else None
        if not wav:
            return False
        _say("🔉 TTS: кусок прочитан локально (piper)")
        _play(wav, my_gen, suffix=".wav")
        return True
    if my_gen != _current_generation():
        return False                           # синтез устарел — не играем
    _play(data, my_gen)
    return True


# ---------------------------------------------------------
# Синтез и кэш
# ---------------------------------------------------------
def _synthesize(text: str, voice: str, rate=None) -> Optional[bytes]:
    """mp3-байты для (text, voice, rate): из кэша или скачиванием. None при ошибке."""
    key = (voice, rate_for(voice, rate), text)
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached

    data = _download(text, voice, rate)
    if data:
        _cache[key] = data
        _cache.move_to_end(key)
        while len(_cache) > CACHE_LIMIT:
            _cache.popitem(last=False)
    return data


def _download_race(text: str, voice: str, jobs: int, rate=None) -> Optional[bytes]:
    """Несколько ОДНОВРЕМЕННЫХ запросов одного куска — берём первый удачный.

    edge-tts эпизодически «болеет»: замер 20.10.2026 — 18 запросов подряд дали
    8 сбоёв (44%), а через минуту те же 18 прошли все. Один запрос — лотерея.
    Три параллельных на кусок: 10/10 успешно, медиана 1.08 с. Поэтому вместо
    «ждать по очереди» стреляем сразу несколькими и берём первый ответ.
    Проигравшие потоки просто бросаем (daemon): они не держат приложение.
    """
    jobs = max(1, int(jobs))
    results: "queue.Queue" = queue.Queue()
    for _ in range(jobs):
        threading.Thread(target=lambda: results.put(_download_once(text, voice, rate)),
                         daemon=True).start()
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT + 0.5
    for _ in range(jobs):
        left = deadline - time.monotonic()
        if left <= 0:
            break
        try:
            data = results.get(timeout=left)
        except queue.Empty:
            break
        if data:
            return data
    return None


def _download(text: str, voice: str, rate=None) -> Optional[bytes]:
    """Скачивает mp3 во временный файл: сначала ПАРАЛЛЕЛЬНО, потом по очереди.

    Вся загрузка ограничена ОБЩИМ временем DOWNLOAD_BUDGET: раньше три попытки
    по таймауту 7 с давали до 26 с тишины посреди фразы (замер).

    Сколько запросов делать разом — config.TTS_PARALLEL_JOBS (3 по умолчанию,
    1 — прежнее поведение, строго по очереди). Общее число попыток остаётся
    RETRY_ATTEMPTS: параллельный залп СЧИТАЕТСЯ попытками, поэтому при jobs=3
    и трёх неудачах повторов уже не будет (ждать дольше незачем — сервис
    всё равно лежит).
    """
    deadline = time.monotonic() + DOWNLOAD_BUDGET
    try:
        jobs = int(getattr(config, "TTS_PARALLEL_JOBS", 1) or 1)
    except (TypeError, ValueError):
        jobs = 1
    jobs = max(1, min(jobs, RETRY_ATTEMPTS))
    attempts = 0
    if jobs > 1:
        data = _download_race(text, voice, jobs, rate)
        attempts = jobs
        if data:
            return data
    while attempts < RETRY_ATTEMPTS:
        data = _download_once(text, voice, rate)
        attempts += 1
        if data:
            return data
        # повторяем, только если СЛЕДУЮЩАЯ попытка успеет в бюджет:
        # так «зависшая» попытка не тянет за собой ещё одну на 5 с
        if time.monotonic() + DOWNLOAD_TIMEOUT >= deadline:
            break
        time.sleep(RETRY_DELAY)
    _schedule_rewarm()               # соединение «протухло» — прогреем заново
    return None


def _download_once(text: str, voice: str, rate=None) -> Optional[bytes]:
    """Одно скачивание mp3 во временный файл. Файл всегда убираем."""
    handle, path = tempfile.mkstemp(prefix="jane_tts_", suffix=".mp3")
    os.close(handle)

    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate=rate_for(voice, rate),
                                           pitch=pitch_for(voice))
        await communicate.save(path)

    try:
        asyncio.run(asyncio.wait_for(_run(), timeout=DOWNLOAD_TIMEOUT))
    except asyncio.TimeoutError:
        _say("⚠️ TTS: таймаут скачивания")
        _safe_remove(path)
        return None
    except Exception as exc:                   # noqa: BLE001 — сеть/сервис любые
        _say(f"⚠️ TTS ошибка: {exc}")
        _safe_remove(path)
        return None

    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        _say(f"⚠️ TTS: файл не прочитан ({exc})")
        return None
    finally:
        _safe_remove(path)


# ---------------------------------------------------------
# Проигрывание
# ---------------------------------------------------------
def _play(data: bytes, my_gen: int, suffix: str = ".mp3") -> None:
    """Проигрывает mp3 (или wav локального голоса) из временного файла.

    Прерываемо (stop/новая реплика). suffix — расширение временного файла:
    pygame определяет формат по нему, поэтому для piper нужен ".wav".
    """
    handle, path = tempfile.mkstemp(prefix="jane_tts_", suffix=suffix)
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
        _say(f"⚠️ TTS воспроизведение ошибка: {exc}")
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


def _edge_stream(text: str, voice: str, chunks, rate=None) -> None:
    """Качает mp3-чанки edge-tts в очередь и кладёт None в конце."""
    async def _go():
        async for chunk in edge_tts.Communicate(text, voice, rate=rate_for(voice, rate),
                                                     pitch=pitch_for(voice)).stream():
            if chunk.get("type") == "audio":
                chunks.put(chunk["data"])
    try:
        # страховка: зависшее соединение не должно держать поток вечно
        asyncio.run(asyncio.wait_for(_go(), timeout=STREAM_DEADLINE))
    except asyncio.TimeoutError:
        _log.warning("TTS поток: не уложился в %.0f с", STREAM_DEADLINE)
    except Exception as exc:                   # noqa: BLE001 — сбой сети/сервиса
        _log.warning("TTS поток: %s", exc)
    finally:
        chunks.put(None)


def _stream_play(text: str, voice: str, my_gen: int, rate=None) -> bool:
    """Потоковая озвучка С ПОВТОРАМИ (edge-tts иногда отвечает 403).

    True — что-то прозвучало; False — не вышло (переходим к запасному пути).
    """
    if not _STREAM_OK:
        return False
    for _attempt in range(RETRY_ATTEMPTS):
        if _stop.is_set() or my_gen != _current_generation():
            return False
        if _stream_once(text, voice, my_gen, rate):
            return True
        time.sleep(RETRY_DELAY)
    return False


def _stream_once(text: str, voice: str, my_gen: int, rate=None) -> bool:
    """Одна попытка потоковой озвучки. True — что-то проиграли."""
    if not _STREAM_OK:
        return False
    chunks = queue.Queue()
    reader = _ByteStream(chunks)
    threading.Thread(target=_edge_stream, args=(text, voice, chunks, rate),
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
            try:                      # громкость → эквалайзер и губы робота
                _report_level(float(_np.abs(arr).mean()))
            except Exception:         # noqa: BLE001 — измерение не должно мешать звуку
                pass
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
# Сколько кусков качаем ОДНОВРЕМЕННО. Куски короткие, поэтому 6 запросов к
# edge-tts проходят спокойно (замер: 7 кусков готовы за ~1.1 с); ограничитель
# нужен только чтобы длинная реплика не открывала десяток соединений сразу.
_PREFETCH_SLOTS = threading.BoundedSemaphore(6)


class _Prefetch:
    """Фоновая загрузка mp3 одного куска (играем текущий — качаем следующий)."""

    def __init__(self, text: str, voice: str, rate=None) -> None:
        self.text = text
        self.voice = voice
        self.rate = rate
        self._data = None
        self._event = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            with _PREFETCH_SLOTS:            # не больше 6 скачиваний разом
                self._data = _download(self.text, self.voice, self.rate)
        except Exception:                      # noqa: BLE001 — сбой загрузки не критичен
            self._data = None
        finally:
            self._event.set()

    def wait(self, timeout=None):
        self._event.wait(timeout)
        return self._data


def _decode_bytes_into(out, data, samplerate, channels, my_gen,
                       fmt: str = STREAM_FORMAT) -> bool:
    """Декодирует аудио-байты (в памяти) и пишет PCM в ОБЩИЙ поток вывода.

    fmt — формат контейнера: "mp3" (edge-tts) или "wav" (локальный piper).
    Раньше здесь был жёстко mp3; для локального запаса понадобился wav,
    а дублировать разбор кадров, ресемплинг и уровень громкости незачем.
    """
    try:
        container = av.open(io.BytesIO(data), format=fmt)
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
            try:                      # громкость → эквалайзер и губы робота
                _report_level(float(_np.abs(arr).mean()))
            except Exception:         # noqa: BLE001 — измерение не должно мешать звуку
                pass

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


def _decode_into(out, data, samplerate, channels, my_gen) -> bool:
    """Декодирует mp3-байты edge-tts (совместимость: прежняя сигнатура)."""
    return _decode_bytes_into(out, data, samplerate, channels, my_gen,
                              STREAM_FORMAT)


def _decode_stream_into(out, text, voice, samplerate, channels, my_gen,
                        rate=None) -> bool:
    """Декодирует mp3-ПОТОК edge-tts прямо в общий выход (старт по первым байтам)."""
    chunks = queue.Queue()
    threading.Thread(target=_edge_stream, args=(text, voice, chunks, rate),
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
            try:                      # громкость → эквалайзер и губы робота
                _report_level(float(_np.abs(arr).mean()))
            except Exception:         # noqa: BLE001 — измерение не должно мешать звуку
                pass

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


# ---------------------------------------------------------
# Локальный запас: piper (работает без интернета)
# ---------------------------------------------------------
# edge-tts — ОНЛАЙН. Когда сервис недоступен (нет сети, «No audio was
# received», 403), кусок раньше пропадал МОЛЧА. Теперь английский кусок
# читает локальный piper: замер 20.10.2026 — файл 60 МБ, загрузка 0.93 с,
# RTF 0.05, память 156 МБ, частота 22050 Гц. Русский piper не годится по
# качеству (решение пользователя), поэтому русские куски — только edge-tts,
# но и они больше не теряются: их берёт параллельный залп запросов.
_piper_lock = threading.Lock()
_piper_voice = None
_piper_failed = False
_piper_cache: "OrderedDict[str, bytes]" = OrderedDict()
PIPER_CACHE_LIMIT = 16


def piper_path() -> str:
    """Полный путь к файлу голоса piper (из config, папка — от корня проекта)."""
    name = str(getattr(config, "PIPER_VOICE_EN", "") or "")
    if not name:
        return ""
    folder = str(getattr(config, "PIPER_MODEL_DIR", "models/piper"))
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, folder.replace("/", os.sep), name)


def piper_available() -> bool:
    """Есть ли локальный запас: включён, ещё не падал и файл голоса на месте."""
    if not getattr(config, "PIPER_FALLBACK", False):
        return False
    if _piper_failed:
        return False
    path = piper_path()
    return bool(path) and os.path.exists(path)


def piper_synth(text: str) -> Optional[bytes]:
    """WAV-байты локального голоса. None — не вышло (кусок тогда молчит).

    Голос грузится ЛЕНИВО при первой нужде (0.93 с) и живёт в памяти
    (~156 МБ). Падение piper не ломает озвучку: ставим флаг и больше не
    пробуем — приложение работает как раньше, только без запаса.
    """
    global _piper_voice, _piper_failed
    if not text:
        return None
    cached = _piper_cache.get(text)
    if cached is not None:
        _piper_cache.move_to_end(text)
        return cached
    with _piper_lock:
        if not piper_available():
            return None
        if _piper_voice is None:
            try:
                from piper import PiperVoice
                started = time.monotonic()
                _piper_voice = PiperVoice.load(piper_path())
                _say("🔉 TTS: локальный голос готов за %.2f с"
                      % (time.monotonic() - started))
            except Exception as exc:           # noqa: BLE001 — нет piper/файла
                _piper_failed = True
                _log.warning("TTS: piper не загрузился (%s)", exc)
                return None
        try:
            from piper import SynthesisConfig
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                _piper_voice.synthesize_wav(
                    text, wav_file,
                    syn_config=SynthesisConfig(
                        length_scale=float(getattr(config, "PIPER_LENGTH_SCALE", 1.0))))
            data = buffer.getvalue()
        except Exception as exc:               # noqa: BLE001 — синтез не критичен
            _log.warning("TTS: piper не синтезировал (%s)", exc)
            return None
    if not data:
        return None
    _piper_cache[text] = data
    _piper_cache.move_to_end(text)
    while len(_piper_cache) > PIPER_CACHE_LIMIT:
        _piper_cache.popitem(last=False)
    return data


def _piper_play(out, text, lang, samplerate, channels, my_gen) -> bool:
    """Прочитать кусок локальным голосом (только английский).

    Русский piper не годится по качеству, поэтому для "ru" сразу False:
    лучше тишина, чем неправильные ударения (решение 20.10.2026).
    """
    if lang is None:
        lang = detect_language(text)
    if lang != "en":
        return False
    data = piper_synth(text)
    if not data:
        return False
    if _stop.is_set() or my_gen != _current_generation():
        return False
    played = _decode_bytes_into(out, data, samplerate, channels, my_gen, "wav")
    if played:
        _say("🔉 TTS: кусок прочитан локально (piper)")
    return played


def _play_segment(out, text, voice, samplerate, channels, my_gen,
                  data=None, lang=None, rate=None) -> bool:
    """Проиграть ОДИН кусок так, чтобы НИ ОДНО слово не пропало.

    Порядок попыток: готовые mp3-байты (предзагрузка) → поток → загрузка
    целиком (уже с параллельными запросами) → ЛОКАЛЬНЫЙ голос piper.
    Раньше при неудачной предзагрузке кусок МОЛЧА выбрасывался — и из
    смешанной фразы исчезало слово (например, русское). Теперь английское
    слово звучит всегда: либо из сети, либо локально.

    lang — язык куска ("ru"/"en"); нужен локальному запасу. Без него язык
    определяется по тексту (совместимость со старыми вызовами).

    True — что-то прозвучало; False — не вышло (или реплику прервали).
    """
    if data and _decode_into(out, data, samplerate, channels, my_gen):
        return True
    if _stop.is_set() or my_gen != _current_generation():
        return False
    if _decode_stream_into(out, text, voice, samplerate, channels, my_gen, rate):
        return True
    if _stop.is_set() or my_gen != _current_generation():
        return False
    data = _download(text, voice, rate)          # последняя попытка целиком
    if data and _decode_into(out, data, samplerate, channels, my_gen):
        return True
    # Последний рубеж: интернета нет — читаем локальным голосом.
    return _piper_play(out, text, lang, samplerate, channels, my_gen)


def _write_silence(out, samplerate, channels,
                   ms: int = LEAD_SILENCE_MS) -> bool:
    """Отдать в звук ms миллисекунд тишины: устройство просыпается на НЕЙ.

    Тихо и без замеров: уровень не отдаём (робот не должен шевелить губами).
    """
    try:
        frames = int(samplerate * max(0, int(ms)) / 1000)
    except (TypeError, ValueError):
        return False
    if frames <= 0:
        return False
    if channels > 1:
        data = _np.zeros((frames, channels), dtype="int16")
    else:
        data = _np.zeros(frames, dtype="int16")
    out.write(_np.ascontiguousarray(data))
    return True


def _stream_play_segments(segments, my_gen, tracker=None, rate=None) -> bool:
    """Проиграть все куски ЧЕРЕЗ ОДИН звуковой выход.

    Первый кусок читаем ПОТОКОМ (звук — как только пришли первые байты, не
    дожидаясь полной загрузки), остальные качаются ЗАРАНЕЕ — пока звучит
    текущий. Выход открывается ОДИН раз → нет пауз между языками.

    Сколько кусков качать заранее — решает config.TTS_PREFETCH_ALL:
      True  — ВСЕ сразу. Замер: 7 кусков (4 русских вставки) готовы за ~1.1 с,
              а первый кусок звучит ~2 с, поэтому к моменту смены голоса
              русский кусок уже наготове — пауз нет, фраза звучит целиком;
      False — прежнее поведение (два куска вперёд): на длинной реплике был
              слышен провал до 2.3 с перед 4-м куском.

    tracker (необязательно) — _PartTracker: сообщает лицу робота, какая
    часть реплики звучит сейчас. Куски — (номер части, язык, текст); если
    пришли пары (язык, текст), номер части считаем нулевым.
    """
    if not _STREAM_OK or not segments:
        return False
    segments = [seg if len(seg) >= 3 else (0, seg[0], seg[1]) for seg in segments]
    samplerate, channels = _output_params()
    prefs = [None] * len(segments)

    def _start(i):
        if 0 <= i < len(segments) and prefs[i] is None:
            _index, lang, chunk = segments[i]
            prefs[i] = _Prefetch(chunk, voice_for(lang), rate)

    prefetch_all = bool(getattr(config, "TTS_PREFETCH_ALL", True))
    if prefetch_all:
        for i in range(1, len(segments)):      # ВСЕ куски — сразу
            _start(i)
    else:
        _start(1)                              # прежний режим: 1 и 2
        _start(2)
    played = False
    waits = []                                 # сколько ждали каждый кусок
    try:
        t_open = time.monotonic()
        with _sd.OutputStream(samplerate=samplerate, channels=channels,
                              dtype="int16", blocksize=STREAM_BLOCKSIZE) as out:
            # Тишина перед речью: устройство просыпается на ней, а не на
            # первом слове (иначе «Hi» в начале съедалось — см. LEAD_SILENCE_MS).
            _write_silence(out, samplerate, channels)
            # кусок 0 — ПОТОКОМ (быстрый старт, не ждём полной загрузки)
            index0, lang0, chunk0 = segments[0]
            if tracker is not None:
                tracker.start(index0)
            if _play_segment(out, chunk0, voice_for(lang0),
                             samplerate, channels, my_gen, lang=lang0, rate=rate):
                played = True
                _say("TTS: первый звук через %.2f с (включая %.0f мс тишины)"
                     % (time.monotonic() - t_open, LEAD_SILENCE_MS))
            # остальные куски — из предзагрузки (без пауз между языками)
            for i in range(1, len(segments)):
                if _stop.is_set() or my_gen != _current_generation():
                    break
                if tracker is not None:
                    tracker.start(segments[i][0])
                _index, lang, chunk = segments[i]
                # Ждём готовый кусок НЕ ДОЛЬШЕ SEGMENT_WAIT_MAX: если
                # предзагрузка застряла, быстрее начать поток заново, чем
                # держать ученика в тишине (раньше wait() ждал до 26 с).
                t_wait = time.monotonic()
                data = (prefs[i].wait(SEGMENT_WAIT_MAX)
                        if prefs[i] is not None else None)
                waits.append(round(time.monotonic() - t_wait, 2))
                if _play_segment(out, chunk, voice_for(lang),
                                 samplerate, channels, my_gen, data, lang=lang,
                                 rate=rate):
                    played = True
                if not prefetch_all:
                    _start(i + 2)
    except Exception as exc:                   # noqa: BLE001 — звук некритичен
        _log.warning("TTS: сегментный поток (%s)", exc)
    finally:
        if waits and max(waits) > 0.3:         # видно в logs\app.log
            _say("⏱ TTS: ожидание кусков, с: %s" % waits)
    return played


def _safe_remove(path: str) -> None:
    """Удалить файл, не падая, если он занят/уже удалён."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
