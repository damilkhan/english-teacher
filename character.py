# -*- coding: utf-8 -*-
# =========================================================
# CHARACTER.PY — анимированный робот-персонаж Джейн (Этап 1)
# =========================================================
# Робот живёт в области чата (правый нижний угол) и «дышит»: картинка
# пульсирует на ±0.5 % с периодом 2 секунды (30 кадров в секунду).
#
# Почему устроено именно так:
#   • кадры считает daemon-поток (масштабирование Pillow) — главный поток
#     Tk свободен, окно не подвисает;
#   • кадры считаются ЗАРАНЕЕ (IDLE_PERIOD*IDLE_FPS картинок), а в цикле
#     меняются одной строкой — canvas.itemconfigure(item, image=...);
#   • ImageTk.PhotoImage создаётся в главном потоке (ImageTk требует Tk),
#     тяжёлый ресайз остаётся в фоне;
#   • в главный поток зовём через dispatch (очередь приложения) — см. _ui().
#
# ВАЖНО про _ui(): классический приём «canvas.after(0, fn) из воркера»
# работает ТОЛЬКО когда запущен mainloop; без него tkinter падает с
# «main thread is not in main loop» (та же грабля, из-за которой в проекте
# появился controllers/dispatcher.py). Поэтому основной путь — dispatch из
# приложения (queue), а canvas.after(0, ...) оставлен запасным: он нужен,
# если Character используют без диспетчера, в живом окне.
#
# Состояния: работает только «idle». listening / thinking / speaking /
# happy / sad — заглушки: пишут в лог и НИЧЕГО не меняют (мимика и жесты —
# следующий этап). Никакой нейросети и VRAM: только Pillow + Tk, всё на CPU.
# =========================================================

import math
import os
import threading
import time

# ---------------------------------------------------------
# Параметры idle-анимации
# ---------------------------------------------------------
IDLE_PERIOD = 2.0          # секунды на полный цикл «дыхания»
IDLE_FPS = 30              # кадров в секунду
PULSE = 0.005              # амплитуда ±0.5 % — лёгкое дыхание, не «желе»
DEFAULT_WIDTH = 300        # ширина робота в области чата, px
GAP = 10                   # отступ от правого нижнего угла области чата, px

DEFAULT_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "character", "robot_base.png")

IDLE_STATE = "idle"
KNOWN_STATES = ("idle", "listening", "thinking", "speaking", "happy", "sad")


