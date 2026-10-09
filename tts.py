# -*- coding: utf-8 -*-
# =========================================================
# TTS.PY — озвучка ответов Джейн (edge-tts → mp3 → pygame)
# =========================================================
# Схема: текст → чистка эмодзи → выбор голоса по языку → скачивание mp3
# (edge-tts, ОНЛАЙН) → проигрывание pygame.
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
# stop() — по желанию: прервать текущую речь. Остальные имена (VOICE_*,
# remove_emojis, detect_language) оставлены для совместимости.
# =========================================================

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from typing import Dict, Optional, Tuple

import edge_tts
import pygame

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

# Микшер инициализируем один раз и держим живым: pygame.mixer.quit() после
# каждой реплики давал лишние init/quit и гонки. Нет звуковой карты — озвучка
# просто не пойдёт, но модуль обязан импортироваться.
try:
    pygame.mixer.init()
except Exception as exc:                      # noqa: BLE001 — важен сам факт
    _log.warning("TTS: pygame.mixer не инициализирован (%s)", exc)

# Голоса для разных языков
VOICE_EN = "en-US-JennyNeural"
VOICE_RU = "ru-RU-SvetlanaNeural"

RATE = "+10%"                 # скорость речи
DOWNLOAD_TIMEOUT = 7.0        # ТОЛЬКО скачивание (проигрывание — отдельно)
PLAYBACK_TICK = 0.05          # шаг опроса get_busy (для прерывания речи)
CACHE_LIMIT = 16              # сколько mp3 держим в памяти

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
def speak(text: str) -> None:
    """Озвучить текст. Блокирующая: вызывать из фонового потока.

    Порядок: чистка эмодзи → выбор голоса → синтез (кэш/скачивание) →
    проигрывание. Новая реплика важнее текущей: она прерывает предыдущую.
    """
    if not text or not str(text).strip():
        return
    clean_text = clean_for_speech(str(text))
    if not clean_text:
        return

    lang = detect_language(clean_text)
    voice = VOICE_RU if lang == "ru" else VOICE_EN
    print(f"🔊 Озвучивание на языке: {'Русский' if lang == 'ru' else 'English'} ({voice})")

    my_gen = _bump_generation()
    stop()                                     # новая реплика прерывает старую
    with _lock:
        _stop.clear()
        if my_gen != _current_generation():
            return                             # пока ждали — запросили ещё новее
        try:
            data = _synthesize(clean_text, voice)
        except Exception as exc:               # noqa: BLE001 — синтез не должен ронять поток
            print(f"⚠️ TTS ошибка синтеза: {exc}")
            data = None
        if not data or my_gen != _current_generation():
            return                             # синтез устарел/не удался — не играем
        _play(data, my_gen)


# ---------------------------------------------------------
# Синтез и кэш
# ---------------------------------------------------------
def _synthesize(text: str, voice: str) -> Optional[bytes]:
    """mp3-байты для (text, voice): из кэша или скачиванием. None при ошибке."""
    key = (voice, RATE, text)
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
    """Скачивает mp3 во ВРЕМЕННЫЙ файл и возвращает байты. Файл всегда убираем."""
    handle, path = tempfile.mkstemp(prefix="jane_tts_", suffix=".mp3")
    os.close(handle)

    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate=RATE)
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


def _safe_remove(path: str) -> None:
    """Удалить файл, не падая, если он занят/уже удалён."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
