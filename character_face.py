# -*- coding: utf-8 -*-
# =========================================================
# CHARACTER_FACE.PY — «лицо» робота: эмоции, взгляд, моргание, речь, кивок
# =========================================================
# Принцип: ТЕЛО — КУКЛА, ЛИЦО — СМЕННЫЕ НАКЛЕЙКИ.
# Берём face_empty.png (робот с пустым экраном) и поверх кладём слой глаз
# и слой рта. Меняем наклейки — меняется выражение.
#
# ВАЖНО: все слои выгружены по ОБЩЕМУ холсту (661x377), поэтому накладываются
# друг на друга без подгонки координат.
#
# Что здесь есть:
#   * STATES — таблица «эмоция → глаза + рты + поведение»;
#   * FaceAnimator — «режиссёр»: по времени решает, какие слои показать
#     (моргание, блуждание взгляда, смена формы рта, кивок, речь);
#   * FaceRenderer — склейка слоёв в картинку с кэшем;
#   * плавные переходы: между двумя состояниями глаз картинки СМЕШИВАЮТСЯ
#     (cross-fade), поэтому моргание и смена взгляда не «щёлкают».
#
# КИВОК. Отдельных картинок «робот кивнул» нет — и не нужно: кивок делается
# СМЕЩЕНИЕМ лица (глаза + рот) вниз внутри экрана на несколько пикселей и
# обратно. Экран неподвижен (это часть корпуса), а содержимое «клюёт» вниз —
# ровно то, как кивают NPC.
#
# Модуль чистый: ни Tk, ни потоков, ни звука. Снаружи нужно только
# вызывать tick(dt, level) и отдавать картинку в интерфейс.
# =========================================================

from __future__ import annotations

import logging
import math
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

# ---------------------------------------------------------
# Имена состояний
# ---------------------------------------------------------
IDLE = "idle"
LISTENING = "listening"
THINKING = "thinking"
SPEAKING = "speaking"
HAPPY = "happy"
SMILE = "smile"
SAD = "sad"
SURPRISED = "surprised"
SCORN = "scorn"
ANGRY = "angry"

# «Говорящие» варианты: те же глаза по настроению + рот, который двигается.
# Нужны для «актёрской игры»: Джейн рассказывает историю и её лицо меняется
# по предложениям (см. mood.py).
SPEAK_HAPPY = "speak_happy"
SPEAK_SAD = "speak_sad"
SPEAK_SURPRISED = "speak_surprised"
SPEAK_THINKING = "speak_thinking"
SPEAK_STORY = "speak_story"

# ---------------------------------------------------------
# Тайминги (секунды) — одна точка настройки «живости»
# ---------------------------------------------------------
BLINK_MIN = 2.8            # пауза между морганиями (по умолчанию)
BLINK_MAX = 6.0
BLINK_DURATION = 0.11      # сколько держим закрытые глаза
BLINK_SHUT_CHANCE = 0.22   # шанс «крепко зажмуриться»
BLINK_SHUT_DURATION = 0.20

GAZE_MIN = 2.2             # пауза между «взглядами в сторону»
GAZE_MAX = 4.5
GAZE_HOLD = 1.1            # сколько смотрим в сторону

EYES_FADE = 0.12           # плавность смены глаз (cross-fade)
MOUTH_RATE = 6.2           # «слогов» в секунду во время речи
MOUTH_SILENCE = 0.12       # тишина дольше — рот закрывается

MOUTH_SHAPE_PERIOD = 1.1   # как часто меняется ФОРМА закрытого рта («думает»)

NOD_DEPTH = 6              # на сколько пикселей лицо «клюёт» вниз при кивке
NOD_DURATION = 0.40        # длительность одного кивка
NOD_GAP = 0.22             # пауза между двумя кивками подряд
NOD_DELAY_AFTER_BLINK = 0.18   # «моргнул → чуть подождал → кивнул»
NOD_AFTER_BLINK_MIN = 1        # кивков после моргания
NOD_AFTER_BLINK_MAX = 2
NOD_ON_PAUSE = 0.32        # сколько тишины в речи ученика = «пора кивнуть»
NOD_COOLDOWN = 1.9         # не кивать чаще, чем раз в столько секунд
PAUSE_LEVEL = 6.0          # ниже этой громкости считаем тишиной
PAUSE_AFTER_LEVEL = 14.0   # до этого была речь (чтобы не кивать в полной тишине)


