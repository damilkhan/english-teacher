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
import character
import commands
import config
import lesson as lesson_mod
import model_registry
import profile_store
import progress_map
import reactions
import server_manager
import settings_store
import stt_engine
import theme
import tts
import user_manager
from controllers.chat_controller import ChatController
from controllers.dispatcher import Dispatcher
from controllers.lesson_controller import LessonController
from controllers.server_waiter import ServerWaiter
from controllers.level_test_controller import LevelTestController
from controllers.recording_controller import RecordingController
from controllers.server_monitor import ServerMonitor
from llm_client import LLMClient
from roles.analyst import Analyst
from roles.planner import Planner
from ui import gradient
from ui.first_run import FirstRunForm
from ui.panels.block_panel import BlockPanel
from ui.panels.boot_panel import BootPanel
from ui.panels.level_test_panel import LevelTestPanel
from ui.panels.settings_panel import SettingsPanel
from ui.panels.users_panel import UsersPanel
from ui.widgets.chat_view import ChatView
from ui.widgets.control_bar import ControlBar
from ui.widgets.info_bar import InfoBar
from ui.widgets.input_bar import InputBar
from ui.widgets.lesson_bar import LessonBar
from ui.widgets.map_view import MapView
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
SETUP_HINT = ("✋ Чтобы начать, заполни профиль: имя и пол. "
              "Нажми «👥 Пользователи», затем ✏️ у активного профиля.")
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
CHARACTER_WIDTH = 300        # ширина робота-персонажа в области чата, px
REDRAW_DELAY_MS = 90

# Подписи разбора Аналитика для тонкой строки «учительского» вида.
MOVE_TYPE_RU = {"Q": "вопрос", "A": "ответ", "S": "реплика", "F": "отклик", "O": "прочее"}
MOVE_STATUS_RU = {"A": "✔ принято", "P": "⚠ доработать"}

# Подписи ошибок для вкладки «Профиль».
MISTAKE_WORD = {"grammar": "грамматика", "vocabulary": "лексика",
                "pronunciation": "произношение"}


def profile_summary(user, profile, map_progress=(0, 0)):
    """Строки сводки для вкладки «Профиль»: [(заголовок, значение), …].

    Чистая функция (без Tk) — её удобно проверять тестами и пересобирать
    при смене ученика/темы, не трогая логику окна.
    """
    user = user or {}
    profile = profile or {}
    out = []

    name = str(user.get("name") or "").strip() or "Ученик"
    avatar = user.get("avatar") or "🙂"
    out.append(("Ученик", "%s %s" % (avatar, name)))
    out.append(("Уровень", user_manager.level_label(user.get("level"))))
    try:
        done, total = int(map_progress[0]), int(map_progress[1])
    except Exception:
        done, total = 0, 0
    out.append(("Карта «Пустыня»", "пройдено блоков: %d из %d" % (done, total)))
    out.append(("Занятий с Джейн", str(profile.get("total_lessons", 0))))

    mistakes = profile.get("mistakes") or {}
    counts = []
    for key in ("grammar", "vocabulary", "pronunciation"):
        items = mistakes.get(key) or []
        if items:
            counts.append("%s %d" % (MISTAKE_WORD.get(key, key), len(items)))
    out.append(("Ошибки", " · ".join(counts) if counts else "пока нет"))

    weak = profile.get("weak_topics") or []
    topics = [str(w.get("topic")) for w in weak if isinstance(w, dict) and w.get("topic")]
    if topics:
        out.append(("Слабые темы", ", ".join(topics[:5])))

    strengths = profile.get("strengths") or []
    if strengths:
        out.append(("Сильные стороны", "удачных реплик: %d" % len(strengths)))

    recent = []
    for key in ("grammar", "vocabulary", "pronunciation"):
        for item in (mistakes.get(key) or [])[-5:]:
            if not isinstance(item, dict):
                continue
            wrong = str(item.get("wrong") or "").strip()
            correct = str(item.get("correct") or "").strip()
            if wrong and correct:
                recent.append("%s → %s" % (wrong, correct))
    if recent:
        out.append(("Последние ошибки", "\n".join(recent[-5:])))
    return out


class _Tabview(ctk.CTkTabview):
    """CTkTabview, который зовёт command и при ПРОГРАММНОМ set().

    Штатный CTkTabview дёргает command только по клику мыши (значение
    передаётся с флагом from_button_callback). Из-за этого переключение
    вкладки кодом (tabs.set("Карта")) не будило карту. Здесь мы просто
    дублируем вызов command после смены вкладки.
    """

    def set(self, name):
        super().set(name)
        command = getattr(self, "_command", None)
        if command is not None:
            try:
                command(name)
            except Exception:
                pass


