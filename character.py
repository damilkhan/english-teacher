# -*- coding: utf-8 -*-
# =========================================================
# CHARACTER.PY — анимированный робот Джейн (лицо из слоёв)
# =========================================================
# Робот живёт в области чата (правый нижний угол) и «играет лицом»:
# глаза, рот, моргание, взгляд по сторонам, кивки, эмоции.
#
# Как устроено:
#   * Тело робота — face_empty.png (пустой экран), поверх накладываются
#     слои глаз и рта из assets/character/eyes и /mouth (character_face).
#   * «Режиссёр» (FaceAnimator) решает, ЧТО показать в каждый кадр;
#     кадр рисует FaceRenderer (Pillow) и превращает в картинку для Tk.
#   * Кадры считает daemon-поток: главный поток Tk свободен, окно не висит.
#   * ImageTk.PhotoImage создаётся ТОЛЬКО в главном потоке (требование Tk),
#     поэтому поток «заказывает» кадр, а главный его устанавливает.
#   * В главный поток зовём через dispatch (очередь приложения) — см. _ui().
#
# Состояния (см. character_face.STATES): idle, listening, thinking,
# speaking, happy, smile, sad, surprised, scorn, angry + «говорящие»
# варианты (speak_happy, speak_sad, ...).
#
# Всё на CPU: только Pillow + Tk.
# =========================================================

import os
import threading
import time

FRAME_INTERVAL = 1.0 / 18.0      # ~18 кадров в секунду (плавно и не грузит CPU)
DEFAULT_WIDTH = 300              # ширина робота в области чата, px
GAP = 10                         # отступ от правого нижнего угла, px

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARACTER_DIR = os.path.join(BASE_DIR, "assets", "character")
DEFAULT_IMAGE = os.path.join(CHARACTER_DIR, "face_empty.png")
FALLBACK_IMAGE = os.path.join(CHARACTER_DIR, "robot_base.png")

IDLE_STATE = "idle"
KNOWN_STATES = ("idle", "listening", "thinking", "speaking", "happy", "smile",
                "sad", "surprised", "scorn", "angry", "speak_happy",
                "speak_sad", "speak_surprised", "speak_thinking", "speak_story",
                "story_end")