# ---------------------------------------------------------
# Таблица эмоций
# ---------------------------------------------------------
@dataclass(frozen=True)
class StateConfig:
    """Как выглядит и ведёт себя эмоция."""
    eyes: str                                  # базовый слой глаз
    mouth_closed: str                          # рот в покое
    mouth_half: str = ""                       # приоткрыт (для речи)
    mouth_open: str = ""                       # широко открыт
    blink: bool = True                         # моргает ли
    blink_range: Tuple[float, float] = (BLINK_MIN, BLINK_MAX)
    gaze: bool = False                         # блуждает ли взглядом
    talk: bool = False                         # двигает ли ртом на речи
    static_mouth: str = ""                     # рот-«застывшее выражение»
    mouth_cycle: Tuple[str, ...] = ()          # смена ФОРМЫ закрытого рта
    nod: bool = False                          # кивает ли
    transient: float = 0.0                     # через сколько секунд сменить эмоцию
    transient_to: str = ""                     # куда уйти ("" → в покой)


# Рты: пары «закрыт/приоткрыт/открыт» — из файлов пользователя.
_M_NEUTRAL = ("mouth_closed_neutral", "mouth_open_neutral", "mouth_open")
_M_THINK = ("mouth_thinking_closed", "mouth_thinking_open", "")
_M_SMILE = ("mouth_smile_closed", "mouth_smile_open", "")
_M_SAD = ("mouth_sad_closed", "mouth_sad_open", "")

STATES: Dict[str, StateConfig] = {
    # покой: моргает, смотрит по сторонам, рот закрыт
    IDLE: StateConfig(eyes="eyes_normal_open", mouth_closed=_M_NEUTRAL[0],
                      mouth_half=_M_NEUTRAL[1], mouth_open=_M_NEUTRAL[2],
                      blink=True, gaze=True, talk=False),

    # слушает ученика: ЛЁГКАЯ УЛЫБКА, моргает чаще (2-3 с), кивает
    LISTENING: StateConfig(eyes="eyes_normal_open", mouth_closed=_M_SMILE[0],
                           static_mouth=_M_SMILE[0],
                           blink=True, blink_range=(2.0, 3.0),
                           gaze=False, talk=False, nod=True),

    # думает: ФОРМА закрытого рта меняется (не «жуёт», а «подбирает слова»)
    THINKING: StateConfig(eyes="eyes_thinking", mouth_closed=_M_THINK[0],
                          blink=False, gaze=False, talk=False,
                          mouth_cycle=(_M_THINK[0], _M_NEUTRAL[0], _M_THINK[0],
                                       _M_SMILE[0])),

    # говорит: рот двигается по громкости (три ступени)
    SPEAKING: StateConfig(eyes="eyes_normal_open", mouth_closed=_M_NEUTRAL[0],
                          mouth_half=_M_NEUTRAL[1], mouth_open=_M_NEUTRAL[2],
                          blink=True, gaze=False, talk=True),

    # радость (урок пройден / похвала) — держится подольше
    HAPPY: StateConfig(eyes="eyes_happy", mouth_closed=_M_SMILE[0],
                       static_mouth=_M_SMILE[0], blink=False, gaze=False,
                       transient=2.6),

    # тёплая улыбка (мягкая похвала)
    SMILE: StateConfig(eyes="eyes_smile", mouth_closed=_M_SMILE[0],
                       static_mouth=_M_SMILE[0], blink=False, gaze=False,
                       transient=2.2),

    # грусть — наигранная: держится 1.5 с и СМЕНЯЕТСЯ УЛЫБКОЙ
    # (именно переход в улыбку и делает её «слегка наигранной»)
    SAD: StateConfig(eyes="eyes_sad", mouth_closed=_M_SAD[0],
                     static_mouth=_M_SAD[0], blink=False, gaze=False,
                     transient=1.5, transient_to=SMILE),

    # удивление — рот застыл приоткрытым
    SURPRISED: StateConfig(eyes="eyes_surprised", mouth_closed=_M_NEUTRAL[1],
                           static_mouth=_M_NEUTRAL[1], blink=False, gaze=False,
                           transient=1.4),

    # ирония / хитринка
    SCORN: StateConfig(eyes="eyes_scorn", mouth_closed=_M_SMILE[0],
                       static_mouth=_M_SMILE[0], blink=False, gaze=False,
                       transient=1.6),

    # строгий вид — тоже КОРОТКИЙ и наигранный
    ANGRY: StateConfig(eyes="eyes_angry", mouth_closed=_M_SAD[0],
                       static_mouth=_M_SAD[0], blink=False, gaze=False,
                       transient=1.5),

    # ---------- «говорящие» варианты (рот двигается по громкости) ----------
    SPEAK_HAPPY: StateConfig(eyes="eyes_smile", mouth_closed=_M_SMILE[0],
                             mouth_half=_M_SMILE[1], mouth_open=_M_SMILE[1],
                             blink=True, gaze=True, talk=True),
    SPEAK_SAD: StateConfig(eyes="eyes_sad", mouth_closed=_M_SAD[0],
                           mouth_half=_M_SAD[1], mouth_open=_M_SAD[1],
                           blink=True, gaze=False, talk=True),
    SPEAK_SURPRISED: StateConfig(eyes="eyes_surprised", mouth_closed=_M_NEUTRAL[0],
                                 mouth_half=_M_NEUTRAL[1], mouth_open=_M_NEUTRAL[2],
                                 blink=False, gaze=False, talk=True),
    SPEAK_THINKING: StateConfig(eyes="eyes_thinking", mouth_closed=_M_THINK[0],
                                mouth_half=_M_THINK[1], mouth_open=_M_THINK[1],
                                blink=False, gaze=False, talk=True),
    # рассказ: обычные глаза, гуляет взглядом, рот по громкости
    SPEAK_STORY: StateConfig(eyes="eyes_normal_open", mouth_closed=_M_NEUTRAL[0],
                             mouth_half=_M_NEUTRAL[1], mouth_open=_M_NEUTRAL[2],
                             blink=True, gaze=True, talk=True),
}


