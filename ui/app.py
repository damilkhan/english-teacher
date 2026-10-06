# -*- coding: utf-8 -*-
# =========================================================
# UI/APP.PY — сборка окна English Teacher
# =========================================================
# Здесь только «клей»: создать виджеты, связать их с контроллерами,
# обновить интерфейс. Логика — в controllers/ и модулях верхнего уровня.
#
# Многопользовательский режим (вариант B):
#   • при первом запуске (профилей нет) — форма FirstRunForm;
#   • при повторном — сразу грузится последний активный профиль;
#   • кнопка «👥 Пользователи» открывает правую панель UsersPanel;
#   • прогресс обучения у каждого ученика свой (profile_store + user_id).
#
# Раскладка после редизайна:
#   фон окна — вертикальный градиент (рисуется на tk.Canvas полосками);
#   карточки («левая колонка» и правая панель) лежат на нём с отступами,
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
import user_manager
from controllers.chat_controller import ChatController
from controllers.dispatcher import Dispatcher
from controllers.level_test_controller import LevelTestController
from controllers.recording_controller import RecordingController
from controllers.server_monitor import ServerMonitor
from llm_client import LLMClient
from roles.analyst import Analyst
from ui import gradient
from ui.first_run import FirstRunForm
from ui.panels.level_test_panel import LevelTestPanel
from ui.panels.settings_panel import SettingsPanel
from ui.panels.users_panel import UsersPanel
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

# Пока в фоне грузится модель распознавания (Whisper) — отдельный статус,
# иначе бейдж показывал «Готов», хотя микрофон ещё не готов работать.
STT_LOADING_TEXT = "● Готовлю распознавание…"

NEW_PROFILE_NOTE = "📊 Создан профиль ученика. Я буду запоминать твой прогресс!"
LEVEL_TEST_NOTE = "🎯 Уровень определён: %s. Подстрою уроки под него."
NOT_READY_LOADING = "⏳ Модель ещё загружается — подожди несколько секунд и попробуй снова."
NOT_READY_OFFLINE = "❌ LLM-сервер не отвечает. Подробности в logs\\llama-server.log"

