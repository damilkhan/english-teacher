# -*- coding: utf-8 -*-
# =========================================================
# UI/APP.PY — сборка окна English Teacher
# =========================================================
# Здесь только «клей»: создать виджеты, связать их с контроллерами,
# обновить интерфейс. Логика — в controllers/ и модулях верхнего уровня.
#
# Раскладка после редизайна:
#   фон окна — вертикальный градиент (рисуется на tk.Canvas полосками);
#   карточки («левая колонка» и «настройки») лежат на нём с отступами,
#   поэтому градиент виден по краям и в зазоре между колонками;
#   сверху карточки — градиентная шапка с заголовком и бейджем статуса.
#
# Раскладка делается через place(), потому что pack не умеет «парящие»
# карточки на градиенте. Размеры пересчитываются в _layout().
# =========================================================

import threading
import tkinter as tk

import customtkinter as ctk

import audio_vad
import commands
import config
import profile_store
import stt_engine
import theme
import tts
from controllers.chat_controller import ChatController
from controllers.dispatcher import Dispatcher
from controllers.recording_controller import RecordingController
from controllers.server_monitor import ServerMonitor
from llm_client import LLMClient
from ui import gradient
from ui.panels.settings_panel import SettingsPanel
from ui.widgets.chat_view import ChatView
from ui.widgets.control_bar import ControlBar
from ui.widgets.input_bar import InputBar
from ui.widgets.visualizer import AudioVisualizer

# --- состояние сервера → текст и цвет бейджа ---
STATUS_TEXT = {
    "ready": "● Готов",
    "loading": "● Модель загружается…",
    "offline": "● Сервер не запущен",
}
STATUS_COLOR = {"ready": "ok", "loading": "warn", "offline": "err"}

GREETING = ("Джейн",
            "Привет! Я твой преподаватель английского.\n"
            "Я буду запоминать твои ошибки и подстраивать уроки под тебя.")
NEW_PROFILE_NOTE = "📊 Создан новый профиль ученика. Я буду запоминать твой прогресс!"
NOT_READY_LOADING = "⏳ Модель ещё загружается — подожди несколько секунд и попробуй снова."
NOT_READY_OFFLINE = "❌ LLM-сервер не отвечает. Подробности в logs\\llama-server.log"

HERO_HEIGHT = 92
PANEL_WIDTH = 288
REDRAW_DELAY_MS = 90


