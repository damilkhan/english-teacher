# -*- coding: utf-8 -*-
# =========================================================
# UI/APP.PY — сборка окна English Teacher
# =========================================================
# Здесь только «клей»: создать виджеты, связать их с контроллерами,
# обновить интерфейс. Никакой сетевой логики, промптов и работы
# с файлом профиля — всё это в controllers/ и модулях верхнего уровня.
#
# Раскладка (как было):
#   левая  колонка — заголовок, визуализатор, чат, поле ввода, кнопки
#   правая колонка — настройки (режим, тема), выезжает по кнопке
# =========================================================

import threading

import customtkinter as ctk

import audio_vad
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
from ui.panels.settings_panel import SettingsPanel
from ui.widgets.chat_view import ChatView
from ui.widgets.control_bar import ControlBar
from ui.widgets.input_bar import InputBar
from ui.widgets.visualizer import AudioVisualizer

# Состояние сервера → текст и цвет бейджа
STATUS_TEXT = {
    "ready": "● Готов",
    "loading": "● Модель загружается…",
    "offline": "● Сервер не запущен",
}
STATUS_COLOR = {"ready": "ok", "loading": "warn", "offline": "err"}

NEW_PROFILE_NOTE = "📊 Создан новый профиль ученика. Я буду запоминать твой прогресс!"
NOT_READY_LOADING = "⏳ Модель ещё загружается — подожди несколько секунд и попробуй снова."
NOT_READY_OFFLINE = "❌ LLM-сервер не отвечает. Подробности в logs\\llama-server.log"
MODE_LABELS = {"lesson": "Урок", "free": "Свободное общение"}


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
        self.window.geometry("1100x750")
        self.window.minsize(900, 650)
        self.window.configure(fg_color=self.palette["window"])

        # ---------- передача вызовов в главный поток ----------
        self.dispatcher = Dispatcher(schedule=self.window.after, cancel=self.window.after_cancel)
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

    # =====================================================
    # Сборка интерфейса
    # =====================================================
    def _build_ui(self):
        p = self.palette

        self.main_container = ctk.CTkFrame(self.window, fg_color=p["window"], corner_radius=0)
        self.main_container.pack(fill="both", expand=True, padx=15, pady=15)

        # ---------- левая колонка ----------
        self.left_frame = ctk.CTkFrame(self.main_container, fg_color=p["surface"], corner_radius=16)
        self.left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.title_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.title_frame.pack(fill="x", pady=(15, 5))

        self.title_label = ctk.CTkLabel(self.title_frame, text="🎙️ ИИ-ПРЕПОДАВАТЕЛЬ",
                                        font=theme.FONT_TITLE, text_color=p["text_strong"])
        self.title_label.pack(side="left", padx=15)

        self.status_badge = ctk.CTkLabel(self.title_frame, text="● Проверяю сервер…",
                                         font=theme.FONT_SMALL, text_color=p["muted"])
        self.status_badge.pack(side="right", padx=15)

        self.visualizer = AudioVisualizer(self.left_frame, p, width=400, height=40)
        self.visualizer.pack(pady=(0, 10), padx=15, fill="x")

        self.chat_view = ChatView(self.left_frame, p, height=400)
        self.chat_view.pack(fill="x", padx=15, pady=(0, 10))

        self.input_bar = InputBar(self.left_frame, p, on_send=self.send_text)
        self.input_bar.pack(fill="both", padx=15, pady=(0, 10))

        self.control_bar = ControlBar(self.left_frame, p,
                                      on_record=self.toggle_recording,
                                      on_settings=self.open_panel,
                                      on_clear=self.clear_chat)
        self.control_bar.pack(fill="x", padx=15, pady=(0, 15))

        # ---------- правая колонка (изначально скрыта) ----------
        self.right_panel = SettingsPanel(self.main_container, p,
                                         mode=self.mode, theme_name=self.current_theme,
                                         on_save=self.save_settings, on_close=self.close_panel)

    # =====================================================
    # Мостик «фон → главный поток»
    # =====================================================
    def _dispatch(self, fn):
        """Выполнить fn в главном потоке Tk (виджеты из чужих потоков трогать нельзя).

        Просто кладём вызов в очередь: window.after() напрямую из чужого
        потока падает, если mainloop ещё не запущен.
        """
        self.dispatcher.dispatch(fn)

    # =====================================================
    # Обратная связь от контроллеров
    # =====================================================
    def add_message(self, sender, text):
        self.chat_view.add_message(sender, text)

    def _set_status(self, text, color_key="ok"):
        self.status_badge.configure(text=text, text_color=self.palette.get(color_key, self.palette["ok"]))

    def _set_busy(self, busy):
        self.busy = busy
        self.input_bar.set_busy(busy)

    def _on_response(self, user_text, response):
        """Ответ получен: озвучиваем и гасим визуализатор."""
        threading.Thread(target=tts.speak, args=(response,), daemon=True).start()
        self.visualizer.reset()

    def _on_recording_changed(self, recording):
        """Кнопка записи: красная во время записи, обычная после."""
        self.control_bar.set_recording(recording)

    def _on_recognized(self, text, lang):
        self.current_lang = lang
        self.chat.set_language(lang)
        self.add_message("Вы (голос)", text)
        self._submit(text)

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
        self._submit(text)

    def _submit(self, text):
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
            self.right_panel.pack(side="right", fill="y", padx=(0, 0))
            self.panel_visible = True

    def close_panel(self):
        if self.panel_visible:
            self.right_panel.pack_forget()
            self.panel_visible = False

    def save_settings(self):
        self.mode = self.right_panel.get_mode()
        self.chat.set_mode(self.mode)

        new_theme = self.right_panel.get_theme()
        if new_theme != self.current_theme:
            self.current_theme = new_theme
            self.palette = theme.palette(new_theme)
            ctk.set_appearance_mode(new_theme)
            self._apply_theme()

        self.close_panel()
        self.add_message("Джейн", f"⚙️ Режим изменён на {MODE_LABELS.get(self.mode, self.mode)}")

    # =====================================================
    # Тема
    # =====================================================
    def _apply_theme(self):
        """Одна точка смены темы вместо двух копий if/else с configure()."""
        p = self.palette
        self.window.configure(fg_color=p["window"])
        self.main_container.configure(fg_color=p["window"])
        self.left_frame.configure(fg_color=p["surface"])
        self.title_label.configure(text_color=p["text_strong"])

        self.visualizer.apply_theme(p)
        self.chat_view.apply_theme(p)
        self.input_bar.apply_theme(p)
        self.control_bar.apply_theme(p)
        self.right_panel.apply_theme(p)

        # бейдж перекрашиваем по текущему состоянию сервера
        self._on_server_state(self.server_state, "")

    # =====================================================
    # Сервер и жизненный цикл
    # =====================================================
    def check_server(self):
        return self.monitor.check_now()

    def run(self):
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.window.mainloop()

    def on_closing(self):
        try:
            self.monitor.stop()
        except Exception:
            pass
        try:
            self.dispatcher.stop()
        except Exception:
            pass
        if self.recorder.is_recording:
            self.recorder.stop()
        self.window.destroy()