class Character:
    """Робот-персонаж в области чата: картинка на Canvas + idle-анимация."""

    def __init__(self, parent, image_path=None, width=DEFAULT_WIDTH, bg=None,
                 dispatch=None):
        self.parent = parent
        self.width = int(width)
        self.height = 0
        self.canvas = None
        self.available = False          # True, если картинка загрузилась
        self._canvas_size = (self.width, self.height)
        self._dispatch = dispatch       # queue-мост в главный поток (или None)

        self._item = None               # id картинки на Canvas
        self._pil_frames = []           # кадры (PIL) — считаются в фоне
        self._photos = []               # кадры (PhotoImage) — только главный поток
        self._frame = 0                 # показанный кадр
        self._pending = False           # кадр уже заказан в главный поток
        self._started = 0.0             # старт фазы «дыхания»
        self._thread = None
        self._stop = threading.Event()  # флаг остановки анимации
        self._lock = threading.Lock()
        self._state = IDLE_STATE

        self._base = self._load(image_path or DEFAULT_IMAGE)
        if self._base is None:
            # Робот — украшение: без картинки чат работает как раньше.
            print("ℹ️ Робот-персонаж не подключён: нет картинки")
            return
        self.available = True
        self._build_canvas(bg)

    # -----------------------------------------------------
    # Загрузка картинки и Canvas
    # -----------------------------------------------------
    def _load(self, path):
        """PNG → RGBA и масштаб до width (пропорции сохраняются)."""
        if not path or not os.path.exists(path):
            print("⚠️ Робот: нет картинки %s" % path)
            return None
        try:
            from PIL import Image
            im = Image.open(path).convert("RGBA")
        except Exception as exc:
            print("⚠️ Робот: картинка не читается (%s)" % exc)
            return None
        src_w, src_h = im.size
        if src_w <= 0 or src_h <= 0:
            return None
        self.height = max(1, int(round(src_h * self.width / float(src_w))))
        return im.resize((self.width, self.height), Image.LANCZOS)

    def _build_canvas(self, bg):
        """Canvas в правом нижнем углу области чата (поверх текста)."""
        import tkinter as tk
        if bg is None:
            bg = self._parent_bg()
        # Кадр «вдоха» на пару пикселей ШИРЕ номинала, а Tk обрезает рисунок
        # по краям Canvas. Поэтому сам Canvas чуть больше номинала — иначе
        # пульсация срезалась бы по краю.
        cw = int(math.ceil(self.width * (1.0 + PULSE)))
        ch = int(math.ceil(self.height * (1.0 + PULSE)))
        self._canvas_size = (cw, ch)
        try:
            self.canvas = tk.Canvas(self.parent, width=cw, height=ch,
                                    highlightthickness=0, bd=0, bg=bg)
        except Exception as exc:
            print("⚠️ Робот: Canvas не создался (%s)" % exc)
            self.canvas = None
            self.available = False
            return
        # прижат к правому нижнему углу области чата с отступом GAP
        self.canvas.place(relx=1.0, rely=1.0, anchor="se", x=-GAP, y=-GAP)

    def _parent_bg(self):
        """Фон Canvas — как у области чата (Tk настоящей прозрачности не умеет)."""
        try:
            colour = self.parent.cget("fg_color")
        except Exception:
            colour = None
        if isinstance(colour, (list, tuple)) and colour:
            colour = colour[0]
        if isinstance(colour, str) and colour and colour != "transparent":
            return colour
        try:
            import theme
            return theme.DARK["chat_bg"]
        except Exception:
            return "#14161F"

    # -----------------------------------------------------
    # Публичный API
    # -----------------------------------------------------
    @property
    def size(self):
        """Размер робота (ширина, высота) при масштабе 1.0."""
        return (self.width, self.height)

    @property
    def reserve(self):
        """Сколько места справа/снизу нужно освободить под робота, px.

        Это размер Canvas (на 2 px больше номинала — запас на «вдох») плюс
        отступ GAP. По нему область чата отодвигает текст и полосу прокрутки.
        """
        cw, ch = self._canvas_size
        return (cw + GAP, ch + GAP)

    @property
    def state(self):
        return self._state

    @property
    def animating(self):
        """True, если поток анимации сейчас живой."""
        return self._thread is not None and self._thread.is_alive()

    def start_idle(self):
        """Запустить idle-анимацию в daemon-потоке (повторный вызов — no-op)."""
        if not self.available or self.canvas is None:
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._idle_loop,
                                        name="character-idle", daemon=True)
        self._thread.start()
        return True

    def stop_idle(self):
        """Остановить анимацию (флаг + join с небольшим таймаутом)."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._thread = None

    def set_state(self, state):
        """Сменить состояние персонажа. Пока работает только idle.

        Остальные состояния — заглушки: сообщаем в лог и НИЧЕГО не меняем
        (анимация продолжает «дышать»). Мимика/жесты — следующий этап.
        """
        name = str(state or "").strip().lower()
        if name in ("", IDLE_STATE):
            return
        if name in KNOWN_STATES:
            print("ℹ️ Робот: состояние «%s» пока не реализовано — остаётся idle"
                  % name)
            return
        print("⚠️ Робот: неизвестное состояние %r" % (state,))

    def apply_theme(self, bg):
        """Перекрасить фон Canvas при смене темы."""
        if self.canvas is not None:
            try:
                self.canvas.configure(bg=bg)
            except Exception:
                pass

    def destroy(self):
        """Остановить анимацию и убрать Canvas."""
        self.stop_idle()
        if self.canvas is not None:
            try:
                self.canvas.destroy()
            except Exception:
                pass
            self.canvas = None
        self.available = False

    # -----------------------------------------------------
    # Анимация
    # -----------------------------------------------------
    def _idle_loop(self):
        """Фоновый поток: строит кадры и «тикает» в главный поток.

        Сам кадр выбирается по часам в момент отрисовки (см. _tick), поэтому
        дыхание не заикается и не отстаёт, даже если главный поток занят.
        """
        frames = self._build_frames()
        if not frames:
            return
        with self._lock:
            self._pil_frames = frames
        self._ui(self._install_frames)      # PhotoImage — только главный поток

        delay = 1.0 / float(IDLE_FPS)
        while not self._stop.is_set():
            # не копим очередь: кадр заказываем, только если предыдущий уже
            # отрисован (главный поток мог притормозить на перерисовке)
            if not self._pending:
                self._pending = True
                self._ui(self._tick)
            self._stop.wait(delay)

    def _build_frames(self):
        """Кадры «дыхания»: scale = 1 ± PULSE, период IDLE_PERIOD."""
        base = self._base
        if base is None:
            return []
        from PIL import Image
        count = max(2, int(round(IDLE_PERIOD * IDLE_FPS)))
        frames = []
        for i in range(count):
            angle = 2.0 * math.pi * (i / float(count))
            scale = 1.0 + PULSE * math.sin(angle)
            w = max(1, int(round(self.width * scale)))
            h = max(1, int(round(self.height * scale)))
            try:
                frames.append(base.resize((w, h), Image.LANCZOS))
            except Exception as exc:
                print("⚠️ Робот: кадр не построен (%s)" % exc)
                return []
        return frames

    def _ui(self, fn):
        """Выполнить fn в главном потоке Tk (см. шапку файла)."""
        if self._dispatch is not None:
            try:
                self._dispatch(fn)      # очередь приложения — работает всегда
                return
            except Exception:
                pass
        canvas = self.canvas
        if canvas is None:
            return
        try:
            canvas.after(0, fn)         # запасной путь: живёт только с mainloop
        except Exception:
            pass        # окно уже закрыто — молча выходим

    def _install_frames(self):
        """Создаёт PhotoImage-кадры (главный поток) и рисует первый."""
        canvas = self.canvas
        if canvas is None:
            return
        try:
            from PIL import ImageTk
        except Exception as exc:
            print("⚠️ Робот: ImageTk недоступен (%s)" % exc)
            return
        with self._lock:
            images = list(self._pil_frames)
        photos = []
        for im in images:
            try:
                photos.append(ImageTk.PhotoImage(im, master=canvas))
            except Exception as exc:
                print("⚠️ Робот: кадр не подготовлен (%s)" % exc)
                return
        if not photos:
            return
        # держим ссылки на PhotoImage: без них Tk «потеряет» картинку
        self._photos = photos
        cx = self._canvas_size[0] / 2.0
        cy = self._canvas_size[1] / 2.0
        try:
            if self._item is None:
                self._item = canvas.create_image(cx, cy, anchor="center",
                                                 image=photos[0])
            else:
                canvas.itemconfigure(self._item, image=photos[0])
        except Exception:
            self._item = None
            return
        self._frame = 0
        self._started = time.monotonic()    # с этого момента считаем фазу

    def _tick(self):
        """Показать кадр по ТЕКУЩЕМУ времени (вызывается в главном потоке)."""
        self._pending = False
        if not self._photos or self._item is None:
            return
        if self._started <= 0.0:
            self._started = time.monotonic()
        phase = (time.monotonic() - self._started) % IDLE_PERIOD
        count = len(self._photos)
        self._show(int(phase / IDLE_PERIOD * count) % count)

    def _show(self, index):
        """Показать кадр index (только главный поток)."""
        if not self._photos or self._item is None:
            return
        index %= len(self._photos)
        if index == self._frame:
            return
        try:
            self.canvas.itemconfigure(self._item, image=self._photos[index])
            self._frame = index
        except Exception:
            pass