class EnglishTeacherApp:
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.current_theme = config.DEFAULT_THEME
        self.palette = theme.palette(self.current_theme)
        self.mode = config.DEFAULT_MODE
        self.current_lang = "en"
        self.panel_visible = False
        self.busy = False
        self.server_state = "offline"
        self.server_ready = False

        # ---------- окно ----------
        self.window = ctk.CTk()
        self.window.title("English Teacher — Jane")
        self.window.geometry("1160x780")
        self.window.minsize(940, 660)
        self.window.configure(fg_color=self.palette["window"])

        # шрифты подбираем, когда окно уже есть (нужен список семейств системы)
        theme.resolve_fonts(self.window)

        # ---------- фон: градиент на Canvas ----------
        self._bg_job = None
        self._hero_cache = (None, None)
        self.base = tk.Canvas(self.window, highlightthickness=0, bd=0,
                              bg=self.palette["grad_top"])
        self.base.pack(fill="both", expand=True)
        self.base.bind("<Configure>", self._on_base_resize)

        # ---------- передача вызовов в главный поток ----------
        self.dispatcher = Dispatcher(schedule=self.window.after,
                                    cancel=self.window.after_cancel)
        self.dispatcher.start()

        # ---------- железо и сеть ----------
        self.vad = audio_vad.AudioVAD()
        self.stt = stt_engine.STTEngine()
        self.llm = LLMClient()

        # ---------- контроллеры ----------
        self.chat = ChatController(llm=self.llm, dispatch=self._dispatch,
                                   mode=self.mode, lang=self.current_lang)
        self.chat.on_message = self.add_message
        self.chat.on_status = self._set_status
        self.chat.on_busy = self._set_busy
        self.chat.on_response = self._on_response

        self.recorder = RecordingController(
            vad=self.vad, stt=self.stt, dispatch=self._dispatch,
            on_status=self._set_status,
            on_recording_changed=self._on_recording_changed,
            on_recognized=self._on_recognized,
        )

        # ---------- интерфейс ----------
        self._build_ui()

        self.monitor = ServerMonitor(
            on_state=self._on_server_state,
            schedule=self.window.after,
            cancel=self.window.after_cancel,
        )

        # ---------- старт ----------
        _, created = profile_store.ensure_profile()
        if created:
            self.add_message("Джейн", NEW_PROFILE_NOTE)
        self.check_server()
        self.monitor.start()
        self.window.after(60, self._redraw)     # первая отрисовка после раскладки

    # =====================================================
    # Сборка интерфейса
    # =====================================================
    def _build_ui(self):
        p = self.palette

        # ---------- карточка «чат» ----------
        self.left_frame = ctk.CTkFrame(self.base, fg_color=p["surface"],
                                       corner_radius=theme.R["card"],
                                       border_width=1, border_color=p["border"])
        self.visualizer = AudioVisualizer(self.left_frame, p, height=30, bars=30)
        self.chat_view = ChatView(self.left_frame, p, greeting=GREETING)
        self.input_bar = InputBar(self.left_frame, p, on_send=self.send_text)
        self.control_bar = ControlBar(self.left_frame, p,
                                      on_record=self.toggle_recording,
                                      on_settings=self.open_panel,
                                      on_clear=self.clear_chat)

        self._build_hero()

        # порядок упаковки = порядок сверху вниз
        self.hero.pack(fill="x", padx=theme.CARD_PAD, pady=(theme.CARD_PAD, 8))
        self.visualizer.pack(fill="x", padx=theme.CARD_PAD + 4, pady=(0, 6))
        self.chat_view.pack(fill="both", expand=True, padx=theme.CARD_PAD, pady=(0, 10))
        self.input_bar.pack(fill="x", padx=theme.CARD_PAD, pady=(0, 8))
        self.control_bar.pack(fill="x", padx=theme.CARD_PAD, pady=(0, theme.CARD_PAD))

        # ---------- карточка «настройки» (появляется по кнопке) ----------
        self.right_panel = SettingsPanel(self.base, p,
                                         mode=self.mode, theme_name=self.current_theme,
                                         on_save=self.save_settings, on_close=self.close_panel)

    def _build_hero(self):
        """Градиентная шапка: картинка-фон + тексты поверх неё."""
        p = self.palette
        self.hero = ctk.CTkFrame(self.left_frame, fg_color=p["surface"],
                                 corner_radius=theme.R["card"], height=HERO_HEIGHT)
        self.hero.pack_propagate(False)

        # фон-градиент шапки (создаём первым → он под текстами)
        self.hero_bg = ctk.CTkLabel(self.hero, text="", fg_color="transparent")
        self.hero_bg.place(x=0, y=0, relwidth=1, relheight=1)

        self.title_label = ctk.CTkLabel(self.hero, text="🎙️  ИИ-ПРЕПОДАВАТЕЛЬ",
                                        font=theme.FONT_TITLE, text_color="#FFFFFF")
        self.title_label.place(x=22, y=16)

        self.subtitle_label = ctk.CTkLabel(self.hero,
                                          text="Джейн · локальный преподаватель английского",
                                          font=theme.FONT_SUBTITLE, text_color="#DAD3FF")
        self.subtitle_label.place(x=24, y=50)

        self.status_badge = ctk.CTkLabel(self.hero, text="● Проверяю сервер…",
                                         font=theme.FONT_SMALL,
                                         text_color=p["muted"],
                                         fg_color=p["muted_soft"],
                                         corner_radius=theme.R["pill"],
                                         padx=12, pady=5)
        self.status_badge.place(relx=1.0, rely=0.5, x=-18, anchor="e")

    # =====================================================
    # Фон-градиент и раскладка
    # =====================================================
    def _on_base_resize(self, _event=None):
        """При изменении окна перерисовываем фон (с небольшой задержкой)."""
        if self._bg_job is not None:
            try:
                self.window.after_cancel(self._bg_job)
            except Exception:
                pass
        self._bg_job = self.window.after(REDRAW_DELAY_MS, self._redraw)

    def _redraw(self):
        self._bg_job = None
        w = self.base.winfo_width()
        h = self.base.winfo_height()
        if w < 50 or h < 50:
            return
        try:
            gradient.draw_vertical(self.base, w, h,
                                   self.palette["grad_top"], self.palette["grad_bottom"])
        except Exception as exc:
            print(f"⚠️ Не удалось нарисовать фон: {exc}")
        self._layout(w, h)

    def _layout(self, w=None, h=None):
        """Расставляет карточки: слева чат, справа настройки (если открыты)."""
        w = w or self.base.winfo_width()
        h = h or self.base.winfo_height()
        if w < 50 or h < 50:
            return

        pad, gap = theme.PAGE_PAD, theme.GAP
        inner_h = max(260, h - 2 * pad)
        right_w = (PANEL_WIDTH + gap) if self.panel_visible else 0
        left_w = max(320, w - 2 * pad - right_w)

        # customtkinter запрещает передавать width/height в place(),
        # поэтому размеры задаём относительными долями (это он разрешает).
        self.left_frame.place(x=pad, y=pad,
                              relwidth=left_w / float(w), relheight=inner_h / float(h))
        if self.panel_visible:
            self.right_panel.place(x=w - pad - PANEL_WIDTH, y=pad,
                                   relwidth=PANEL_WIDTH / float(w),
                                   relheight=inner_h / float(h))

        self._update_hero(max(160, left_w - 2 * theme.CARD_PAD))

    def _update_hero(self, width):
        """Градиент шапки пересобираем только при смене ширины или темы."""
        key = (int(width), self.current_theme)
        if self._hero_cache[0] == key:
            return
        try:
            p = self.palette
            img = gradient.hero(width, HERO_HEIGHT, p["hero_a"], p["hero_b"],
                                radius=theme.R["card"], bg=p["surface"])
            cimg = ctk.CTkImage(light_image=img, dark_image=img, size=(width, HERO_HEIGHT))
        except Exception as exc:
            print(f"⚠️ Не удалось собрать шапку: {exc}")
            return
        self._hero_cache = (key, cimg)          # держим ссылку, иначе картинка пропадёт
        try:
            self.hero_bg.configure(image=cimg)
        except Exception as exc:
            print(f"⚠️ Шапка не обновилась: {exc}")

    # =====================================================
    # Мостик «фон → главный поток»
    # =====================================================
    def _dispatch(self, fn):
        """Выполнить fn в главном потоке Tk (виджеты из чужих потоков трогать нельзя)."""
        self.dispatcher.dispatch(fn)

    # =====================================================
    # Обратная связь от контроллеров
    # =====================================================
    def add_message(self, sender, text):
        self.chat_view.add_message(sender, text)

    def _set_status(self, text, color_key="ok"):
        """Бейдж-«пилюля»: цвет текста и мягкая подложка по состоянию."""
        p = self.palette
        self.status_badge.configure(
            text=text,
            text_color=p.get(color_key, p["ok"]),
            fg_color=p.get(color_key + "_soft", p["muted_soft"]),
        )

    def _set_busy(self, busy):
        self.busy = busy
        self.input_bar.set_busy(busy)

    def _on_response(self, user_text, response):
        """Ответ получен: озвучиваем и гасим эквалайзер."""
        self._say(response)
        self.visualizer.reset()

    @staticmethod
    def _say(text):
        """Озвучка в фоне — окно ждать не должно."""
        if text:
            threading.Thread(target=tts.speak, args=(text,), daemon=True).start()

    def _on_recording_changed(self, recording):
        self.control_bar.set_recording(recording)

    def _on_recognized(self, text, lang):
        self.current_lang = lang
        self.chat.set_language(lang)
        self.add_message("Вы (голос)", text)
        self._handle_text(text)

    def _on_server_state(self, state, message):
        self.server_state = state
        self.server_ready = (state == "ready")
        if self.busy:                       # не сбиваем «Думает…»/«Распознаю…»
            return state
        self._set_status(STATUS_TEXT.get(state, STATUS_TEXT["offline"]),
                         STATUS_COLOR.get(state, "err"))
        return state

    # =====================================================
    # Действия пользователя
    # =====================================================
    def send_text(self):
        text = self.input_bar.get_text()
        if not text:
            return
        self.input_bar.clear_text()
        self.add_message("Вы", text)
        self._handle_text(text)

    def _handle_text(self, text):
        """Ввод пользователя — текстом или голосом (разницы нет).

        Сначала проверяем команду смены режима («урок», «перерыв»…):
        её выполняем локально, к модели не ходим и сервер не требуем.
        """
        mode = commands.parse_mode_command(text)
        if mode is not None:
            changed = (mode != self.mode)
            self._switch_mode(mode)
            if changed:
                self._say(commands.GREETINGS.get(mode))
            return

        if not self._require_server():
            return
        self.chat.send(text)

    def _require_server(self):
        """True, если сервер готов. Иначе объясняем причину в чате."""
        if self.server_ready:
            return True
        state = self.check_server()
        self.add_message("Джейн", NOT_READY_LOADING if state == "loading" else NOT_READY_OFFLINE)
        return False

    def toggle_recording(self):
        self.recorder.toggle()

    def clear_chat(self):
        self.chat_view.clear()
        self.chat.clear_history()

    def open_panel(self):
        if not self.panel_visible:
            self.panel_visible = True
            self._layout()

    def close_panel(self):
        if self.panel_visible:
            self.panel_visible = False
            self.right_panel.place_forget()
            self._layout()

    def save_settings(self):
        self._switch_mode(self.right_panel.get_mode())

        new_theme = self.right_panel.get_theme()
        if new_theme != self.current_theme:
            self.current_theme = new_theme
            self.palette = theme.palette(new_theme)
            ctk.set_appearance_mode(new_theme)
            self._apply_theme()

        self.close_panel()

    def _switch_mode(self, mode):
        """Единая точка смены режима: панель настроек и голосовые команды.

        Раньше переключение жило только в консольной версии
        (profile_manager.switch_to_teacher/friend), теперь — здесь.
        """
        self.mode = mode
        self.chat.set_mode(mode)
        self.right_panel.set_values(mode=mode)
        self.add_message("Джейн", f"⚙️ Режим изменён на {commands.MODE_LABELS.get(mode, mode)}")

    # =====================================================
    # Тема
    # =====================================================
    def _apply_theme(self):
        """Одна точка смены темы вместо двух копий if/else с configure()."""
        p = self.palette
        self.window.configure(fg_color=p["window"])
        self.base.configure(bg=p["grad_top"])
        self.left_frame.configure(fg_color=p["surface"], border_color=p["border"])
        self.hero.configure(fg_color=p["surface"])

        self._hero_cache = (None, None)          # шапку пересобрать под новую палитру
        self.visualizer.apply_theme(p)
        self.chat_view.apply_theme(p)
        self.input_bar.apply_theme(p)
        self.control_bar.apply_theme(p)
        self.right_panel.apply_theme(p)

        self._on_server_state(self.server_state, "")
        self._redraw()                            # фон + шапка + раскладка

    # =====================================================
    # Сервер и жизненный цикл
    # =====================================================
    def check_server(self):
        return self.monitor.check_now()

    def run(self):
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.window.mainloop()

    def on_closing(self):
        for stopper in (self.monitor.stop, self.dispatcher.stop):
            try:
                stopper()
            except Exception:
                pass
        if self.recorder.is_recording:
            self.recorder.stop()
        self.window.destroy()