# Настроение текста (mood.py) → «говорящее» состояние лица.
MOOD_TO_STATE = {
    "happy": SPEAK_HAPPY,
    "sad": SPEAK_SAD,
    "surprised": SPEAK_SURPRISED,
    "thinking": SPEAK_THINKING,
    "neutral": SPEAKING,
}


def state_for_mood(mood: str, story: bool = False) -> str:
    """Какое лицо показать для настроения очередного куска реплики."""
    if story and mood in ("neutral", "thinking"):
        return SPEAK_STORY
    return MOOD_TO_STATE.get(str(mood or "").strip().lower(), SPEAKING)


@dataclass
class FaceFrame:
    """Что показывать в этот кадр (решение «режиссёра»)."""
    eyes: str                      # текущий слой глаз
    eyes_from: str = ""            # предыдущий слой (для плавного перехода)
    eyes_mix: float = 1.0          # 0 — от «предыдущего», 1 — к «текущему»
    mouth: str = ""                # слой рта
    dy: int = 0                    # смещение лица вниз (кивок), пиксели
    state: str = IDLE

    def key(self) -> Tuple[str, str, str, int, int]:
        """Ключ кэша (переходы и кивок кэшировать нельзя — только «покой»)."""
        return (self.eyes_from, self.eyes, self.mouth,
                int(self.eyes_mix * 100), int(self.dy))