class EnglishTeacherApp:
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.current_theme = config.DEFAULT_THEME
        self.palette = theme.palette(self.current_theme)
        self.mode = config.DEFAULT_MODE
        self.current_model_id = settings_store.get_selected_model_id()
        self.current_lang = "en"
        self._jane_mark = None     # метка последней реплики Джейн (для повтора)
        self.panel_visible = False
        self.active_panel = None      # "settings" | "users" | None
        self.busy = False
        self.server_state = "offline"
        self.server_ready = False
        self.stt_state = "loading"      # loading | ready | error
        self.stt_ready = False
        self._status_text, self._status_color = INITIAL_STATUS
        self._last_speaker = "jane"     # чей цвет на эквалайзере
        self._last_char_level = -1.0    # последний уровень, отданный лицу
        self._last_char_speaker = ""
        self.reactions = reactions.ReactionTracker()   # 3 промаха → похвала
        self._mood_plan = None          # план эмоций текущей реплики
        self._mood_at = 0.0             # сколько реплики уже прозвучало
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

        # ---------- активный пользователь ----------
        # Заготовка профиля создаётся даже без формы, но считается НЕПОЛНОЙ:
        # пока профиль не заполнен (имя + пол), общение с Джейн недоступно.
        self.current_user = self._resolve_user()
        self.profile_ready = user_manager.is_complete(self.current_user)
        profile_store.set_active_user(self.current_user["id"])
        print("👤 Активный профиль: #%s %s (полный: %s)"
              % (self.current_user["id"], self.current_user["name"], self.profile_ready))

        # ---------- железо и сеть ----------
        self.vad = audio_vad.AudioVAD()
        # Модель грузится В ФОНЕ (preload ниже): иначе старт окна «замирал»
        # на десятки секунд, пока Whisper читается с диска.
        self.stt = stt_engine.STTEngine(on_state=self._on_stt_state,
                                        hotwords_provider=self._stt_hotwords)
        self.llm = LLMClient()

        # ---------- контроллеры ----------
        # роль-Аналитик: разбирает реплики ученика в режиме урока
        analyst = Analyst(self.llm) if config.ANALYST_ENABLED else None
        # роль-Планировщик: короткий план урока (в промпт Учителя)
        planner = Planner(self.llm) if config.PLANNER_ENABLED else None
        self.chat = ChatController(llm=self.llm, dispatch=self._dispatch,
                                   mode=self.mode, lang=self.current_lang,
                                   user_id=self.current_user["id"],
                                   analyst=analyst, planner=planner)
        self.chat.on_message = self.add_message
        self.chat.on_status = self._set_status
        self.chat.on_busy = self._set_busy
        self.chat.on_response = self._on_response
        self.chat.on_analysis = self._on_analysis   # разбор → строка над вводом
        self.chat.on_plan = self._on_plan           # план урока → туда же

        # ---------- тест уровня (адаптивный, любой активной моделью) ----------
        self.level_test = LevelTestController(dispatch=self._dispatch)

        self.recorder = RecordingController(
            vad=self.vad, stt=self.stt, dispatch=self._dispatch,
            on_status=self._set_status,
            on_recording_changed=self._on_recording_changed,
            on_recognized=self._on_recognized,
        )

        # ---------- занятие по карте ----------
        # Держит текущую сессию урока (lesson.LessonSession); логика правил —
        # в lesson.py, интерфейс — здесь.
        self.lesson = LessonController(
            dispatch=self._dispatch,
            on_started=self._on_lesson_started,
            on_reply=self._on_lesson_reply,
            on_finished=self._on_lesson_finished,
            on_aborted=self._on_lesson_aborted,
        )
        self._pending_lesson = None      # урок, ждущий готовности распознавания
        # Отложенное действие, ждущее LLM-сервер (см. _run_when_server_ready)
        self._server_task = None

        # ---------- карта прогресса ----------
        # curriculum.json читаем ОДИН раз: карта и вкладка «Профиль»
        # берут данные отсюда (см. progress_map.ProgressMap)
        self.progress_map = progress_map.ProgressMap()
        self.map_view = None

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
        self.window.after(120, self._visual_tick)   # эквалайзер: кто говорит
        self._refresh_input_state()             # чат закрыт, пока нет профиля/модели
        # неполный профиль → обязательная форма; иначе (нет уровня) — тест
        self.window.after(200, self._first_run_flow)

    # =====================================================
    # Пользователи
    # =====================================================
    def _resolve_user(self):
        """Активный профиль: последний из profiles/ либо НЕПОЛНАЯ заготовка.

        Форму здесь НЕ показываем: за неё отвечает _first_run_flow (после
        сборки окна). Так один путь и для первого запуска, и для «пустого»
        профиля — оба обязаны задать имя и пол.
        """
        users = user_manager.list_users()
        if users:
            return user_manager.get_last_user() or users[0]
        # профилей нет — заготовка (complete=False), её заполнит форма
        return (user_manager.create_user("Ученик", "other", None, None, "", "🙂",
                                         complete=False)
                or user_manager.get_last_user())

    # =====================================================
    # Гейт: обязательный профиль + готовность сервера
    # =====================================================
    def _first_run_flow(self):
        """После старта: заполнить профиль → дождаться модели → тест уровня."""
        self._refresh_input_state()
        if not self.profile_ready:
            self._prompt_profile_setup()
            return
        self._after_profile_ready()

    def _after_profile_ready(self):
        """Профиль полон: показать экран загрузки модели и предложить тест.

        Пока сервер грузится — модальный экран BootPanel (он сам закроется,
        когда модель готова; можно «продолжить без модели»). Тест уровня
        запускаем только при готовом сервере (он умеет ждать, но два окна
        ожидания подряд — лишнее).
        """
        if not self.server_ready and self.server_state == "loading":
            BootPanel.ask(self.window, self.palette, self.check_server)
        self._refresh_input_state()
        if self.server_ready and not (self.current_user or {}).get("level"):
            self.window.after(300, lambda: self.run_level_test(self.current_user["id"]))

    def _prompt_profile_setup(self):
        """Обязательная форма: без имени и пола общение с Джейн запрещено."""
        user = self.current_user or {}
        data = FirstRunForm.ask(self.window, self.palette)     # режим «первого запуска»
        if not data:
            self.add_message("Джейн", SETUP_HINT)
            return

        target = user.get("id")
        if target:
            user_manager.update_user(target, dict(self._form_profile(data), complete=True))
        else:
            created = user_manager.create_user(**self._form_profile(data), complete=True)
            target = created["id"] if created else None
        if not target:
            self.add_message("Джейн", SETUP_HINT)
            return

        self.current_user = user_manager.get_user(target) or self.current_user
        self.profile_ready = user_manager.is_complete(self.current_user)
        profile_store.set_active_user(target)
        profile_store.ensure_profile(target)
        self.chat.set_user(target)
        self.chat_view.clear()
        self.info_bar.clear()
        self.add_message("Джейн", self._greeting())
        self._refresh_hero()
        self._refresh_input_state()
        self._refresh_side_views()
        self._after_profile_ready()

    def _refresh_input_state(self):
        """Поле ввода активно только при ПОЛНОМ профиле и готовом сервере."""
        ready = bool(self.profile_ready and self.server_ready)
        if not self.profile_ready:
            hint = "Заполни профиль"
        elif not self.server_ready:
            hint = "Загружаю модель…"
        else:
            hint = ""
        self.input_bar.set_enabled(ready, hint)

    @staticmethod
    def _form_profile(data):
        """Поля профиля из формы. Уровень НЕ берём: его ставит вводный тест,
        поэтому у нового профиля уровень остаётся «не определён»."""
        return {
            "name": data["name"], "name_latin": data.get("name_latin") or "",
            "gender": data["gender"], "age": data["age"],
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
        if self.lesson.is_active:
            # занятие принадлежит прошлому ученику — прерываем, не засчитывая
            self._pending_lesson = None
            self.lesson.abort()
            self.lesson.reset()
        self.current_user = user
        self.profile_ready = user_manager.is_complete(user)
        user_manager.set_last_user(user_id)
        profile_store.set_active_user(user_id)
        profile_store.ensure_profile(user_id)
        self.chat.set_user(user_id)         # сброс истории диалога
        try:
            self.reactions.reset()          # у нового ученика свой счёт
        except Exception:
            pass
        self.chat_view.clear()
        self.info_bar.clear()
        self.add_message("Джейн", self._greeting())
        self._refresh_hero()
        self._refresh_input_state()
        self._refresh_side_views()
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
        user_manager.update_user(user_id, dict(data, complete=True))
        if user_id == (self.current_user or {}).get("id"):
            self.current_user = user_manager.get_user(user_id)
            self.profile_ready = user_manager.is_complete(self.current_user)
            self.add_message("Джейн", "✅ Профиль обновлён.")
            self._refresh_hero()
            self._refresh_input_state()
            self._refresh_side_views()
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
                # заготовка (неполный профиль): чат останется закрыт до заполнения
                created = user_manager.create_user("Ученик", "other", None, None, "", "🙂",
                                                   complete=False)
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

        # Вкладки «Чат» / «Карта» / «Профиль» живут ВНУТРИ левой карточки,
        # а шапка и эквалайзер остаются НАД ними (вариант А) — они общие.
        self.tabs = _Tabview(
            self.left_frame, fg_color=p["surface"],
            segmented_button_fg_color=p["btn"],
            segmented_button_selected_color=p["accent"],
            segmented_button_selected_hover_color=p["accent_hover"],
            segmented_button_unselected_color=p["btn"],
            segmented_button_unselected_hover_color=p["btn_hover"],
            text_color=p["text"], corner_radius=theme.R["block"],
            command=self._on_tab_changed,
        )
        self.chat_tab = self.tabs.add("Чат")
        self.map_tab = self.tabs.add("Карта")
        self.profile_tab = self.tabs.add("Профиль")

        self._ui_ready = False      # до конца сборки на смену вкладок не реагируем

        self.chat_view = ChatView(self.chat_tab, p,
                                  greeting=("Джейн", self._greeting()),
                                  on_replay=self._replay_reply)

        # ---------- робот-персонаж Джейн (idle-анимация) ----------
        # Робот — украшение области чата: его сбой не должен ломать окно,
        # поэтому весь блок в try/except. Робот лежит ПОВЕРХ области чата,
        # но текст чата заканчивается выше него — реплики не перекрываются
        # (полоса прокрутки при этом остаётся у правого края, не в середине).
        self.character = None
        try:
            self.character = character.Character(self.chat_view,
                                                 width=CHARACTER_WIDTH,
                                                 dispatch=self._dispatch)
            if self.character.available:
                # робот занимает правый нижний угол: чат занимает ВСЁ поле,
                # а сообщения на полосе робота обтекают его слева
                reserve_w, reserve_h = self.character.reserve
                self.chat_view.set_character_reserve(reserve_w, reserve_h)
                self.character.start_idle()
        except Exception as exc:
            print("⚠️ Робот-персонаж не подключился: %s" % exc)
            self.character = None
        self.input_bar = InputBar(self.chat_tab, p, on_send=self.send_text)
        self.control_bar = ControlBar(self.chat_tab, p,
                                      on_record=self._start_recording,
                                      on_record_release=self._stop_recording,
                                      on_settings=self.open_panel,
                                      on_clear=self.clear_chat,
                                      on_users=self.open_users_panel)

        # ---------- тонкая строка «учительского» вида ----------
        # Разбор Аналитика и фокус плана урока — ОТДЕЛЬНОЙ полосой над
        # полем ввода (в чат такие служебные строки не пишем). Виджет сам
        # прячется, пока данных нет, поэтому при старте её не видно.
        self.info_bar = InfoBar(self.chat_tab, p, before=self.chat_view)

        # ---------- полоса идущего занятия ----------
        # «🎓 Урок 1.1 · Hello / Hi · говорение · 4/12  [Выйти]» — над полем
        # ввода (pack before=chat_view), сама прячется, когда урока нет.
        self.lesson_bar = LessonBar(self.chat_tab, p, on_exit=self.exit_lesson,
                                    before=self.chat_view)

        self._build_hero()

        # Порядок упаковки важен! pack отдаёт место СНАЧАЛА упакованным,
        # поэтому нижние элементы крепим к низу первыми — тогда они никогда
        # не обрезаются, а чат забирает ровно то, что осталось (expand).
        # Раньше чат упаковывался раньше кнопок: при недостатке высоты
        # панель управления уходила за нижний край окна.
        self.hero.pack(side="top", fill="x", padx=theme.CARD_PAD, pady=(theme.CARD_PAD, 8))
        self.visualizer.pack(side="top", fill="x", padx=theme.CARD_PAD + 4, pady=(0, 6))
        self.tabs.pack(side="top", fill="both", expand=True,
                       padx=theme.CARD_PAD - 6, pady=(0, theme.CARD_PAD - 6))

        # ---- вкладка «Чат»: кнопки и ввод прижаты к низу, чат растёт ----
        self.control_bar.pack(side="bottom", fill="x", padx=6,
                              pady=(0, theme.CARD_PAD - 6))
        self.input_bar.pack(side="bottom", fill="x", padx=6, pady=(0, 8))

        # чат — последним: он и только он растягивается
        self.chat_view.pack(side="top", fill="both", expand=True,
                            padx=6, pady=(0, 8))

        # ---- вкладки «Карта» и «Профиль» ----
        self._build_map_tab()
        self._build_profile_tab()

        # ---------- правая панель «настройки» ----------
        self.right_panel = SettingsPanel(self.base, p,
                                         mode=self.mode, theme_name=self.current_theme,
                                         on_save=self.save_settings, on_close=self.close_panel,
                                         models=model_registry.available_models(),
                                         model=self.current_model_id)

        # ---------- правая панель «пользователи» ----------
        self.users_panel = UsersPanel(self.base, p,
                                      active_id=self.current_user["id"],
                                      on_add=self.add_user,
                                      on_edit=self.edit_user,
                                      on_delete=self.delete_user,
                                      on_select=self.select_user,
                                      on_close=self.close_panel,
                                      on_test=self.run_level_test)

        # «Держать кнопку»: отпускание мыши в ЛЮБОМ месте останавливает запись
        # (иначе, уведя курсор и отпустив вне кнопки, запись зависла бы).
        self.window.bind("<ButtonRelease-1>", self._on_global_release, add="+")
        self._ui_ready = True      # с этого момента реагируем на смену вкладок

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
    # Вкладки: карта и профиль
    # =====================================================
    def _build_map_tab(self):
        """Вкладка «Карта»: интерактивная карта локации «Пустыня»."""
        self.map_view = MapView(self.map_tab, self.palette,
                                location_id="desert",
                                on_point_click=self.on_point_click,
                                map_obj=self.progress_map)
        self.map_view.pack(fill="both", expand=True, padx=4, pady=4)
        self.map_view.set_active(False)      # стартовая вкладка — «Чат»

    def _build_profile_tab(self):
        """Вкладка «Профиль»: краткая сводка прогресса ученика."""
        import customtkinter as _ctk
        self.profile_box = _ctk.CTkScrollableFrame(self.profile_tab,
                                                   fg_color="transparent")
        self.profile_box.pack(fill="both", expand=True, padx=4, pady=4)
        self._refresh_profile_tab()

    def _active_profile(self):
        """Прогресс активного ученика. Ошибки наружу не пробрасываем."""
        try:
            return profile_store.load((self.current_user or {}).get("id"))
        except Exception:
            return {}

    def _refresh_profile_tab(self, profile=None):
        """Пересобрать сводку профиля (уровень, ошибки, слабые темы…)."""
        box = getattr(self, "profile_box", None)
        if box is None:
            return
        for child in box.winfo_children():
            child.destroy()
        if profile is None:
            profile = self._active_profile()
        try:
            done, total = self.progress_map.get_location_progress("desert", profile)
        except Exception:
            done, total = (0, 0)
        p = self.palette
        for heading, value in profile_summary(self.current_user, profile, (done, total)):
            ctk.CTkLabel(box, text=heading, anchor="w",
                         font=theme.FONT_SECTION,
                         text_color=p["muted"]).pack(anchor="w", padx=6, pady=(10, 0))
            ctk.CTkLabel(box, text=str(value), anchor="w", justify="left",
                         wraplength=520, font=theme.FONT_UI,
                         text_color=p["text"]).pack(anchor="w", padx=6)

    def _refresh_side_views(self):
        """Обновить «Карту» и «Профиль» (после смены ученика и т. п.)."""
        try:
            profile = self._active_profile()
            if getattr(self, "map_view", None) is not None:
                self.map_view.refresh(profile)
            self._refresh_profile_tab(profile)
        except Exception as exc:
            print(f"⚠️ Карта/профиль не обновились: {exc}")

    def _on_tab_changed(self, *_args):
        """Переключение вкладок: пауза робота и «пробуждение» карты.

        Вызывается и как command (по клику), и через trace переменной
        сегмента (программное переключение); лишние аргументы игнорируем.
        """
        if not getattr(self, "_ui_ready", False):
            return
        try:
            name = self.tabs.get()
        except Exception:
            return
        on_chat = (name == "Чат")
        if getattr(self, "character", None) is not None:
            try:
                # робот «дышит» только на вкладке «Чат» (карта — без анимаций)
                self.character.start_idle() if on_chat else self.character.stop_idle()
            except Exception:
                pass
        if getattr(self, "map_view", None) is not None:
            # карта рисуется и пульсирует ТОЛЬКО когда её видно
            self.map_view.set_active(name == "Карта")
            if name == "Карта":
                self.map_view.refresh(self._active_profile())
        if name == "Профиль":
            self._refresh_profile_tab()

    def on_point_click(self, point_id):
        """Клик по кружку карты: окно блока уроков → старт выбранного урока."""
        try:
            point = self.progress_map.get_point(point_id) or {}
        except Exception:
            point = {}
        location_title = ""
        try:
            location_title = (self.progress_map.get_location("desert") or {}).get("title") or ""
        except Exception:
            pass
        chosen = None
        try:
            chosen = BlockPanel.ask(self.window, self.palette, point, location_title)
        except Exception as exc:
            print("⚠️ Окно блока не открылось: %s" % exc)
        if chosen:
            self.start_lesson(chosen, point_id)

    # =====================================================
    # ЗАНЯТИЕ по карте (lesson.py + LessonController)
    # =====================================================
    def start_lesson(self, lesson_id, point_id=None):
        """Начать занятие по уроку с карты (после выбора в окне блока)."""
        if not self.profile_ready:
            self.add_message("Джейн", SETUP_HINT)
            return None
        if self.lesson.is_active:
            self.add_message("Джейн", "⚠️ Сначала заверши текущий урок — кнопка «Выйти».")
            return None

        data = self._lesson_data(lesson_id, point_id)
        if data is None:
            self.add_message("Джейн", "⚠️ Не нашёл этот урок в учебном плане.")
            return None

        # урок «голосом» невозможен без микрофона и без распознавания
        if lesson_mod.needs_microphone(data["type"]):
            ready, message = self._microphone_ready()
            if not ready:
                self.add_message("Джейн", message)
                if self.stt_state == "loading":
                    # распознавание ещё грузится — запомним урок и начнём,
                    # как только Whisper будет готов (см. _apply_stt_state)
                    self._pending_lesson = (lesson_id, point_id)
                    self._set_status("● Готовлю распознавание…", "warn")
                return None

        self._pending_lesson = None
        return self._begin_lesson(data)

    def _lesson_data(self, lesson_id, point_id=None):
        """Данные урока и его блока из учебного плана (или None)."""
        try:
            lesson = self.progress_map.get_lesson(lesson_id) or {}
        except Exception:
            lesson = {}
        if not lesson:
            return None
        if not point_id:
            point_id = self._point_of_lesson(lesson_id)
        point = {}
        if point_id:
            try:
                point = self.progress_map.get_point(point_id) or {}
            except Exception:
                point = {}
        block_title = str(point.get("block_title") or "").strip()
        title = str(lesson.get("title") or lesson_id).strip()
        topic = " — ".join(x for x in (block_title, title) if x) or title
        lesson_type = lesson.get("type")
        return {
            "id": str(lesson.get("id") or lesson_id),
            "title": title,
            "type": lesson_type,
            "topic": topic,
            "point_id": point_id,
            "block_number": point.get("number"),
            "block_title": block_title,
            # что Джейн делает в начале: для listening — рассказывает историю
            "task": lesson_mod.opening_task(lesson_type),
            "story": lesson_mod.is_story_lesson(lesson_type),
        }

    def _point_of_lesson(self, lesson_id):
        """В каком блоке лежит урок (по данным карты)."""
        try:
            for point in self.progress_map.points_of("desert"):
                for item in self.progress_map.lessons_of(str(point.get("id"))):
                    if str(item.get("id")) == str(lesson_id):
                        return str(point.get("id"))
        except Exception:
            pass
        return None

    def _microphone_ready(self):
        """(готово?, сообщение) для уроков, где нужно говорить."""
        try:
            has_mic = self.vad.has_input_device()
        except Exception:
            has_mic = False
        if not has_mic:
            return (False, "🎤 Микрофон не найден — урок «говорение» сейчас недоступен.")
        if self.stt_ready:
            return (True, "")
        if self.stt_state == "loading":
            return (False, "⏳ Готовлю распознавание — начну урок через несколько секунд.")
        return (False, "❌ Распознавание речи недоступно — перезапусти приложение.")

    def _begin_lesson(self, data):
        """Создать сессию занятия, настроить интерфейс и начать диалог."""
        session = self.lesson.start(
            lesson_id=data["id"], point_id=data.get("point_id"),
            lesson_type=data.get("type"), title=data.get("title"),
            topic=data.get("topic"), block_number=data.get("block_number"),
            block_title=data.get("block_title"))
        if session is None:
            return None

        # занятие — это учёба: режим Джейн «урок» (без служебной строки в чат)
        self.mode = "lesson"
        self.chat.set_mode("lesson")
        try:
            self.right_panel.set_values(mode="lesson")
        except Exception:
            pass

        lesson_payload = {"title": data.get("title"), "type": data.get("type"),
                          "topic": data.get("topic"), "task": data.get("task")}
        try:
            self.chat.set_lesson(lesson_payload)
        except Exception:
            pass
        self.info_bar.clear()
        opening = "🎓 Начинаем %s (%s)." % (
            session.label(), lesson_mod.type_label(data.get("type")))
        if data.get("story"):
            opening += "\n🎧 Слушай историю, а потом перескажи её — по-русски или по-английски."
        try:
            self.reactions.reset()          # новый урок — новый счёт стараний
        except Exception:
            pass
        self.add_message("Джейн", opening)
        try:
            self.tabs.set("Чат")          # урок идёт в чате — покажем его
        except Exception:
            pass
        self.lesson_bar.set_lesson(session.label(),
                                   lesson_mod.type_label(data.get("type")),
                                   session.progress_text())
        self._apply_lesson_input_state(session)
        self._lesson_state("thinking")
        if self.server_ready:
            self._open_lesson_dialog(lesson_payload)
        else:
            # сервер молчит — ждём его («ожидание»), занятие пока «на паузе»
            self._run_when_server_ready(
                lambda: self._open_lesson_dialog(lesson_payload),
                on_timeout=self._lesson_server_timeout)
        return session

    def _open_lesson_dialog(self, lesson_payload):
        """Дать Джейн начать занятие (первая реплика урока)."""
        try:
            self.chat.begin_lesson(lesson_payload)
        except Exception as exc:
            print("⚠️ Не удалось начать занятие в чате: %s" % exc)

    def _lesson_server_timeout(self):
        """Сервер не ответил за отведённое время — занятие придётся закрыть."""
        if self.lesson.is_active:
            self.lesson.abort()

    def _apply_lesson_input_state(self, session):
        """Включить/выключить текст и запись по типу урока."""
        if session is None or not session.is_active:
            self.input_bar.set_locked(False)
            self.control_bar.set_record_enabled(True)
            return
        if session.allows_text():
            self.input_bar.set_locked(False)
        else:
            self.input_bar.set_locked(True, lesson_mod.locked_hint(session.lesson_type))
        self.control_bar.set_record_enabled(session.allows_voice())

    def _lesson_state(self, state):
        """Состояние робота во время занятия (пока заглушка — только лог)."""
        if getattr(self, "character", None) is None:
            return
        try:
            self.character.set_state(state)
        except Exception:
            pass

    # ---------- колбэки занятия ----------
    def _on_lesson_started(self, session):
        self.lesson_bar.set_lesson(session.label(),
                                   lesson_mod.type_label(session.lesson_type),
                                   session.progress_text())

    def _on_lesson_reply(self, state):
        if state:
            self.lesson_bar.set_progress("%d/%d" % (state["replies"], state["target"]))

    def _on_lesson_finished(self, session):
        """Урок доигран до конца: засчитываем и обновляем карту."""
        user_id = (self.current_user or {}).get("id")
        try:
            profile_store.record_lesson_completed(session.lesson_id, user_id)
        except Exception as exc:
            print("⚠️ Не удалось засчитать урок: %s" % exc)

        text = "🎉 Урок %s пройден!" % session.lesson_id
        try:
            profile = self._active_profile()
            if (session.point_id
                    and self.progress_map.get_point_state(session.point_id, profile)
                    == progress_map.COMPLETED):
                text += " Блок «%s» пройден целиком!" % (session.block_title or session.point_id)
        except Exception:
            pass
        self.add_message("Джейн", text)
        self._end_lesson()
        self._refresh_side_views()
        self._lesson_state("happy")

    def _on_lesson_aborted(self, session):
        """Ученик вышел раньше: урок не засчитан (прогресс уже записан)."""
        self.add_message("Джейн", "⏸ Урок прерван — он не засчитан. Ошибки из разбора сохранены.")
        self._end_lesson()

    def exit_lesson(self):
        """Кнопка «Выйти»: прервать занятие и вернуть обычный ввод."""
        session = self.lesson.current()
        if session is None or not session.is_active:
            self._end_lesson()
            return
        self.lesson.abort()

    def _end_lesson(self):
        """Свернуть интерфейс занятия (полоса, блокировка, тема промпта)."""
        self._server_task = None        # занятие закрыто — ожидание сервера не нужно
        self.lesson_bar.clear()
        self.input_bar.set_locked(False)
        self.control_bar.set_record_enabled(True)
        try:
            self.chat.set_lesson(None)
        except Exception:
            pass

    def _register_lesson_reply(self):
        """Учесть реплику ученика в занятии (голос и текст — одинаково)."""
        if self.lesson.is_active:
            try:
                self.lesson.register_reply()
            except Exception as exc:
                print("⚠️ Счёт занятия сбился: %s" % exc)

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
        mark = self.chat_view.add_message(sender, text)
        # запоминаем метку последней реплики Джейн: к ней привяжем кнопку
        # «прослушать повторно», когда озвучка этой реплики закончится
        if sender == "Джейн" and mark:
            self._jane_mark = mark

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
        if busy:
            self._character_state("thinking")      # «думает»: прищур и форма рта
        elif self._character_state() == "thinking":
            self._character_state("idle")

    # -----------------------------------------------------
    # Лицо робота: эмоции и реакции
    # -----------------------------------------------------
    def _character_state(self, state=None):
        """Поставить/прочитать состояние лица робота."""
        char = getattr(self, "character", None)
        if char is None or not getattr(char, "available", False):
            return None
        if state is None:
            return getattr(char, "state", None)
        try:
            char.set_state(state)
        except Exception as exc:
            print("⚠️ Робот: состояние не сменилось (%s)" % exc)
        return getattr(char, "state", None)

    def _start_mood_play(self, response):
        """Начать «игру лицом» по тексту ответа: настроение по предложениям."""
        try:
            import mood as mood_mod
            plan = mood_mod.plan_reply(response)
        except Exception as exc:
            print("⚠️ Настроение не разобрано: %s" % exc)
            plan = None
        self._mood_plan = plan
        self._mood_at = 0.0
        if plan is None or not plan.segments:
            self._character_state("speak_story")
            return
        self._character_state(self._mood_state(plan, 0))

    @staticmethod
    def _mood_state(plan, index):
        """Состояние лица для куска плана."""
        try:
            import character_face as cf
            segment = plan.segments[min(index, len(plan.segments) - 1)]
            return cf.state_for_mood(segment.mood, story=plan.story)
        except Exception:
            return "speaking"

    def _mood_tick(self):
        """Во время озвучки менять лицо по ходу рассказа (по времени)."""
        plan = self._mood_plan
        if plan is None or not plan.segments:
            return
        try:
            import tts
            level = float(tts.get_level())
        except Exception:
            level = 0.0
        if level <= 2.0:
            return              # тишина: лицо не трогаем (пусть доигрывает своё)
        # время «звучания» накапливаем, пока есть звук
        if level > 2.0:
            self._mood_at += 0.1
        index = 0
        left = self._mood_at
        for i, seg in enumerate(plan.segments):
            if left < seg.seconds:
                index = i
                break
            left -= seg.seconds
            index = i
        state = self._mood_state(plan, index)
        char = getattr(self, "character", None)
        if char is not None and getattr(char, "available", False):
            try:
                char.set_level(level, speaking=(level > 2.0))
                if getattr(char, "state", None) != state:
                    char.set_state(state)
            except Exception:
                pass

    def _react_to_analysis(self, result):
        """Реакция на разбор Аналитика: 3 промаха → верный ответ → похвала.

        Сначала УДИВЛЕНИЕ (1.5 с), потом ОДОБРИТЕЛЬНАЯ УЛЫБКА — как договорились.
        """
        try:
            correct = reactions.answer_is_correct(result)
            reaction = self.reactions.record(correct)
        except Exception as exc:
            print("⚠️ Реакция не сработала: %s" % exc)
            return
        if reaction:
            char = getattr(self, "character", None)
            if char is not None and getattr(char, "available", False):
                try:
                    char.play_sequence(reaction.steps)
                except Exception as exc:
                    print("⚠️ Сценарий реакции не запустился: %s" % exc)

    # -----------------------------------------------------
    # Эквалайзер «кто говорит»
    # -----------------------------------------------------
    def _visual_tick(self):
        """Опрос громкости: 0..100 от озвучки Джейн и от микрофона ученика.

        Виджет только рисует — сигнал берём из tts.get_level() (Джейн) и
        vad.get_level() (ученик). Цвет эквалайзера показывает говорящего.
        """
        try:
            jane = 0.0
            user = 0.0
            try:
                jane = float(tts.get_level())
            except Exception:
                jane = 0.0
            try:
                if self.recorder.is_recording:
                    user = float(self.vad.get_level())
            except Exception:
                user = 0.0

            if user > 2.0 and user >= jane:
                speaker, level = "user", user
            elif jane > 2.0:
                speaker, level = "jane", jane
            else:
                speaker, level = self._last_speaker, 0.0
            self._last_speaker = speaker
            self.visualizer.update_level(level, speaker)
            char = getattr(self, "character", None)
            if char is not None and getattr(char, "available", False):
                # не дёргаем лицо, если уровень почти не изменился
                if abs(level - self._last_char_level) > 1.5 or speaker != self._last_char_speaker:
                    self._last_char_level = level
                    self._last_char_speaker = speaker
                    char.set_level(level, speaking=(speaker == "jane" and level > 2.0))
            if speaker == "jane" and self._mood_plan is not None:
                self._mood_tick()
        except Exception as exc:
            print("⚠️ Эквалайзер: %s" % exc)
        try:
            self.window.after(45, self._visual_tick)   # ~22 кадра/с (дёшево)
        except Exception:
            pass

    def _on_response(self, user_text, response):
        """Ответ получен: озвучиваем, гасим эквалайзер, готовим повтор.

        Здесь же закрываем занятие, если ученик набрал нужное число реплик —
        делаем это ПОСЛЕ ответа Джейн, чтобы последняя реплика успела прозвучать.
        """
        session = self.lesson.current()
        if session is not None and session.is_active and session.should_finish:
            self.lesson.finish()

        # «актёрская игра»: настроение её собственного текста
        self._start_mood_play(response)
        is_story = bool(self._mood_plan is not None and self._mood_plan.story)
        mark = self._jane_mark
        def _after_speech(m=mark, story=is_story):
            # «доиграла»: для рассказа — закрыть глаза на 3 с (конец истории)
            self._dispatch(lambda: self._finish_speech(m, story))

        self._say(response, on_done=_after_speech)
        self.visualizer.reset()

    def _finish_speech(self, mark, story):
        """Речь Джейн закончилась: кнопка повтора и «конец рассказа»."""
        if mark:
            try:
                self.chat_view.enable_replay(mark)
            except Exception:
                pass
        if story:
            # досказала историю — закрывает глаза на пару секунд (STORY_END)
            self._mood_plan = None          # план больше не нужен
            self._character_state("story_end")

    def _replay_reply(self, text):
        """Кнопка «прослушать повторно»: озвучить ту же реплику заново."""
        self._say(text)

    # -----------------------------------------------------
    # Озвучка недоступна (edge-tts иногда отвечает 403)
    # -----------------------------------------------------
    def _notify_no_voice(self):
        """Один раз сообщить, что озвучка не работает, — чтобы не было загадки."""
        if getattr(self, "_voice_warned", False):
            return
        self._voice_warned = True
        reason = ""
        try:
            reason = tts.last_failure or ""
        except Exception:
            reason = ""
        hint = "🔇 Озвучка не работает (%s). Текст и уроки — в порядке." % (
            reason or "нет ответа от edge-tts")
        self.info_bar.set_analysis(hint)
        self._set_status("● Без озвучки", "warn")

    def _clear_no_voice(self):
        """Озвучка снова работает — снять предупреждение."""
        if getattr(self, "_voice_warned", False):
            self._voice_warned = False
            self.info_bar.set_analysis("")
            self._refresh_status()

    # =====================================================
    # «Учительский» вид: разбор Аналитика и план урока
    # =====================================================
    def _on_analysis(self, result):
        """Разбор Аналитика → тонкая строка (не в чат) + реакция робота."""
        self.info_bar.set_analysis(self._analysis_text(result))
        self._react_to_analysis(result)

    @staticmethod
    def _analysis_text(result):
        """Короткая подпись разбора: что ученик сделал, статус, ошибки, тема."""
        if not result or not result.get("ok"):
            return ""
        parts = [MOVE_TYPE_RU.get(result.get("move_type"),
                                  result.get("move_type") or "—")]
        status = MOVE_STATUS_RU.get(result.get("move_status"))
        if status:
            parts.append(status)
        errors = result.get("errors") or []
        if errors:
            parts.append("ошибок %d" % len(errors))
        topics = result.get("topics") or []
        if topics:
            parts.append(str(topics[0]))
        return " · ".join(str(p) for p in parts if p)

    def _on_plan(self, plan_text):
        """План урока построен → показать фокус урока в строке (не в чат)."""
        self.info_bar.set_plan(self._plan_info_text(plan_text))

    @staticmethod
    def _plan_info_text(plan_text):
        """Из текста плана берём первую строку («Focus: …») без префикса."""
        plan_text = str(plan_text or "").strip()
        if not plan_text:
            return ""
        first = plan_text.splitlines()[0].strip()
        if first.lower().startswith("focus:"):
            first = first.split(":", 1)[1].strip()
        return first


    def _say(self, text, on_done=None):
        """Озвучка в фоне — окно ждать не должно.

        on_done вызывается (тоже в фоне) сразу после того, как звук доиграл;
        UI-обновления внутри него обязаны уйти через dispatch в главный поток.
        """
        if not text:
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass
            return

        u = self.current_user or {}
        name = u.get("name")
        name_latin = u.get("name_latin")

        def _worker():
            try:
                ok = tts.speak(text, name=name, name_latin=name_latin)
                if ok is False:
                    # Джейн не смогла озвучить (например, edge-tts ответил 403)
                    self._dispatch(self._notify_no_voice)
                else:
                    self._dispatch(self._clear_no_voice)
            finally:
                if on_done:
                    try:
                        on_done()
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    # Примечание: _say объявлен выше (в блоке обратной связи), здесь пусто.

    def _on_recording_changed(self, recording):
        self.control_bar.set_recording(recording)
        # слушает ученика: улыбка, кивки, моргание
        self._character_state("listening" if recording else "idle")

    def _on_recognized(self, text, lang):
        self.current_lang = lang
        self.chat.set_language(lang)
        self.add_message("Вы (голос)", text)
        self._handle_text(text)

    def _on_server_state(self, state, message):
        self.server_state = state
        self.server_ready = (state == "ready")
        self._refresh_status()
        self._refresh_input_state()
        return state

    def _stt_hotwords(self):
        """Слова-подсказки для Whisper: имя ученика в двух формах.

        Имена — главная «жертва» распознавания («Дамиль» легко услышать как
        что-то другое). Возвращаем строку через запятую; вызывается из
        фонового потока распознавания, поэтому только ЧИТАЕМ данные.
        """
        u = self.current_user or {}
        parts = [u.get("name"), u.get("name_latin")]
        return ", ".join(p for p in parts if p)

    def _on_stt_state(self, state, message):
        """Колбэк STTEngine (из фонового потока) → в главный поток."""
        self._dispatch(lambda: self._apply_stt_state(state, message))

    def _apply_stt_state(self, state, message):
        self.stt_state = state
        self.stt_ready = (state == "ready")
        self._refresh_status()
        # урок «говорение», который ждал готовности распознавания, можно начинать
        if self.stt_ready and self._pending_lesson:
            lesson_id, point_id = self._pending_lesson
            self._pending_lesson = None
            self.window.after(200, lambda: self.start_lesson(lesson_id, point_id))

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
        if self.input_bar.is_locked:
            self.add_message("Джейн", "🎤 На этом уроке говори в микрофон — текст отключён.")
            return
        self.input_bar.clear_text()
        self.add_message("Вы", text)
        self._handle_text(text)

    def _handle_text(self, text):
        """Ввод пользователя — текстом или голосом (разницы нет).

        Сначала проверяем команду смены режима («урок», «перерыв»…):
        её выполняем локально, к модели не ходим и сервер не требуем.
        """
        # пока профиль не заполнен — общение невозможно (гейт)
        if not self.profile_ready:
            self.add_message("Джейн", SETUP_HINT)
            return
        # пользователь что-то делает — гасим текущую речь Джейн
        tts.stop()

        mode = commands.parse_mode_command(text)
        if mode is not None:
            changed = (mode != self.mode)
            self._switch_mode(mode)
            if changed:
                self._say(commands.GREETINGS.get(mode))
            return

        if self.server_ready:
            self._send_to_teacher(text)
            return
        # сервер молчит: сначала «ожидание», и только если долго — «не отвечает»
        self._run_when_server_ready(lambda: self._send_to_teacher(text))

    def _send_to_teacher(self, text):
        """Отправить реплику учителю (в занятии — учесть её в счёте)."""
        self._register_lesson_reply()
        self.chat.send(text)

    def _run_when_server_ready(self, action, on_timeout=None):
        """Выполнить действие, когда LLM-сервер ответит.

        Сначала проверяем сервер СРАЗУ (одним запросом), дальше «тикаем» по
        таймеру и читаем уже готовое состояние (монитор обновляет его в фоне).
        Сообщения: тишина → «ожидание» → (если долго) «не отвечает».
        """
        if self.server_ready:
            self._safe_call(action)
            return
        try:
            if self.check_server() == "ready":
                self._safe_call(action)
                return
        except Exception as exc:
            print("⚠️ Не удалось опросить сервер: %s" % exc)

        if self._server_task is not None:
            return                      # ожидание уже идёт — не плодим их
        self._server_task = {
            "action": action,
            "on_timeout": on_timeout,
            "waiter": ServerWaiter(
                getattr(config, "SERVER_WAIT_SECONDS", 15.0),
                getattr(config, "SERVER_WAIT_POLL_MS", 800),
                getattr(config, "SERVER_ANNOUNCE_AFTER", 1.5)),
        }
        self._poll_server_task()

    def _poll_server_task(self):
        """Шаг ожидания сервера (вызывается по таймеру)."""
        task = self._server_task
        if task is None:
            return
        status = task["waiter"].step(bool(self.server_ready))
        if status == ServerWaiter.READY:
            self._server_task = None
            self._safe_call(task["action"])
            return
        if status == ServerWaiter.TIMEOUT:
            self._server_task = None
            self.add_message("Джейн", NOT_READY_OFFLINE)
            self._set_status("● Сервер не отвечает", "err")
            if task.get("on_timeout") is not None:
                self._safe_call(task["on_timeout"])
            return
        if status == ServerWaiter.ANNOUNCE:
            self._set_status("● Ожидаю сервер…", "warn")
            self.add_message("Джейн", "⏳ Ожидаю LLM-сервер…")
        try:
            self.window.after(int(task["waiter"].poll_ms), self._poll_server_task)
        except Exception:
            self._server_task = None

    @staticmethod
    def _safe_call(fn):
        """Вызвать fn, не давая исключению сломать окно."""
        if fn is None:
            return
        try:
            fn()
        except Exception as exc:
            print("⚠️ Отложенное действие не выполнилось: %s" % exc)

    def _start_recording(self):
        """Нажали «Запись»: пишем, пока кнопка нажата (push-to-talk)."""
        if self.recorder.is_recording:
            return
        tts.stop()              # начинаем запись — гасим речь Джейн
        self.recorder.start()

    def _stop_recording(self):
        """Отпустили кнопку (или сработала страховка) — стоп и распознавание."""
        if not self.recorder.is_recording:
            return
        self.recorder.stop()

    def _on_global_release(self, _event=None):
        """Отпускание ЛЮБОЙ кнопки мыши: если пишем — останавливаем запись."""
        self._stop_recording()

    def toggle_recording(self):
        """Переключатель (для совместимости): старт/стоп записи."""
        if self.recorder.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def clear_chat(self):
        if self.lesson.is_active:
            self.lesson.abort()
            self.lesson.reset()
        self.chat_view.clear()
        self.chat.clear_history()
        self.info_bar.clear()
        self.lesson_bar.clear()
        self.input_bar.set_locked(False)
        self.control_bar.set_record_enabled(True)

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

        new_model = self.right_panel.get_model()
        if new_model and new_model != self.current_model_id:
            self._apply_model(new_model)

        self.close_panel()

    def _apply_model(self, model_id):
        """Смена модели: сохранить выбор и перезапустить сервер в фоне.

        Перезапуск долгий (~30 с) — делаем его в отдельном потоке, а статус
        обновляем через dispatch, чтобы окно не морозилось.
        """
        settings_store.set_selected_model(model_id)
        self.current_model_id = model_id
        label = next((m["label"] for m in model_registry.available_models()
                      if m["id"] == model_id), model_id)
        self._set_status("● Загружаю модель…", "warn")
        self.add_message("Джейн", "🔄 Перезапускаю модель: %s. Это займёт до минуты." % label)
        threading.Thread(target=self._restart_model_worker, args=(model_id,),
                         daemon=True).start()

    def _restart_model_worker(self, model_id):
        def _progress(_state, message, elapsed):
            self._dispatch(lambda: self._set_status(
                "● %s (%.0f с)" % (message, elapsed), "warn"))
        ok = server_manager.restart_server(model_id, on_progress=_progress)
        self._dispatch(lambda: self._model_restart_done(ok))

    def _model_restart_done(self, ok):
        self.check_server()
        if ok:
            self.add_message("Джейн", "✅ Модель загружена.")
        else:
            self.add_message("Джейн", "⚠️ Модель не загрузилась. "
                                      "Подробности: logs\\llama-server.log")

    def _switch_mode(self, mode):
        """Единая точка смены режима: панель настроек и голосовые команды.

        Раньше переключение жило только в консольной версии
        (profile_manager.switch_to_teacher/friend), теперь — здесь.
        """
        self.mode = mode
        self.chat.set_mode(mode)
        self.right_panel.set_values(mode=mode)
        self.info_bar.clear()
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
        if self.character is not None:
            self.character.apply_theme(p["chat_bg"])
        self.input_bar.apply_theme(p)
        self.control_bar.apply_theme(p)
        self.info_bar.apply_theme(p)
        self.lesson_bar.apply_theme(p)
        self.right_panel.apply_theme(p)
        self.users_panel.apply_theme(p)

        # вкладки и «Карта» красятся вручную (у них свои цвета сегментов)
        try:
            self.tabs.configure(
                fg_color=p["surface"],
                segmented_button_fg_color=p["btn"],
                segmented_button_selected_color=p["accent"],
                segmented_button_selected_hover_color=p["accent_hover"],
                segmented_button_unselected_color=p["btn"],
                segmented_button_unselected_hover_color=p["btn_hover"],
                text_color=p["text"])
        except Exception:
            pass
        if getattr(self, "map_view", None) is not None:
            self.map_view.apply_theme(p)
        self._refresh_profile_tab()

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
        if self.character is not None:
            self.character.stop_idle()
        self.window.destroy()