class Character:
    """Робот-персонаж в области чата: лицо из слоёв + анимация."""

    def __init__(self, parent, image_path=None, width=DEFAULT_WIDTH, bg=None,
                 dispatch=None, layers_dir=None):
        self.parent = parent
        self.width = int(width)
        self.height = 0
        self.canvas = None
        self.available = False
        self._canvas_size = (self.width, self.height)
        self._dispatch = dispatch

        self._item = None
        self._photo = None
        self._frame_key = None       # ключ показанного кадра (чтобы не перерисовывать)
        self._image_cache = {}       # ключ → готовая картинка нужного размера
        self._photo_cache = {}       # ключ → готовый PhotoImage (без работы в Tk)
        self._frame_id = 0
        self._pending = False
        self._started = 0.0
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

        self._level = 0.0          # громкость 0..100 (для рта)
        self._speaking = None      # говорить ли сейчас (None — не важно)
        self._state = IDLE_STATE

        # --- лицо из слоёв ---
        self._renderer = None
        self._animator = None
        try:
            import character_face as face
            self._face_api = face
            self._renderer = face.FaceRenderer(layers_dir or CHARACTER_DIR)
            if self._renderer.available():
                self._animator = face.FaceAnimator()
                self.available = True
        except Exception as exc:                     # noqa: BLE001
            print("⚠️ Робот: слои лица не загрузились (%s)" % exc)
            self._renderer = None
            self._animator = None

        if not self.available:
            # запасной путь: одна картинка робота (как раньше)
            self._base = self._load_fallback(image_path)
            if self._base is None:
                print("ℹ️ Робот-персонаж не подключён: нет картинки")
                return
            self.available = True
            self.height = self._base.height

        self._build_canvas(bg)

    # -----------------------------------------------------
    # Загрузка (запасной путь)
    # -----------------------------------------------------
    def _load_fallback(self, path):
        """PNG → RGBA и масштаб до width (пропорции сохраняются)."""
        path = path or FALLBACK_IMAGE
        if not path or not os.path.exists(path):
            print("⚠️ Робот: нет картинки %s" % path)
            return None
        try:
            from PIL import Image
            im = Image.open(path).convert("RGBA")
        except Exception as exc:                     # noqa: BLE001
            print("⚠️ Робот: картинка не читается (%s)" % exc)
            return None
        src_w, src_h = im.size
        if src_w <= 0 or src_h <= 0:
            return None
        self.height = max(1, int(round(src_h * self.width / float(src_w))))
        return im.resize((self.width, self.height), Image.NEAREST)

    def _build_canvas(self, bg):
        """Canvas в правом нижнем углу области чата (поверх текста)."""
        import math
        import tkinter as tk
        if self.height <= 0 and self._renderer is not None:
            body = self._renderer.face
            if body is not None:
                self.height = int(round(body.height * self.width / float(body.width)))
        if bg is None:
            bg = self._parent_bg()
        # запас на «дыхание» и кивок, чтобы рисунок не обрезался краем Canvas
        cw = int(math.ceil(self.width * 1.02))
        ch = int(math.ceil(self.height * 1.02))
        self._canvas_size = (cw, ch)
        try:
            self.canvas = tk.Canvas(self.parent, width=cw, height=ch,
                                    highlightthickness=0, bd=0, bg=bg)
        except Exception as exc:                     # noqa: BLE001
            print("⚠️ Робот: Canvas не создался (%s)" % exc)
            self.canvas = None
            self.available = False
            return
        self.canvas.place(relx=1.0, rely=1.0, anchor="se", x=-GAP, y=-GAP)

    def _parent_bg(self):
        """Фон Canvas — как у области чата (Tk настоящей прозрачности не умеет)."""
        try:
            colour = self.parent.cget("fg_color")
        except Exception:                            # noqa: BLE001
            colour = None
        if isinstance(colour, (list, tuple)) and colour:
            colour = colour[0]
        if isinstance(colour, str) and colour and colour != "transparent":
            return colour
        try:
            import theme
            return theme.DARK["chat_bg"]
        except Exception:                            # noqa: BLE001
            return "#14161F"

    # -----------------------------------------------------
    # Публичный API (совместим с прежним)
    # -----------------------------------------------------
    @property
    def size(self):
        return (self.width, self.height)

    @property
    def reserve(self):
        cw, ch = self._canvas_size
        return (cw + GAP, ch + GAP)

    @property
    def state(self):
        """Текущее состояние (во время сценария — его собственное)."""
        animator = self._animator
        if animator is not None:
            return animator.state
        return self._state

    @property
    def animating(self):
        return self._thread is not None and self._thread.is_alive()

    def start_idle(self):
        """Запустить анимацию в daemon-потоке (повторный вызов — no-op)."""
        if not self.available or self.canvas is None:
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._started = time.monotonic()
        self._thread = threading.Thread(target=self._loop, name="character-face",
                                        daemon=True)
        self._thread.start()
        return True

    def stop_idle(self):
        """Остановить анимацию."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._thread = None

    def set_state(self, state):
        """Сменить эмоцию: idle/listening/thinking/speaking/happy/...

        ВАЖНО: пока идёт сценарий реакции («удивилась → улыбнулась»), обычная
        смена состояния НЕ применяется — иначе события (настроение текста,
        «думает») перебивали бы реакцию на середине.
        """
        name = str(state or "").strip().lower()
        if name not in KNOWN_STATES:
            return False
        animator = self._animator
        if animator is not None:
            if animator.in_sequence:
                return False                        # сценарий важнее
            try:
                animator.set_state(name)
            except Exception:                        # noqa: BLE001
                return False
            self._state = animator.state
            return True
        self._state = name
        return True

    def play_sequence(self, steps, return_to=None):
        """Проиграть сценарий реакций: [(состояние, секунды), ...]."""
        animator = self._animator
        if animator is None:
            return False
        try:
            animator.play_sequence(steps, return_to=return_to or self._state)
        except Exception as exc:                     # noqa: BLE001
            print("⚠️ Робот: сценарий не запустился (%s)" % exc)
            return False
        return True

    def set_level(self, level, speaking=None):
        """Громкость речи 0..100 (для движения рта)."""
        try:
            self._level = max(0.0, min(100.0, float(level)))
        except (TypeError, ValueError):
            self._level = 0.0
        if speaking is not None:
            self._speaking = bool(speaking)

    def apply_theme(self, bg):
        if self.canvas is not None:
            try:
                self.canvas.configure(bg=bg)
            except Exception:                        # noqa: BLE001
                pass

    def destroy(self):
        self.stop_idle()
        if self.canvas is not None:
            try:
                self.canvas.destroy()
            except Exception:                        # noqa: BLE001
                pass
            self.canvas = None
        self.available = False

    # -----------------------------------------------------
    # Анимация
    # -----------------------------------------------------
    def _loop(self):
        """Фоновый поток: считает кадры и «заказывает» их в главный поток.

        ВАЖНО: шаг времени считаем по РЕАЛЬНЫМ часам, а не «по кадру».
        Кадры приходят реже номинала (очередь диспетчера добавляет задержку),
        и при фиксированном шаге анимация шла бы вдвое медленнее, чем нужно:
        «1.5 секунды удивления» превращались бы в три.
        """
        last = time.monotonic()
        while not self._stop.is_set():
            if not self._pending:
                now = time.monotonic()
                dt = min(1.0, max(0.004, now - last))
                last = now
                self._pending = True
                self._ui(self._tick, dt)
            self._stop.wait(FRAME_INTERVAL)

    def _tick(self, dt):
        """Главный поток: получить решение «режиссёра» и показать кадр."""
        self._pending = False
        if self.canvas is None:
            return
        try:
            self._frame_id += 1
            image, key = self._build_frame(dt)
            if image is None:
                return
            if key is not None and key == self._frame_key and self._item is not None:
                return                    # кадр не изменился — перерисовка не нужна
            self._frame_key = key
            # PhotoImage тоже кэшируем: его создание — самая дорогая часть
            # кадра (несколько миллисекунд), а набор кадров у робота небольшой
            photo = self._photo_cache.get(key)
            if photo is None:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(image, master=self.canvas)
                if len(self._photo_cache) > 400:
                    self._photo_cache.clear()
                self._photo_cache[key] = photo
            self._photo = photo
            if self._item is None:
                cx = self._canvas_size[0] / 2.0
                cy = self._canvas_size[1] / 2.0
                self._item = self.canvas.create_image(cx, cy, anchor="center",
                                                      image=self._photo)
            else:
                self.canvas.itemconfigure(self._item, image=self._photo)
        except Exception as exc:                     # noqa: BLE001
            print("⚠️ Робот: кадр не показан (%s)" % exc)

    def _build_frame(self, dt):
        """Собрать картинку кадра под размер окна. Возвращает (картинка, ключ).

        Ключ — «что именно нарисовано» (глаза, рот, сдвиг кивка, фаза перехода).
        Если ключ тот же, что в прошлом кадре, интерфейс картинку не меняет:
        это в разы дешевле, чем заново склеивать слои и создавать PhotoImage.
        """
        from PIL import Image
        if self._animator is None or self._renderer is None:
            return self._fallback_frame(), None
        frame = self._animator.tick(dt, level=self._level, speaking=self._speaking)
        self._state = frame.state
        key = frame.key()
        cached = self._image_cache.get(key)
        if cached is not None:
            return cached, key
        image = self._renderer.compose_cached(frame)
        if image is None:
            return self._fallback_frame(), None
        resized = image.resize((self.width, self.height), Image.NEAREST)
        # кэш ограничиваем: состояний немного, но фазы переходов добавляют ключи
        if len(self._image_cache) > 160:
            self._image_cache.clear()
        self._image_cache[key] = resized
        return resized, key

    def _fallback_frame(self):
        """Запасной путь: одна картинка (робот без лица)."""
        base = getattr(self, "_base", None)
        if base is None:
            return None
        # лёгкое «дыхание» по времени, чтобы робот не был совсем статичным
        import math
        phase = (time.monotonic() - (self._started or time.monotonic())) % 2.0
        scale = 1.0 + 0.005 * math.sin(2.0 * math.pi * phase / 2.0)
        from PIL import Image
        w = max(1, int(round(self.width * scale)))
        h = max(1, int(round(self.height * scale)))
        return base.resize((w, h), Image.NEAREST)

    def _ui(self, fn, *args):
        """Выполнить fn в главном потоке Tk."""
        if self._dispatch is not None:
            try:
                self._dispatch(lambda: fn(*args))
                return
            except Exception:                        # noqa: BLE001
                pass
        canvas = self.canvas
        if canvas is None:
            return
        try:
            canvas.after(0, lambda: fn(*args))
        except Exception:                            # noqa: BLE001
            pass