class FaceAnimator:
    """Режиссёр лица: по времени решает, какие слои показать.

    Использование:
        anim = FaceAnimator()
        anim.set_state(SPEAKING)
        for каждый кадр: frame = anim.tick(dt, level=громкость_0_100)
    """

    def __init__(self, seed: Optional[int] = None,
                 blink: bool = True, gaze: bool = True) -> None:
        self._rnd = random.Random(seed)
        self._blink_allowed = blink
        self._gaze_allowed = gaze

        self._state = IDLE
        self._cfg = STATES[IDLE]
        self._state_time = 0.0

        self._t = 0.0                 # общее время (для фазы рта)
        self._next_blink = 0.0
        self._blink_left = 0.0        # сколько ещё держать закрытые глаза

        self._next_gaze = 0.0
        self._gaze_left = 0.0
        self._gaze_eyes = ""

        self._next_nod = 0.0
        self._nod_left = 0.0
        self._nod_queue = 0          # сколько кивков ещё сделать
        self._nod_gap = 0.0          # пауза перед следующим кивком
        self._nod_delay = 0.0        # «моргнул → подождал → кивнул»
        self._silence = 0.0          # сколько длится тишина в речи
        self._was_loud = False       # была ли до тишины речь
        self._last_nod = -99.0       # время последнего кивка (остывание)

        self._eyes = self._cfg.eyes
        self._eyes_from = ""
        self._fade_left = 0.0

        # сценарий реакции (например, «удивилась → улыбнулась»)
        self._seq: list = []          # [[состояние, осталось секунд], ...]
        self._seq_return = IDLE       # куда вернуться после сценария

        self._schedule_blink(0.0)
        self._schedule_gaze(0.0)

    # -----------------------------------------------------
    # Состояние
    # -----------------------------------------------------
    def set_state(self, state: str) -> None:
        """Сменить эмоцию (неизвестная → покой)."""
        state = str(state or "").strip().lower()
        if state not in STATES or state == self._state:
            return
        self._state = state
        self._cfg = STATES[state]
        self._state_time = 0.0
        self._change_eyes(self._cfg.eyes)

    @property
    def state(self) -> str:
        return self._state

    @property
    def in_sequence(self) -> bool:
        """Сейчас проигрывается сценарий реакции."""
        return bool(self._seq)

    def play_sequence(self, steps, return_to: Optional[str] = None) -> None:
        """Проиграть сценарий: [(состояние, секунды), ...] и вернуться.

        Нужен для реакций вида «удивилась 1.5 с → одобрительно улыбнулась».
        Пока сценарий идёт, обычная смена состояний его не перебивает.
        """
        prepared = []
        for item in (steps or []):
            try:
                name, seconds = item
            except (TypeError, ValueError):
                continue
            name = str(name or "").strip().lower()
            if name not in STATES:
                continue
            try:
                seconds = float(seconds)
            except (TypeError, ValueError):
                continue
            if seconds > 0:
                prepared.append([name, seconds])
        if not prepared:
            return
        self._seq_return = return_to or (self._state if self._state else IDLE)
        self._seq = prepared
        self.set_state(prepared[0][0])
        self._seq[0][1] = prepared[0][1]

    def _change_eyes(self, eyes: str) -> None:
        """Сменить слой глаз с плавным переходом."""
        if eyes == self._eyes:
            return
        self._eyes_from = self._eyes
        self._eyes = eyes
        self._fade_left = EYES_FADE

    # -----------------------------------------------------
    # Планирование
    # -----------------------------------------------------
    def _schedule_blink(self, now: float) -> None:
        low, high = self._cfg.blink_range
        self._next_blink = now + self._rnd.uniform(low, high)

    def _schedule_gaze(self, now: float) -> None:
        self._next_gaze = now + self._rnd.uniform(GAZE_MIN, GAZE_MAX)

    def _queue_nods(self, count: int, delay: float = 0.0) -> None:
        """Запланировать кивки (после моргания или на паузе речи)."""
        if count <= 0:
            return
        self._nod_queue = min(4, self._nod_queue + int(count))
        if delay > 0:
            self._nod_delay = max(self._nod_delay, float(delay))

    # -----------------------------------------------------
    # Такт (вызывается каждый кадр)
    # -----------------------------------------------------
    def tick(self, dt: float, level: Optional[float] = None,
             speaking: Optional[bool] = None) -> FaceFrame:
        """Продвинуть анимацию на dt секунд и вернуть кадр.

        level    — громкость 0..100 (для движения рта);
        speaking — говорить ли сейчас (иначе рот спокоен).
        """
        dt = max(0.0, float(dt))
        self._t += dt
        self._state_time += dt

        # сценарий реакции важнее обычных переходов
        if self._seq:
            self._seq[0][1] -= dt
            while self._seq and self._seq[0][1] <= 0.0:
                self._seq.pop(0)
                if self._seq:
                    self.set_state(self._seq[0][0])
            if not self._seq:
                self.set_state(self._seq_return or IDLE)

        # короткие эмоции уходят сами: грусть → улыбка (наигранная),
        # остальные → покой
        if self._cfg.transient > 0 and self._state_time >= self._cfg.transient:
            target = self._cfg.transient_to or IDLE
            self.set_state(target)
            self._state_time = dt

        talk = self._cfg.talk and (speaking is not False)

        # ----- моргание -----
        if self._cfg.blink and self._blink_allowed and self._nod_left <= 0.0:
            if self._blink_left > 0.0:
                self._blink_left -= dt
                if self._blink_left <= 0.0:
                    self._change_eyes(self._gaze_eyes or self._cfg.eyes)
                    # моргнул → чуть позже кивнёт 1-2 раза (живой NPC)
                    if self._cfg.nod:
                        self._queue_nods(
                            self._rnd.randint(NOD_AFTER_BLINK_MIN, NOD_AFTER_BLINK_MAX),
                            delay=NOD_DELAY_AFTER_BLINK)
            elif self._t >= self._next_blink:
                # иногда «крепко зажмуривается» — это делает моргание живым
                shut = self._rnd.random() < BLINK_SHUT_CHANCE
                self._blink_left = BLINK_SHUT_DURATION if shut else BLINK_DURATION
                self._change_eyes("eyes_closed_shut" if shut else "eyes_closed")
                self._schedule_blink(self._t)

        # ----- блуждание взгляда (только если разрешено эмоцией) -----
        if self._cfg.gaze and self._gaze_allowed and self._blink_left <= 0.0:
            if self._gaze_left > 0.0:
                self._gaze_left -= dt
                if self._gaze_left <= 0.0:
                    self._gaze_eyes = ""
                    self._change_eyes(self._cfg.eyes)
            elif self._t >= self._next_gaze:
                self._gaze_eyes = "eyes_%s" % self._rnd.choice(
                    ("left", "right", "upstairs", "down"))
                self._gaze_left = GAZE_HOLD
                self._change_eyes(self._gaze_eyes)
                self._schedule_gaze(self._t)

        # ----- паузы в речи ученика: «услышала → кивнула» -----
        if self._cfg.nod and level is not None:
            if level > PAUSE_AFTER_LEVEL:
                self._was_loud = True
                self._silence = 0.0
            elif self._was_loud:
                self._silence += dt
                if (self._silence >= NOD_ON_PAUSE and self._nod_left <= 0.0
                        and self._t - self._last_nod >= NOD_COOLDOWN):
                    self._was_loud = False        # киваем один раз на паузу
                    self._silence = 0.0
                    self._queue_nods(1)

        # ----- кивок: лицо «клюёт» вниз внутри экрана -----
        dy = 0
        if self._cfg.nod:
            if self._nod_delay > 0.0:
                self._nod_delay = max(0.0, self._nod_delay - dt)
            elif self._nod_left <= 0.0 and self._nod_queue > 0:
                self._nod_left = NOD_DURATION
                self._nod_queue -= 1
                self._nod_gap = NOD_GAP
                self._last_nod = self._t
            elif self._nod_left <= 0.0 and self._nod_gap > 0.0:
                self._nod_gap = max(0.0, self._nod_gap - dt)
        if self._nod_left > 0.0:
            self._nod_left = max(0.0, self._nod_left - dt)
            progress = 1.0 - (self._nod_left / NOD_DURATION)
            # плавный «вниз-вверх»: синус даёт мягкий кивок без рывка
            dy = int(round(NOD_DEPTH * math.sin(math.pi * progress)))

        # ----- плавный переход между слоями глаз -----
        if self._fade_left > 0.0:
            self._fade_left = max(0.0, self._fade_left - dt)
            mix = 1.0 - (self._fade_left / EYES_FADE if EYES_FADE else 1.0)
        else:
            mix = 1.0
            self._eyes_from = ""

        mouth = self._mouth_layer(level, talk)
        return FaceFrame(eyes=self._eyes, eyes_from=self._eyes_from,
                         eyes_mix=mix, mouth=mouth, dy=dy, state=self._state)

    # -----------------------------------------------------
    def _mouth_layer(self, level: Optional[float], talk: bool) -> str:
        """Какой рот показать: застывший, смена формы или речь по громкости."""
        cfg = self._cfg
        if cfg.static_mouth:
            return cfg.static_mouth
        if cfg.mouth_cycle and not talk:
            index = int(self._t / MOUTH_SHAPE_PERIOD) % len(cfg.mouth_cycle)
            return cfg.mouth_cycle[index]
        if not talk or level is None:
            return cfg.mouth_closed
        amp = max(0.0, min(1.0, float(level) / 100.0))
        if amp < 0.08:                        # тишина/пауза — рот закрыт
            return cfg.mouth_closed
        phase = (self._t * MOUTH_RATE) % 1.0  # «слог»
        if amp < 0.38:                        # тихо — приоткрыт
            return cfg.mouth_half if phase < 0.55 else cfg.mouth_closed
        if phase < 0.45:                      # громко — широко
            return cfg.mouth_open or cfg.mouth_half
        if phase < 0.72:                      # спад
            return cfg.mouth_half
        return cfg.mouth_closed