HERO_HEIGHT = 92
PANEL_WIDTH = 400     # ширина правой панели: даже длинное «Имя Фамилия» видно целиком
TITLE_POS = (22, 17)        # заголовок шапки (x, y) внутри шапки
SUBTITLE_POS = (24, 50)     # подпись под заголовком
BADGE_MARGIN = 18           # отступ пилюли от правого края шапки
TITLE_EMOJI = "🎙️"
TITLE_TEXT = "ИИ-ПРЕПОДАВАТЕЛЬ"
SUBTITLE_TEXT = "Джейн · локальный преподаватель английского"
INITIAL_STATUS = ("● Проверяю сервер…", "muted")
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
        self.active_panel = None      # "settings" | "users" | None
        self.busy = False
        self.server_state = "offline"
        self.server_ready = False
        self.stt_state = "loading"      # loading | ready | error
        self.stt_ready = False
        self._status_text, self._status_color = INITIAL_STATUS
        self._hero_fonts = {}      # заполним ниже, после создания окна

        # ---------- окно ----------
        self.window = ctk.CTk()
        self.window.title("English Teacher — Jane")
        self.window.geometry("1160x760")
        # минимальная высота уменьшена: при 620 px всё помещается целиком
        # (шапка + эквалайзер + чат + поле ввода + кнопки)
        # минимум по ширине: при широкой панели нижней панели кнопок ещё хватает
        # места (иначе «Настройки»/«Пользователи» уезжали за край карточки)
        self.window.minsize(1040, 620)
        self.window.configure(fg_color=self.palette["window"])

        # шрифты подбираем, когда окно уже есть (нужен список семейств системы)
        theme.resolve_fonts(self.window)
        self._hero_fonts = theme.pillow_fonts()   # и файлы для отрисовки шапки

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

        # ---------- активный пользователь (форма при первом запуске) ----------
        self._pending_level_test = None        # id профиля для теста уровня
        self.current_user = self._resolve_user()
        profile_store.set_active_user(self.current_user["id"])
        print("👤 Активный профиль: #%s %s" % (self.current_user["id"], self.current_user["name"]))

        # ---------- железо и сеть ----------
        self.vad = audio_vad.AudioVAD()
        # Модель грузится В ФОНЕ (preload ниже): иначе старт окна «замирал»
        # на десятки секунд, пока Whisper читается с диска.
        self.stt = stt_engine.STTEngine(on_state=self._on_stt_state)
        self.llm = LLMClient()

        # ---------- контроллеры ----------
        # роль-Аналитик: разбирает реплики ученика в режиме урока
        analyst = Analyst(self.llm) if config.ANALYST_ENABLED else None
        self.chat = ChatController(llm=self.llm, dispatch=self._dispatch,
                                   mode=self.mode, lang=self.current_lang,
                                   user_id=self.current_user["id"],
                                   analyst=analyst)
        self.chat.on_message = self.add_message
        self.chat.on_status = self._set_status
        self.chat.on_busy = self._set_busy
        self.chat.on_response = self._on_response

        # ---------- тест уровня (адаптивный, любой активной моделью) ----------
        self.level_test = LevelTestController(dispatch=self._dispatch)

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
        _, created = profile_store.ensure_profile(self.current_user["id"])
        if created:
            self.add_message("Джейн", NEW_PROFILE_NOTE)
        self.check_server()
        self.monitor.start()
        self.stt.preload()                      # Whisper — в фоне, окно не ждёт
        self.window.after(60, self._redraw)     # первая отрисовка после раскладки

        # новый профиль → сразу предлагаем определить уровень
        if self._pending_level_test is not None:
            uid = self._pending_level_test
            self.window.after(900, lambda: self.run_level_test(uid))

    # =====================================================
    # Пользователи
    # =====================================================
    def _resolve_user(self):
        """Активный профиль: последний из profiles/ либо форма первого запуска."""
        users = user_manager.list_users()
        if users:
            return user_manager.get_last_user() or users[0]

        self.window.withdraw()              # прячем пустое окно под формой
        try:
            data = FirstRunForm.ask(self.window, self.palette)
        finally:
            self.window.deiconify()

        if data:
            created = user_manager.create_user(**self._form_profile(data))
            if created:
                self._pending_level_test = created["id"]
                return created

        # форму закрыли — заводим профиль по умолчанию, чтобы приложение жило
        # (уровень не задаём: его определит вводный тест)
        fallback = user_manager.create_user("Ученик", "other", None, None,
                                            "Учиться говорить по-английски", "🙂")
        if fallback:
            self._pending_level_test = fallback["id"]
        return fallback or user_manager.get_last_user()

    @staticmethod
    def _form_profile(data):
        """Поля профиля из формы. Уровень НЕ берём: его ставит вводный тест,
        поэтому у нового профиля уровень остаётся «не определён»."""
        return {
            "name": data["name"], "gender": data["gender"], "age": data["age"],
            "goal": data.get("goal", ""), "avatar": data.get("avatar"),
        }

    def _greeting(self):
        u = self.current_user or {}
        text = (f"{u.get('avatar', '🙂')} Привет, {u.get('name') or 'друг'}! "
                f"Я Джейн, твой преподаватель английского.\n"
                f"Я буду запоминать твои ошибки и подстраивать уроки под тебя.")
        level = u.get("level")
        if level:
            text += f"\n🎯 Твой уровень: {level} — буду подбирать задания под него."
        else:
            text += ("\n🎯 Уровень пока не определён — пройди вводный тест, "
                     "и я подстроюсь под него.")
        return text

    def _hero_subtitle(self):
        """Подпись шапки: аватар + имя + уровень активного ученика."""
        u = self.current_user or {}
        name = str(u.get("name") or "").strip()
        if not name:
            return SUBTITLE_TEXT
        sub = "%s %s" % (u.get("avatar") or "🙂", name)
        sub += " · уровень %s" % user_manager.level_label(u.get("level"))
        return sub

    def _refresh_hero(self):
        """Шапка — КАРТИНКА (кэш _hero_cache): после смены данных сбрасываем кэш."""
        self._hero_cache = (None, None)
        try:
            self._redraw()
        except Exception as exc:
            print(f"⚠️ Шапка не обновилась: {exc}")

    def select_user(self, user_id):
        """Сделать профиль активным: контроллер, история и прогресс — его."""
        if user_id == (self.current_user or {}).get("id"):
            return
        user = user_manager.get_user(user_id)
        if not user:
            return
        self.current_user = user
        user_manager.set_last_user(user_id)
        profile_store.set_active_user(user_id)
        profile_store.ensure_profile(user_id)
        self.chat.set_user(user_id)         # сброс истории диалога
        self.chat_view.clear()
        self.add_message("Джейн", self._greeting())
        self._refresh_hero()
        if self.users_panel is not None:
            self.users_panel.refresh(user_id)

    def add_user(self):
        if user_manager.is_full():
            return
        data = FirstRunForm.ask(self.window, self.palette)
        if not data:
            return
        created = user_manager.create_user(**self._form_profile(data))
        if created:
            self.select_user(created["id"])
            self.window.after(300, lambda: self.run_level_test(created["id"]))

    def edit_user(self, user_id):
        user = user_manager.get_user(user_id)
        if not user:
            return
        data = FirstRunForm.ask(self.window, self.palette, user=user)
        if not data:
            return
        user_manager.update_user(user_id, data)
        if user_id == (self.current_user or {}).get("id"):
            self.current_user = user_manager.get_user(user_id)
            self.add_message("Джейн", "✅ Профиль обновлён.")
            self._refresh_hero()
        if self.users_panel is not None:
            self.users_panel.refresh((self.current_user or {}).get("id"))

    def delete_user(self, user_id):
        created = None
        was_active = (user_id == (self.current_user or {}).get("id"))
        user_manager.delete_user(user_id)

        remaining = user_manager.list_users()
        if not remaining:
            # профилей не осталось — просим создать нового (форма первого запуска)
            data = FirstRunForm.ask(self.window, self.palette)
            created = None
            if data:
                created = user_manager.create_user(**self._form_profile(data))
            if created is None:
                # уровень не задаём: его определит вводный тест
                created = user_manager.create_user("Ученик", "other", None, None,
                                                   "Учиться говорить по-английски", "🙂")
            remaining = [created] if created else user_manager.list_users()

        if was_active and remaining:
            self.select_user(remaining[0]["id"])
        elif self.users_panel is not None:
            self.users_panel.refresh((self.current_user or {}).get("id"))

        if created:
            self.window.after(300, lambda: self.run_level_test(created["id"]))

    def run_level_test(self, user_id):
        """Адаптивный тест уровня: показать окно и сохранить уровень в профиль.

        Панели передаём пробу готовности сервера (решение B): пока модель
        грузится, окно теста показывает «Модель загружается…» и стартует само,
        когда сервер ответит ready. Иначе первые вопросы тихо уходили бы в
        резервный банк и уровень получался бы неточным.
        """
        try:
            level = LevelTestPanel.ask(self.window, self.palette, self.level_test,
                                       user_id, ready_probe=self.check_server)
        except Exception as exc:
            print("⚠️ Тест уровня не открылся: %s" % exc)
            return None
        if level:
            self.current_user = user_manager.get_user(user_id) or self.current_user
            self.add_message("Джейн", LEVEL_TEST_NOTE % level)
            self._refresh_hero()          # уровень — в шапку (это картинка)
        if self.users_panel is not None:
            self.users_panel.refresh((self.current_user or {}).get("id"))
        return level

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
        self.chat_view = ChatView(self.left_frame, p,
                                  greeting=("Джейн", self._greeting()))
        self.input_bar = InputBar(self.left_frame, p, on_send=self.send_text)
        self.control_bar = ControlBar(self.left_frame, p,
                                      on_record=self.toggle_recording,
                                      on_settings=self.open_panel,
                                      on_clear=self.clear_chat,
                                      on_users=self.open_users_panel)

        self._build_hero()

        # Порядок упаковки важен! pack отдаёт место СНАЧАЛА упакованным,
        # поэтому нижние элементы крепим к низу первыми — тогда они никогда
        # не обрезаются, а чат забирает ровно то, что осталось (expand).
        # Раньше чат упаковывался раньше кнопок: при недостатке высоты
        # панель управления уходила за нижний край окна.
        self.hero.pack(side="top", fill="x", padx=theme.CARD_PAD, pady=(theme.CARD_PAD, 8))
        self.visualizer.pack(side="top", fill="x", padx=theme.CARD_PAD + 4, pady=(0, 6))

        self.control_bar.pack(side="bottom", fill="x", padx=theme.CARD_PAD,
                              pady=(0, theme.CARD_PAD))
        self.input_bar.pack(side="bottom", fill="x", padx=theme.CARD_PAD, pady=(0, 8))

        # чат — последним: он и только он растягивается
        self.chat_view.pack(side="top", fill="both", expand=True,
                            padx=theme.CARD_PAD, pady=(0, 10))

        # ---------- правая панель «настройки» ----------
        self.right_panel = SettingsPanel(self.base, p,
                                         mode=self.mode, theme_name=self.current_theme,
                                         on_save=self.save_settings, on_close=self.close_panel)

        # ---------- правая панель «пользователи» ----------
        self.users_panel = UsersPanel(self.base, p,
                                      active_id=self.current_user["id"],
                                      on_add=self.add_user,
                                      on_edit=self.edit_user,
                                      on_delete=self.delete_user,
                                      on_select=self.select_user,
                                      on_close=self.close_panel,
                                      on_test=self.run_level_test)

    def _build_hero(self):
        """Шапка — ОДНА картинка: градиент, заголовок, подпись и пилюля статуса.

        Раньше здесь лежали обычные CTkLabel поверх градиента. Customtkinter
        для bg_color="transparent" берёт цвет РОДИТЕЛЯ (цвет карточки), поэтому
        под каждой строкой заголовка рисовался тёмный прямоугольник вплотную
        к буквам, а под круглой пилюлей «Готов» — тёмный квадрат. Теперь
        текстов-виджетов на градиенте нет вообще: всё вписано в изображение.
        """
        p = self.palette
        self.hero = ctk.CTkFrame(self.left_frame, fg_color=p["surface"],
                                 corner_radius=theme.R["card"], height=HERO_HEIGHT)
        self.hero.pack_propagate(False)

        self.hero_bg = ctk.CTkLabel(self.hero, text="", fg_color="transparent",
                                    bg_color=p["hero_a"])
        self.hero_bg.place(x=0, y=0, relwidth=1, relheight=1)

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
        """Расставляет карточки: слева чат, справа активная панель (если открыта)."""
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
            panel = self.users_panel if self.active_panel == "users" else self.right_panel
            panel.place(x=w - pad - PANEL_WIDTH, y=pad,
                        relwidth=PANEL_WIDTH / float(w),
                        relheight=inner_h / float(h))

        self._update_hero(max(160, left_w - 2 * theme.CARD_PAD))

        # Углы карточек на градиенте: CTk закрашивает скруглённый угол
        # фоном родителя (canvas → grad_top), а не самим градиентом, и в
        # углах проступали тёмные квадраты. Подставляем настоящий цвет
        # градиента на верхнем и нижнем краю карточки.
        corners = self._card_corners(h, pad, pad + inner_h)
        for card in (self.left_frame, self.right_panel, self.users_panel):
            try:
                card.configure(background_corner_colors=corners)
            except Exception:
                pass

    def _card_corners(self, height, top_y, bottom_y):
        """Цвета градиента для углов карточки: (TL, TR, BR, BL).

        Градиент вертикальный, поэтому верхние углы берут цвет на верхнем
        краю карточки, нижние — на нижнем (низ заметнее: там градиент уже
        уходит в фиолетовый).
        """
        p = self.palette
        span = max(1, int(height) - 1)

        def color(y):
            t = max(0.0, min(1.0, float(y) / span))
            return gradient.lerp_hex(p["grad_top"], p["grad_bottom"], t)

        top, bottom = color(top_y), color(bottom_y)
        return (top, top, bottom, bottom)

    def _update_hero(self, width=None):
        """Собирает шапку картинкой: градиент + тексты + пилюля статуса.

        Пересобираем только при смене ширины, темы или текста статуса —
        иначе картинка генерировалась бы каждые 3 секунды (опрос сервера).
        """
        if width is None:
            width = self.hero.winfo_width()
        width = int(width)
        if width < 50:
            return
        subtitle = self._hero_subtitle()
        key = (width, self.current_theme, self._status_text,
               self._status_color, subtitle)
        if self._hero_cache[0] == key:
            return

        p = self.palette
        try:
            img = gradient.hero_full(
                (width, HERO_HEIGHT), p,
                emoji=TITLE_EMOJI, title=TITLE_TEXT, subtitle=subtitle,
                badge=self._status_text,
                badge_text_color=p.get(self._status_color, p["ok"]),
                badge_bg=p.get(self._status_color + "_soft", p["muted_soft"]),
                fonts=self._hero_fonts,
                title_pos=TITLE_POS, subtitle_pos=SUBTITLE_POS,
                badge_margin=BADGE_MARGIN, radius=theme.R["card"],
            )
            cimg = ctk.CTkImage(light_image=img, dark_image=img,
                                size=(width, HERO_HEIGHT))
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
        """Пилюля статуса в шапке.

        Текст вписан в картинку шапки, поэтому здесь только запоминаем
        состояние и просим перерисовать — но лишь если оно изменилось
        (иначе шапка пересобиралась бы на каждом опросе сервера).
        """
        if (text, color_key) == (self._status_text, self._status_color):
            return
        self._status_text, self._status_color = text, color_key
        self._update_hero()

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
        self._refresh_status()
        return state

    def _on_stt_state(self, state, message):
        """Колбэк STTEngine (из фонового потока) → в главный поток."""
        self._dispatch(lambda: self._apply_stt_state(state, message))

    def _apply_stt_state(self, state, message):
        self.stt_state = state
        self.stt_ready = (state == "ready")
        self._refresh_status()

    def _refresh_status(self):
        """Единая точка выбора текста бейджа: сервер + распознавание.

        Приоритет: если доступна модель, но ещё грузится Whisper — говорим об
        этом; во всех остальных случаях показываем состояние LLM-сервера.
        """
        if self.busy:                       # не сбиваем «Думает…»/«Распознаю…»
            return
        if self.server_ready and self.stt_state == "loading":
            self._set_status(STT_LOADING_TEXT, "warn")
            return
        self._set_status(STATUS_TEXT.get(self.server_state, STATUS_TEXT["offline"]),
                         STATUS_COLOR.get(self.server_state, "err"))

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
        # пользователь что-то делает — гасим текущую речь Джейн
        tts.stop()

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
        if not self.recorder.is_recording:
            tts.stop()          # начинаем запись — гасим речь Джейн
        self.recorder.toggle()

    def clear_chat(self):
        self.chat_view.clear()
        self.chat.clear_history()

    def _show_panel(self, name):
        """Показать правую панель: только одну из двух."""
        for panel in (self.right_panel, self.users_panel):
            try:
                panel.place_forget()
            except Exception:
                pass
        self.active_panel = name
        self.panel_visible = True
        self._layout()

    def open_panel(self):
        self._show_panel("settings")

    def open_users_panel(self):
        if self.users_panel is not None:
            self.users_panel.refresh((self.current_user or {}).get("id"))
        self._show_panel("users")

    def close_panel(self):
        if not self.panel_visible:
            return
        self.panel_visible = False
        self.active_panel = None
        for panel in (self.right_panel, self.users_panel):
            try:
                panel.place_forget()
            except Exception:
                pass
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
        self.hero_bg.configure(bg_color=p["hero_a"])

        self._hero_cache = (None, None)          # шапку пересобрать под новую палитру
        self.visualizer.apply_theme(p)
        self.chat_view.apply_theme(p)
        self.input_bar.apply_theme(p)
        self.control_bar.apply_theme(p)
        self.right_panel.apply_theme(p)
        self.users_panel.apply_theme(p)

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