# =========================================================
# Склейка слоёв в картинку
# =========================================================
class FaceRenderer:
    """Собирает картинку лица из слоёв (тело + глаза + рот) с кэшем."""

    def __init__(self, layers_dir: str, face_name: str = "face_empty.png") -> None:
        self.layers_dir = layers_dir
        self.face_name = face_name
        self._face = None
        self._cache: Dict[Tuple[str, str, int], object] = {}
        self._raw: Dict[str, object] = {}

    # ---------- загрузка ----------
    def _path(self, name: str) -> str:
        """Путь к слою: глаза и рты лежат в подпапках eyes/ и mouth/."""
        clean = name if name.endswith(".png") else name + ".png"
        for folder in ("eyes", "mouth", ""):
            candidate = os.path.join(self.layers_dir, folder, clean) if folder \
                else os.path.join(self.layers_dir, clean)
            if os.path.isfile(candidate):
                return candidate
        return ""

    def layer(self, name: str):
        """Загруженный слой (с кэшем). None, если файла нет."""
        if not name:
            return None
        if name in self._raw:
            return self._raw[name]
        path = self._path(name)
        image = None
        if path:
            try:
                from PIL import Image
                image = Image.open(path).convert("RGBA")
            except Exception as exc:                     # noqa: BLE001
                _log.warning("Лицо: слой %s не открылся (%s)", name, exc)
        self._raw[name] = image
        return image

    @property
    def face(self):
        """Тело робота (с пустым экраном)."""
        if self._face is None:
            self._face = self.layer(self.face_name)
        return self._face

    def available(self) -> bool:
        return self.face is not None

    # ---------- сборка ----------
    @staticmethod
    def _shift(layer, dy: int):
        """Сдвинуть слой вниз на dy пикселей (для кивка)."""
        if not dy:
            return layer
        from PIL import Image
        shifted = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        shifted.paste(layer, (0, int(dy)))
        return shifted

    def compose(self, frame: FaceFrame):
        """Собрать картинку кадра. Возвращает PIL.Image (RGBA) или None."""
        from PIL import Image

        body = self.face
        if body is None:
            return None

        eyes = self.layer(frame.eyes)
        mouth = self.layer(frame.mouth)
        eyes_from = self.layer(frame.eyes_from) if frame.eyes_from else None

        # плавный переход: смешиваем два слоя глаз
        if eyes is not None and eyes_from is not None and 0.0 < frame.eyes_mix < 1.0:
            try:
                eyes = Image.blend(eyes_from, eyes, frame.eyes_mix)
            except Exception:                            # noqa: BLE001
                pass

        if frame.dy:
            eyes = self._shift(eyes, frame.dy) if eyes is not None else None
            mouth = self._shift(mouth, frame.dy) if mouth is not None else None

        out = body.copy()
        if eyes is not None:
            out.alpha_composite(eyes)
        if mouth is not None:
            out.alpha_composite(mouth)
        return out

    def compose_cached(self, frame: FaceFrame):
        """То же, но с кэшем — только для «спокойных» кадров без перехода."""
        blended = bool(frame.eyes_from) and 0.0 < frame.eyes_mix < 1.0
        if blended:
            return self.compose(frame)          # переход — считаем каждый кадр
        key = (frame.eyes, frame.mouth, int(frame.dy))
        if key in self._cache:
            return self._cache[key]
        image = self.compose(frame)
        if image is not None:
            self._cache[key] = image
        return image

    def clear_cache(self) -> None:
        self._cache.clear()


def layer_names(layers_dir: str) -> Dict[str, List[str]]:
    """Что вообще есть в папке слоёв (для проверок и каталога)."""
    out: Dict[str, List[str]] = {"eyes": [], "mouth": []}
    for folder in ("eyes", "mouth"):
        path = os.path.join(layers_dir, folder)
        if not os.path.isdir(path):
            continue
        out[folder] = sorted(n for n in os.listdir(path) if n.endswith(".png"))
    return out
