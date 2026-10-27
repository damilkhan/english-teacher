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

import os
import threading
import time
import tkinter as tk

import customtkinter as ctk

import audio_vad
import character
import commands
import config
import exam as exam_mod
import gaps
import glossary
from controllers.glossary_controller import GlossaryController
import lesson as lesson_mod
import lesson_summary
import model_registry
import photo_check
import picture_task
import profile_store
import ru_text
import stats_store
import progress_map
import reactions
import server_manager
import translate
import settings_store
import stt_engine
import theme
import tts
import user_manager
import vocabulary
from controllers.chat_controller import ChatController
from controllers.dispatcher import Dispatcher
from controllers.lesson_controller import LessonController
from controllers.server_waiter import ServerWaiter
from controllers.level_test_controller import LevelTestController
from controllers.recording_controller import RecordingController
from controllers.server_monitor import ServerMonitor
from controllers.vocabulary_controller import VocabularyController
from llm_client import LLMClient
from roles.analyst import Analyst
from roles.planner import Planner
from ui import fonts as ui_fonts
from ui import gradient
from ui.first_run import FirstRunForm
from ui.panels.block_panel import BlockPanel, VOCAB_RESULT
from ui.panels.boot_panel import BootPanel
from ui.panels.level_test_panel import LevelTestPanel
from ui.panels.settings_panel import SettingsPanel
from ui.panels.users_panel import UsersPanel
from ui.panels.vocab_panel import VocabPanel
from ui.widgets.chat_view import ChatView
from ui.widgets.control_bar import ControlBar
from ui.widgets.info_bar import InfoBar
from ui.widgets.input_bar import InputBar
from ui.widgets.hint_bar import HintBar
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

SETUP_HINT = ("✋ Чтобы начать, заполни профиль: имя и пол. "
              "Нажми «👥 Пользователи», затем ✏️ у активного профиля.")
LEVEL_TEST_NOTE = "🎯 Уровень определён: %s. Подстрою уроки под него."
NOT_READY_LOADING = "⏳ Модель ещё загружается — подожди несколько секунд и попробуй снова."
NOT_READY_OFFLINE = "❌ LLM-сервер не отвечает. Подробности в logs\\llama-server.log"
LOCKED_TEXT_NOTE = ("🎤 На этом уроке говори в микрофон: английское сообщение не "
                    "отправляется. Не помнишь слово — напиши его по-русски и нажми "
                    "«💡 Перевести».")
BLOCK_LOCKED_NOTE = "🔒 Этот блок ещё закрыт — сначала пройди предыдущий."

LESSON_LOCKED_NOTE = "🔒 Этот урок ещё закрыт — начни с открытого."

EXAM_NO_HINT_NOTE = ("🎯 Идёт экзамен: подсказок нет. Скажи ответ вслух — "
                     "слово по-русски здесь не подскажу.")
ALL_LESSONS_NOTE = ("🎉 Вся карта «Пустыня» пройдена! Дальше — свободное общение: "
                   "говорим на любые темы.")

HERO_HEIGHT = 92
PANEL_WIDTH = 400     # ширина правой панели: даже длинное «Имя Фамилия» видно целиком
TITLE_POS = (22, 17)        # заголовок шапки (x, y) внутри шапки
SUBTITLE_POS = (24, 50)     # подпись под заголовком
BADGE_MARGIN = 18           # отступ пилюли от правого края шапки
TITLE_EMOJI = "🎙️"
TITLE_TEXT = "ИИ-ПРЕПОДАВАТЕЛЬ"
# Заголовок окна и подпись шапки собираются из НАЗВАНИЯ приложения
# (config.APP_NAME) и имени преподавателя у активного ученика (поле профиля
# teacher_name, пусто → config.TEACHER_NAME). Раньше здесь были зашиты
# «English Teacher — Jane» и «Джейн · локальный преподаватель».


def window_title(teacher_name=""):
    """Заголовок окна: «Verbot — ИИ-преподаватель английского» (или с именем).

    Если имя преподавателя совпадает с названием приложения (обычный случай,
    имя по умолчанию), второй раз его не пишем: «Verbot — Verbot» выглядит
    как ошибка.
    """
    app = str(getattr(config, "APP_NAME", "Verbot") or "Verbot").strip() or "Verbot"
    teacher = str(teacher_name or "").strip() or app
    if teacher.lower() == app.lower():
        return "%s — ИИ-преподаватель английского" % app
    return "%s — %s" % (app, teacher)


def subtitle_text(teacher_name=""):
    """Подпись шапки, пока имени ученика нет: «Verbot · локальный преподаватель…»."""
    teacher = str(teacher_name or "").strip() or str(
        getattr(config, "TEACHER_NAME", "Verbot") or "Verbot").strip() or "Verbot"
    return "%s · локальный преподаватель английского" % teacher
INITIAL_STATUS = ("● Проверяю сервер…", "muted")
CHARACTER_WIDTH = 300        # ширина робота по умолчанию, px (см. config.ROBOT_WIDTH)
ROBOT_GAP = 12              # воздух между роботом и блоком ввода/кнопок
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
    avatar = user_manager.display_avatar(user.get("avatar"))
    out.append(("Ученик", "%s %s" % (avatar, name)))
    out.append(("Уровень", user_manager.level_label(user.get("level"))))
    try:
        done, total = int(map_progress[0]), int(map_progress[1])
    except Exception:
        done, total = 0, 0
    out.append(("Карта «Пустыня»", "пройдено блоков: %d из %d" % (done, total)))
    out.append(("Занятий с %s" % user_manager.teacher_name(user),
                str(profile.get("total_lessons", 0))))

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

    vocab = [card for card in (profile.get("vocabulary") or [])
             if isinstance(card, dict)]
    if vocab:
        known = vocabulary.stats(vocab)
        out.append(("Слова", "всего %d · к повторению %d · выучено %d"
                    % (known["total"], known["due"], known["learned"])))

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


# Просьба рассказать историю/сказку — включает «режим рассказа» (в конце
# Джейн закрывает глаза на пару секунд). Ищем и по-русски, и по-английски.
import re as _re

_STORY_RE = _re.compile(r"\b(story|stories|tale|fairytale|fairy\s*tale|"
                         r"сказк|истори|расскаж|поведа)", _re.IGNORECASE)


def _asks_for_story(text):
    """Просит ли ученик рассказать историю/сказку."""
    return bool(_STORY_RE.search(str(text or "")))

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

        # Шрифт чата подключаем ДО создания окна: Tk читает список семейств
        # один раз, и шрифт, добавленный позже, может остаться невидимым.
        # Режим FR_PRIVATE — только для нашего процесса, в систему не ставим.
        try:
            ui_fonts.register_font(getattr(config, "CHAT_FONT_FILE", ""))
        except Exception as exc:
            print("ℹ️ Шрифт чата не подключён: %s" % exc)

        self.current_theme = config.DEFAULT_THEME
        self.palette = theme.palette(self.current_theme)
        self.mode = config.DEFAULT_MODE
        self.current_model_id = settings_store.get_selected_model_id()
        self.current_lang = "en"
        self._jane_mark = None     # метка последней реплики Джейн (для повтора)
        # метка ВСТУПИТЕЛЬНОЙ реплики: по ней после теста уровня ЗАМЕНЯЕТСЯ
        # строка «уровень пока не определён» (второй реплики не появляется)
        self._greeting_mark = None
        self.panel_visible = False
        self.active_panel = None      # "settings" | "users" | None
        self.busy = False
        self._speech_busy = False    # идёт озвучка: модель на перевод не зовём
        # §41: состояние, которое МЫ поставили ради движения рта во время речи
        self._face_auto = None
        self.server_state = "offline"
        self.server_ready = False
        self.stt_state = "loading"      # loading | ready | error
        self.stt_ready = False
        self._status_text, self._status_color = INITIAL_STATUS
        self._last_speaker = "jane"     # чей цвет на эквалайзере
        self._last_char_level = -1.0    # последний уровень, отданный лицу
        self._last_char_speaker = ""
        self._story_end_at = 0.0      # когда закончили рассказ (защита от повтора)
        # «Сейчас идёт рассказ»: включается уроком-аудированием ИЛИ просьбой
        # ученика («расскажи историю»). Только тогда в конце речи Джейн
        # закрывает глаза на 3 с — иначе это делал бы любой длинный ответ.
        self._story_context = False
        self.reactions = reactions.ReactionTracker()   # 3 промаха → похвала
        self._mood_plan = None          # план эмоций текущей реплики
        # лицо во время речи меняется по КОЛБЭКАМ из tts.py (начало звука
        # очередного куска), поэтому «сколько уже прозвучало» не считаем
        # эталон для сверки произношения: последняя английская подсказка
        # переводчика (ученик должен произнести её вслух) и время её появления
        self._pron_ref = ""
        self._pron_at = 0.0
        # (слово, значение) карточки словаря, чей пример стал эталоном:
        # при вердикте GOOD именно ей начисляем «+1» (см. _vocabulary_success)
        self._pron_card = None
        self._hero_fonts = {}      # заполним ниже, после создания окна

        # ---------- окно ----------
        self.window = ctk.CTk()
        self.window.title(window_title())
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
        self.window.title(self.window_title())   # имя преподавателя из профиля
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
        # перевод RU→EN для подсказки (наша же модель: ~0.3 с на фразу)
        self.translator = translate.Translator(
            self.llm, max_tokens=getattr(config, "TRANSLATE_MAX_TOKENS", 90))
        # подсказки-переводы по наведению (25.10.2026): словарь в памяти +
        # файловый кэш data/glossary.json; модель зовётся ТОЛЬКО в паузах
        self.glossary = glossary.Glossary(llm=self.llm)
        self.glossary_controller = GlossaryController(
            self.glossary, is_idle=self._glossary_idle)

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

        # ---------- повторение слов (окно «Повторение», этап B) ----------
        # Заход собирает VocabularyController (без Tk), окно только показывает.
        # Открывает его сама Джейн при запуске — см. maybe_review_vocabulary.
        self.vocab = VocabularyController(user_id=self.current_user["id"])
        self.vocab_panel = None        # открытое окно повторения (или None)
        self._vocab_wanted = False     # повторение ждёт готовности распознавания
        # окно открыто ПОСЛЕ автозапуска (при старте) — урок взведём, когда
        # его закроют. Для захода с карты этот флаг остаётся False.
        self._arm_after_vocab = False

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
        # Автозапуск урока (Джейн сама ведёт занятие): взведён — следующая
        # реплика ученика начнёт следующий урок по карте (решение §14.5).
        self._auto_lesson_armed = False
        self._auto_lesson_used = False   # одна попытка за запуск
        # Отложенное действие, ждущее LLM-сервер (см. _run_when_server_ready)
        self._server_task = None
        # Задание с картинкой в конце урока: данные фото (тема, порог букв)
        # или None. Пока не None, реплика ученика проверяется по порогу и
        # в модель НЕ уходит (порог жёсткий, решение ученика 25.10.2026).
        self._picture = None
        # Ответ учителя ещё В ПУТИ: ученик отправил реплику, модель думает.
        # Если эта реплика закрывает урок, итог и задание с фото ждут её ответа
        # (баг 25.10.2026: итог влезал РАНЬШЕ реплики и обрывал озвучку).
        self._reply_in_flight = False
        self._deferred_finish = None    # сессия урока, ждущая конца ответа
        # ...и до какого момента ждём конца ОЗВУЧКИ (баг 26.10.2026: итог
        # показывался, пока реплика ещё звучала, и глушил её).
        self._deferred_deadline = None
        # §36: задания урока. _lesson_payload — словарь урока для промпта
        # (title/topic/task/exam + номер задания и фаза), _last_student_text —
        # за какую реплику пришёл разбор Аналитика (зачёт по варианту Б).
        self._lesson_payload = None
        self._last_student_text = ""

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
        # Файл прогресса заводим молча: раньше здесь появлялась третья
        # вступительная реплика «📊 Создан профиль ученика…», и чат встречал
        # ученика тремя абзацами (решение 22.10.2026 — оставить приветствие
        # и строку уровня, всё остальное лишнее).
        profile_store.ensure_profile(self.current_user["id"])
        self.check_server()
        self.monitor.start()
        self.stt.preload()                      # Whisper — в фоне, окно не ждёт
        # Соединение с edge-tts тоже «холодное» в первые секунды после запуска
        # (замер: 1-й запрос до 7 с, потом 1.0–1.3 с) — греем его ЗАРАНЕЕ,
        # иначе первая реплика Джейн обрывается долгой паузой посреди фразы.
        # Голос берём из settings.json ДО прогрева: иначе прогрев скачает
        # mp3 голосом по умолчанию, а ученик выбрал другой (26.10.2026).
        tts.set_voice(settings_store.get_voice_en())
        tts.warmup_async()
        self.window.after(60, self._redraw)     # первая отрисовка после раскладки
        self.window.after(120, self._visual_tick)   # эквалайзер: кто говорит
        self._refresh_input_state()             # чат закрыт, пока нет профиля/модели
        # неполный профиль → обязательная форма; иначе (нет уровня) — тест
        self.window.after(200, self._first_run_flow)

    # =====================================================
    # Пользователи
    # =====================================================
    @property
    def teacher_name(self):
        """Как зовут преподавателя у активного ученика (по умолчанию Verbot).

        Имя живёт В ПРОФИЛЕ (поле teacher_name): ученик называет преподавателя
        сам, и это его личный выбор. Пусто → config.TEACHER_NAME.
        """
        return user_manager.teacher_name(self.current_user)

    def window_title(self):
        """Заголовок окна для ЭТОГО ученика (лаунчер добавляет свои пометки)."""
        return window_title(self.teacher_name)

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
            self.window.after(300, lambda: self._level_test_then_vocab())
        else:
            self.window.after(300, self._review_then_arm)

    def _level_test_then_vocab(self):
        """Порядок запуска: вводный тест уровня → повторение слов.

        Тест модальный (wait_window), поэтому строка после него выполняется
        только когда окно теста закрыто — два окна не наложатся.
        """
        try:
            self.run_level_test((self.current_user or {}).get("id"))
        finally:
            self._review_then_arm()

    def _prompt_profile_setup(self):
        """Обязательная форма: без имени и пола общение с Джейн запрещено."""
        user = self.current_user or {}
        data = FirstRunForm.ask(self.window, self.palette)     # режим «первого запуска»
        if not data:
            self.add_message(self.teacher_name, SETUP_HINT)
            return

        target = user.get("id")
        if target:
            user_manager.update_user(target, dict(self._form_profile(data), complete=True))
        else:
            created = user_manager.create_user(**self._form_profile(data), complete=True)
            target = created["id"] if created else None
        if not target:
            self.add_message(self.teacher_name, SETUP_HINT)
            return

        self.current_user = user_manager.get_user(target) or self.current_user
        self.profile_ready = user_manager.is_complete(self.current_user)
        profile_store.set_active_user(target)
        profile_store.ensure_profile(target)
        self.chat.set_user(target)
        self.vocab.user_id = target       # слова копятся у нового профиля
        self.chat_view.clear()
        self.info_bar.clear()
        self._show_greeting()
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
            # как ученик называет преподавателя (пусто → config.TEACHER_NAME)
            "teacher_name": data.get("teacher_name") or "",
        }

    def _greeting(self):
        """Вступительная реплика: приветствие + строка уровня.

        Решение ученика (22.10.2026): вступительного текста было слишком много
        (три абзаца), а строка «уровень пока не определён» после теста
        оставалась висеть рядом с новой «уровень определён: A2». Теперь две
        строки, и строка уровня ЗАМЕНЯЕТСЯ на месте (см.
        _update_greeting_level), а не дописывается второй репликой.
        """
        u = self.current_user or {}
        text = (f"{user_manager.display_avatar(u.get('avatar'))} Привет, "
                f"{u.get('name') or 'друг'}! "
                f"Я {self.teacher_name}, твой преподаватель английского.")
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
            return subtitle_text(self.teacher_name)
        sub = "%s %s" % (user_manager.display_avatar(u.get("avatar")), name)
        sub += " · уровень %s" % user_manager.level_label(u.get("level"))
        return sub

    def _refresh_hero(self):
        """Шапка — КАРТИНКА (кэш _hero_cache): после смены данных сбрасываем кэш."""
        self._hero_cache = (None, None)
        try:
            self._redraw()
        except Exception as exc:
            print(f"⚠️ Шапка не обновилась: {exc}")

    def select_user(self, user_id, force=False):
        """Сделать профиль активным: контроллер, история и прогресс — его.

        force=True — перечитать профиль, даже если id СОВПАДАЕТ. Это нужно
        после удаления: новый профиль занимает освободившийся слот и получает
        тот же id, а прежняя проверка «id тот же» молча выходила — в памяти
        оставался УДАЛЁННЫЙ ученик (в шапке висел его уровень, история и
        прогресс не переключались).
        """
        if not force and user_id == (self.current_user or {}).get("id"):
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
        self._story_context = False
        self._vocab_wanted = False
        self._arm_after_vocab = False
        self._auto_lesson_armed = False   # у нового ученика свой автозапуск
        self._auto_lesson_used = False
        self.vocab.user_id = user_id      # слова следующего ученика — его
        # имя преподавателя живёт в ПРОФИЛЕ: у другого ученика оно может быть
        # своим, поэтому заголовок окна обновляем вместе со всем остальным
        self.window.title(self.window_title())
        self.chat_view.clear()
        self.info_bar.clear()
        self._show_greeting()
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
        if not created:
            # профиль не сохранился — не молчим, иначе выглядит как «не нажалось»
            self.add_message(
                self.teacher_name,
                "⚠️ Не удалось сохранить профиль. "
                "Проверь папку profiles\\ и попробуй ещё раз.")
            return
        self.select_user(created["id"], force=True)
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
            self.add_message(self.teacher_name, "✅ Профиль обновлён.")
            self.window.title(self.window_title())   # имя преподавателя могло измениться
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
            if created is None:
                # профиль так и не создался — говорим прямо, а не молчим
                self.add_message(
                    self.teacher_name,
                    "⚠️ Не удалось сохранить профиль. "
                    "Проверь папку profiles\\ и попробуй ещё раз.")
                if self.users_panel is not None:
                    self.users_panel.refresh(None)
                return
            remaining = [created]

        if was_active and remaining:
            # force: новый профиль занимает освободившийся слот (тот же id);
            # без этого в памяти оставался удалённый ученик с его уровнем
            self.select_user(remaining[0]["id"], force=True)
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
            # Строку уровня меняем ПРЯМО В ПРИВЕТСТВИИ: раньше рядом с
            # «уровень не определён» появлялась вторая реплика «уровень
            # определён: A2», и в чате висели два противоположных сообщения.
            # Отдельная реплика остаётся только если приветствия нет
            # (например, чат очистили или уровень перепроходят позже).
            if not self._update_greeting_level():
                self.add_message(self.teacher_name, LEVEL_TEST_NOTE % level)
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

        # Приветствие показываем НЕ через параметр greeting: нам нужна его
        # метка, чтобы потом заменить строку уровня в этом же сообщении.
        self.chat_view = ChatView(self.chat_tab, p, on_replay=self._replay_reply,
                                  on_hover_word=self._hover_translation,
                                  on_speak_word=self._speak_word)

        # ---------- нижняя часть вкладки «Чат» ----------
        # Решение ученика 23.10.2026: робот живёт ПОД чатом отдельным блоком
        # справа, а поле ввода и кнопки уезжают влево (config.ROBOT_IN_CHAT =
        # False). Раньше робот лежал ПОВЕРХ чата, и реплики обтекали его —
        # правый край текста менялся при прокрутке, а полоса прокрутки
        # пряталась под роботом.
        self.bottom_row = ctk.CTkFrame(self.chat_tab, fg_color="transparent")
        self.input_control = ctk.CTkFrame(self.bottom_row, fg_color="transparent")
        self.input_control.pack(side="left", fill="both", expand=True)

        # ---------- полоса идущего занятия ----------
        # «🎓 Урок 1.1 · Hello / Hi · говорение · 4/12  [Выйти]» живёт В
        # КОЛОНКЕ ВВОДА, над полем: появляясь, она отнимает высоту у поля,
        # а не у чата (решение ученика 23.10.2026).
        self.input_bar = InputBar(self.input_control, p, on_send=self.send_text)
        self.lesson_bar = LessonBar(self.input_control, p,
                                    on_exit=self.exit_lesson,
                                    before=self.input_bar)
        self.control_bar = ControlBar(self.input_control, p,
                                      on_record=self._start_recording,
                                      on_record_release=self._stop_recording,
                                      on_settings=self.open_panel,
                                      on_clear=self.clear_chat,
                                      on_users=self.open_users_panel)
        # Кнопки — в самый низ, поле ввода — над ними.
        # ВАЖНО: поле ввода растягивается (expand=True). Колонка ввода по
        # высоте равна роботу (161 px), а поле (52) и кнопки (42) занимали
        # только 102 px — над полем оставалась пустая полоса 59 px, ученик
        # видел её как «провал» между полосой урока и полем ввода.
        # Теперь пустоту забирает само поле: высота = колонка − кнопки.
        self.control_bar.pack(side="bottom", fill="x", pady=(8, 0))
        self.input_bar.pack(side="bottom", fill="both", expand=True)

        # ---------- робот-персонаж (idle-анимация) ----------
        # Робот — украшение: его сбой не должен ломать окно, поэтому весь
        # блок в try/except (см. _build_character).
        self.character = None
        self.robot_host = None
        self._build_character(p)
        self._show_greeting()          # первая реплика (её метку запоминаем)

        # ---------- тонкая строка «учительского» вида ----------
        # Разбор Аналитика и фокус плана урока — ОТДЕЛЬНОЙ полосой над
        # полем ввода (в чат такие служебные строки не пишем). Виджет сам
        # прячется, пока данных нет, поэтому при старте её не видно.
        self.info_bar = InfoBar(self.chat_tab, p, before=self.chat_view)

        # ---------- подсказка перевода (RU → EN) ----------
        # English-вариант фразы ученика. Отправки нет: ученик сам решает.
        # Кнопки-динамика больше нет — произношение слушают КЛИКОМ по слову
        # или примеру (см. ui/widgets/hint_bar.py).
        self.hint_bar = HintBar(self.chat_tab, p,
                                on_insert=self._hint_insert,
                                on_listen=self._hint_listen,
                                before=self.chat_view,
                                on_close=self._pron_forget)

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

        # ---- вкладка «Чат»: нижний ряд прижат к низу, чат растёт ----
        self.bottom_row.pack(side="bottom", fill="x", padx=6,
                             pady=(0, theme.CARD_PAD - 6))

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
                                         model=self.current_model_id,
                                         voices=tts.voices(), voice=tts.VOICE_EN)

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

    def _build_character(self, p):
        """Создать робота ПОД чатом, справа от поля ввода и кнопок.

        Решение ученика 23.10.2026: робот больше не лежит поверх чата.
        Поэтому чат не знает про робота вообще (нет ни обтекания, ни отступа
        под полосу прокрутки) — облачка занимают всю ширину.

        Любая ошибка (нет картинки, нет слоёв лица) не должна ломать окно:
        ученик просто останется без робота.
        """
        width = int(getattr(config, "ROBOT_WIDTH", CHARACTER_WIDTH) or CHARACTER_WIDTH)
        try:
            # Фон блока — как у карточки: Tk не умеет прозрачность, иначе
            # Canvas робота нарисовал бы прямоугольник другого цвета.
            # Размер блока = reserve робота, поэтому рисунок встаёт ровно.
            self.robot_host = ctk.CTkFrame(self.bottom_row, fg_color=p["surface"],
                                           corner_radius=0, width=1, height=1)
            # anchor="s": робот прижат к НИЗУ строки. Без этого pack центрирует
            # его по вертикали, и под роботом остаётся пустое место (замечание
            # ученика 23.10.2026: «слишком высоко, под ним пусто»).
            self.robot_host.pack(side="right", anchor="s", padx=(ROBOT_GAP, 0))
            self.robot_host.pack_propagate(False)
            # gap=0: без отступа под роботом (картинка уже обрезана по
            # видимому содержимому, см. character.Character._measure_ink)
            self.character = character.Character(self.robot_host, width=width,
                                                 dispatch=self._dispatch, gap=0)
            if self.character.available:
                reserve_w, reserve_h = self.character.reserve
                self.robot_host.configure(width=reserve_w, height=reserve_h)
                self.character.start_idle()
        except Exception as exc:
            print("⚠️ Робот-персонаж не подключился: %s" % exc)
            self.character = None

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
        """Вкладка «Карта»: карта локации, где ученик сейчас.

        Стартуем не всегда с «Пустыни», а с первой НЕпройденной локации
        (см. ProgressMap.first_open_location): ученику показывают его место
        в программе. Переключение ◀ ▶ — на самой карте.
        """
        try:
            start_location = self.progress_map.first_open_location(
                self._active_profile()) or "desert"
        except Exception:
            start_location = "desert"
        self.map_view = MapView(self.map_tab, self.palette,
                                location_id=start_location,
                                on_point_click=self.on_point_click,
                                map_obj=self.progress_map,
                                on_location_change=self._on_location_change)
        self.map_view.pack(fill="both", expand=True, padx=4, pady=4)
        self.map_view.set_active(False)      # стартовая вкладка — «Чат»

    def _on_location_change(self, location_id):
        """Ученик посмотрел другую локацию: запоминаем выбор до сессии."""
        self._map_location = location_id

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
            profile = profile_store.load((self.current_user or {}).get("id")) or {}
        except Exception:
            return {}
        # Уровень живёт в профиле УЧЕНИКА (user_manager), а карте он нужен
        # рядом с прогрессом: локации ниже уровня считаются пройденными
        # (progress_map.skipped_lessons, решение 25.10.2026). Это КОПИЯ для
        # чтения — файл прогресса не меняется.
        if isinstance(profile, dict):
            profile = dict(profile)
            profile["level"] = (self.current_user or {}).get("level")
        return profile

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
        self._build_stats_section(box, p, profile)

    def _build_stats_section(self, box, p=None, profile=None):
        """«Статистика» в профиле: таблица «Правило · Раз · Примеры» (§46).

        Считаем по базе stats_store (SQLite), а не по JSON: в JSON история
        обрезана до 20 записей на тип, а карте пробелов нужен весь счёт.
        Сетка из CTkLabel, НЕ treeview — у нас своя тёмная тема и шрифты.
        Красный счёт = правило встречалось 2+ раза (пробел).
        """
        p = p or self.palette
        user_id = (self.current_user or {}).get("id")
        try:
            # первый заход: перенести ошибки из JSON в таблицу (§46), иначе
            # ученик увидит «пусто» при 20 записанных ошибках в профиле
            stats_store.ensure_migrated(
                profile if profile is not None else self._active_profile(), user_id)
        except Exception as exc:
            print("Статистика: перенос из профиля не удался (%s)" % exc)
        try:
            rows = gaps.table_rows(user_id)
        except Exception as exc:
            print("Статистика не прочитана: %s" % exc)
            rows = []
        ctk.CTkLabel(box, text="📊 Статистика", anchor="w",
                     font=theme.FONT_SECTION,
                     text_color=p["muted"]).pack(anchor="w", padx=6, pady=(18, 0))
        if not rows:
            ctk.CTkLabel(box, text="Пока пусто: ошибок ещё не было.",
                         anchor="w", font=theme.FONT_UI,
                         text_color=p["text"]).pack(anchor="w", padx=6)
            return
        grid = ctk.CTkFrame(box, fg_color="transparent")
        grid.pack(anchor="w", fill="x", padx=4, pady=(2, 6))
        for col, title in enumerate(("Правило", "Раз", "Примеры")):
            ctk.CTkLabel(grid, text=title, anchor="w", font=theme.FONT_UI,
                         text_color=p["muted"]).grid(row=0, column=col, sticky="w",
                                                    padx=(0, 10), pady=(0, 4))
        for line, item in enumerate(rows, start=1):
            tally = str(item.get("count", 0))
            ctk.CTkLabel(grid, text=str(item.get("label") or item.get("rule")),
                         anchor="w", font=theme.FONT_UI,
                         text_color=p["text"]).grid(row=line, column=0, sticky="w",
                                                    padx=(0, 10))
            ctk.CTkLabel(grid, text=tally, anchor="w", font=theme.FONT_UI,
                         text_color=p["err"] if item.get("gap") else p["text"]
                         ).grid(row=line, column=1, sticky="w", padx=(0, 10))
            ctk.CTkLabel(grid, text=str(item.get("examples") or "—"), anchor="w",
                         justify="left", wraplength=300, font=theme.FONT_UI,
                         text_color=p["muted"]).grid(row=line, column=2, sticky="w")
        ctk.CTkLabel(box,
                     text="Красный счёт — пробел: правило встречалось 2+ раза. "
                          "«Прочее» пробелом не считается.",
                     anchor="w", justify="left", wraplength=520,
                     font=theme.FONT_UI,
                     text_color=p["muted"]).pack(anchor="w", padx=6, pady=(0, 4))

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

    def _block_is_locked(self, point_id, profile=None):
        """Блок закрыт? (красный жетон: предыдущий блок не пройден)"""
        profile = self._active_profile() if profile is None else profile
        try:
            return self.progress_map.get_point_state(point_id, profile) \
                == progress_map.LOCKED
        except Exception:                      # noqa: BLE001 — карта битая
            return False

    def _lesson_is_locked(self, lesson_id):
        """Урок закрыт? (предыдущий в плане ещё не пройден)"""
        try:
            return self.progress_map.get_lesson_state(
                str(lesson_id or ""), self._active_profile()) == progress_map.LOCKED
        except Exception:                      # noqa: BLE001 — карта битая
            return False

    def _block_lesson_states(self, point, profile=None):
        """{id урока: completed/unlocked/locked} для окна блока."""
        profile = self._active_profile() if profile is None else profile
        out = {}
        try:
            lessons = self.progress_map.lessons_of(str((point or {}).get("id")))
        except Exception:                      # noqa: BLE001
            return out
        for item in lessons:
            lid = str(item.get("id") or "")
            if not lid:
                continue
            try:
                out[lid] = self.progress_map.get_lesson_state(lid, profile)
            except Exception:                  # noqa: BLE001
                continue
        return out

    def on_point_click(self, point_id):
        """Клик по кружку карты: окно блока уроков → старт выбранного урока.

        Закрытый блок (красный жетон) не открывается: сначала предыдущий.
        """
        profile = self._active_profile()
        if self._block_is_locked(point_id, profile):
            self.add_message(self.teacher_name, BLOCK_LOCKED_NOTE)
            return
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
            chosen = BlockPanel.ask(self.window, self.palette, point,
                                    location_title,
                                    exams=profile_store.exam_badges(profile),
                                    states=self._block_lesson_states(point,
                                                                   profile))
        except Exception as exc:
            print("⚠️ Окно блока не открылось: %s" % exc)
        if chosen == VOCAB_RESULT:
            # нажали «📚 Повторить слова» — окно повторения вместо урока
            self.review_vocabulary()
        elif chosen:
            self.start_lesson(chosen, point_id)

    # =====================================================
    # ЗАНЯТИЕ по карте (lesson.py + LessonController)
    # =====================================================
    def start_lesson(self, lesson_id, point_id=None, student_text="",
                     auto=False):
        """Начать занятие по уроку с карты (после выбора в окне блока).

        student_text — первая реплика ученика, когда урок начинает САМА Джейн;
        auto — урок выбран автоматически по учебному плану (влияет только на
        строку в чате). Оба параметра необязательны: с карты всё как раньше.
        """
        if not self.profile_ready:
            self.add_message(self.teacher_name, SETUP_HINT)
            return None
        if self.lesson.is_active:
            self.add_message(self.teacher_name, "⚠️ Сначала заверши текущий урок — кнопка «Выйти».")
            return None

        data = self._lesson_data(lesson_id, point_id)
        if data is None:
            self.add_message(self.teacher_name, "⚠️ Не нашёл этот урок в учебном плане.")
            return None

        # закрытый урок (предыдущий не пройден) не начинаем — даже если
        # id пришёл не из окна блока (защита в глубине)
        if self._lesson_is_locked(data["id"]) and not self._test_tail_flag():
            self.add_message(self.teacher_name, LESSON_LOCKED_NOTE)
            return None

        # урок «голосом» невозможен без микрофона и без распознавания
        if lesson_mod.needs_microphone(data["type"]):
            ready, message = self._microphone_ready()
            if not ready:
                self.add_message(self.teacher_name, message)
                if self.stt_state == "loading":
                    # распознавание ещё грузится — запомним урок и начнём,
                    # как только Whisper будет готов (см. _apply_stt_state)
                    self._pending_lesson = (lesson_id, point_id)
                    self._set_status("● Готовлю распознавание…", "warn")
                return None

        self._pending_lesson = None
        return self._begin_lesson(data, student_text=student_text, auto=auto)

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
            # проверочное занятие: Джейн не учит новому, а спрашивает по блоку
            "check": lesson_mod.is_check_lesson(lesson_type),
            # экзамен: в промпт уходит блок «ровно 10 вопросов, без подсказок»
            "exam": lesson_mod.is_check_lesson(lesson_type),
            # сколько реплик ученика до автозавершения (у проверки больше)
            "reply_target": lesson.get("replies"),
            "code": lesson.get("code"),
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

    def _begin_lesson(self, data, student_text="", auto=False):
        """Создать сессию занятия, настроить интерфейс и начать диалог.

        student_text — реплика ученика, с которой начался урок (её Джейн
        сначала услышит в затравке), auto — урок выбран самой Джейн по плану.
        """
        session = self.lesson.start(
            lesson_id=data["id"], point_id=data.get("point_id"),
            lesson_type=data.get("type"), title=data.get("title"),
            topic=data.get("topic"), block_number=data.get("block_number"),
            block_title=data.get("block_title"),
            reply_target=data.get("reply_target"), code=data.get("code"))
        if session is None:
            return None

        # 🧪 ТЕСТ (временный): флаг-файл ставит урок на последний шаг
        if self._test_tail_flag():
            self._jump_to_lesson_tail(session)

        # занятие — это учёба: режим Джейн «урок» (без служебной строки в чат)
        self.mode = "lesson"
        self.chat.set_mode("lesson")
        try:
            self.right_panel.set_values(mode="lesson")
        except Exception:
            pass

        lesson_payload = {"title": data.get("title"), "type": data.get("type"),
                          "topic": data.get("topic"), "task": data.get("task"),
                          "exam": bool(data.get("check"))}
        # §36: без заданий task_prompt() пустой — словарь экзамена и
        # аудирования не меняется ни на байт.
        lesson_payload.update(session.task_prompt())
        self._lesson_payload = dict(lesson_payload)
        try:
            self.chat.set_lesson(lesson_payload)
        except Exception:
            pass
        self.info_bar.clear()
        opening = "🎓 Начинаем %s (%s)." % (
            session.label(), lesson_mod.type_label(data.get("type")))
        if auto:
            opening += "\n📚 По плану дальше — этот урок. Поехали!"
        if data.get("story"):
            opening += "\n🎧 Слушай историю, а потом перескажи её — по-русски или по-английски."
        if data.get("check"):
            opening += ("\n🎯 Это ЭКЗАМЕН по блоку: %s, подсказок нет "
                        "(даже перевода). Отвечай вслух по-английски. "
                        "Балл скажу в конце — %d из 10 нужно, чтобы сдать."
                        % (ru_text.questions(exam_mod.QUESTIONS), exam_mod.PASS_SCORE))
        try:
            self.reactions.reset()          # новый урок — новый счёт стараний
        except Exception:
            pass
        self._story_context = bool(data.get("story"))   # урок-аудирование
        # ЭКЗАМЕН: своя сессия со баллом (10 вопросов, 0/1/2 за ответ).
        # Балл по ходу ученику не показываем — только в конце.
        self._exam = (exam_mod.ExamSession(session.lesson_id, session.point_id)
                      if data.get("check") else None)
        self._exam_pending = []          # тексты ответов, ждущие разбора
        self._exam_done = False
        self._exam_last = None           # итог последнего экзамена (для чата)
        # Счёт вопросов для промпта: затравка УЖЕ содержит первый вопрос,
        # поэтому перед первым ответом ученика задан 1 вопрос.
        self._sync_exam_asked()
        self.add_message(self.teacher_name, opening)
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
            self._open_lesson_dialog(lesson_payload, student_text)
        else:
            # сервер молчит — ждём его («ожидание»), занятие пока «на паузе»
            self._run_when_server_ready(
                lambda: self._open_lesson_dialog(lesson_payload, student_text),
                on_timeout=self._lesson_server_timeout)
        return session

    @staticmethod
    def _test_tail_flag():
        """Включён ли 🧪 тестовый режим «сразу конец урока» (см. config)."""
        path = getattr(config, "LESSON_TEST_TAIL_FLAG", "")
        try:
            return bool(path) and os.path.exists(path)
        except Exception:
            return False

    def _test_lesson_id(self):
        """🧪 Тест: ЛЮБОЙ обычный урок (не экзамен) — первый по карте.

        Закрытость и «пройдено» намеренно не смотрим: прогресс ученика уже
        ушёл вперёд (1.1–1.3 пройдены, дальше экзамен 1.4), а проверить надо
        ОБЫЧНОЕ занятие с тремя заданиями и фото в конце.
        """
        try:
            order = list(getattr(self.progress_map, "_lesson_order", []) or [])
        except Exception as exc:
            print("⚠️ Тест: карта не прочиталась (%s)" % exc)
            return ""
        for lesson_id in order:
            data = self._lesson_data(lesson_id) or {}
            if lesson_mod.is_check_lesson(data.get("type")):
                continue                    # экзамен пропускаем
            return lesson_id
        return ""

    def _jump_to_lesson_tail(self, session):
        """🧪 Тест: подвести урок к ПОСЛЕДНЕМУ шагу (задание + реплика).

        Нужен, чтобы проверить конец урока (итог → похвала → фото), не
        проходя три задания заново. Включается флаг-файлом, в обычной работе
        не вызывается.
        """
        try:
            if lesson_mod.is_check_lesson(session.lesson_type):
                print("⚠️ ТЕСТ: это ЭКЗАМЕН, а нужен обычный урок — пропускаю прыжок")
                return
            if session.has_tasks:
                session.tasks_done = max(0, session.tasks_total - 1)
                session.task_phase = lesson_mod.TASK_ASK
            # реплик оставляем ОДНУ до страховочного предела (не до плана 12:
            # план больше не закрывает урок, lesson.py §38)
            session.replies = max(0, session.hard_reply_limit - 1)
        except Exception as exc:
            print("⚠️ Тестовый прыжок в конец урока не удался: %s" % exc)
            return
        print("🧪 ТЕСТ: урок сразу на последнем шаге "
              "(задание %d/%d, реплика %d/%d — осталась одна)"
              % (session.task_index, session.tasks_total or 0,
                 session.replies + 1, session.hard_reply_limit))
        # Сообщение ПО-АНГЛИЙСКИ: русская реплика переключает язык урока
        # (проверено 26.10.2026 — при русском тексте ответ шёл по-русски).
        self.add_message(self.teacher_name,
                         "🧪 TEST MODE: this lesson starts at the LAST step. "
                         "Answer once and I will show the summary and the "
                         "photo task.")

    def _open_lesson_dialog(self, lesson_payload, student_text=""):
        """Дать Джейн начать занятие (первая реплика урока).

        student_text — что ученик сказал перед стартом: Джейн сначала коротко
        ответит на это, а потом поведёт урок (пусто — обычная затравка).
        """
        try:
            self.chat.begin_lesson(lesson_payload, student_text=student_text)
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
            # На экзамене словарь выключен совсем (подсказок нет) — поле
            # остаётся замком даже с русскими буквами.
            self.input_bar.set_locked(
                True, lesson_mod.locked_hint(session.lesson_type),
                allow_dictionary=session.allows_dictionary())
        self.control_bar.set_record_enabled(session.allows_voice())

    def _note_hint(self):
        """Подсказка перевода пошла в дело (ученик произнёс её).

        Нужна ИТОГУ занятия: сколько раз ученик выкручивался подсказкой.
        Вне занятия ничего не считаем.
        """
        session = self.lesson.current()
        if session is None or not session.is_active:
            return
        session.use_hint()

    def _note_mistakes(self, count):
        """Записать ошибки разбора в сессию занятия (для итога)."""
        session = self.lesson.current()
        if session is None or not session.is_active:
            return
        session.add_mistakes(count)

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
        if not state:
            return
        # §36: у урока с заданиями полоса показывает ЗАДАНИЯ («Задание 2/3»),
        # а не реплики; экзамен и аудирование — по-прежнему реплики.
        session = self.lesson.current()
        text = (session.progress_text() if session is not None
                else "%d/%d" % (state["replies"], state["target"]))
        self.lesson_bar.set_progress(text)

    def _finish_exam(self):
        """Экзамен отвечен полностью: итог, запись в профиль, закрытие."""
        exam = getattr(self, "_exam", None)
        if exam is None or getattr(self, "_exam_done", False):
            return None
        self._exam_done = True
        result = exam.result()
        self._exam_last = result
        user_id = (self.current_user or {}).get("id")
        try:
            profile_store.record_exam(exam.lesson_id, result["score"],
                                     result["passed"], user_id)
        except Exception as exc:
            print("⚠️ Не удалось записать балл экзамена: %s" % exc)
        try:
            self.lesson.finish()        # дальше — _on_lesson_finished
        except Exception as exc:
            print("⚠️ Экзамен не закрылся: %s" % exc)
        return result

    @staticmethod
    def exam_summary_text(result):
        """Итог экзамена для чата (по решению ученика — в КОНЦЕ занятия)."""
        if not result:
            return "🎯 Экзамен закончен."
        lines = ["🎯 ЭКЗАМЕН: %s" % exam_mod.score_text(result.get("score"))]
        marks = "".join(str(int(x)) for x in (result.get("answers") or []))
        if marks:
            lines.append("📋 Баллы за ответы: %s" % " ".join(marks))
        if result.get("passed"):
            lines.append("✅ Сдал! Порог %d из 10 пройден — блок засчитан."
                         % exam_mod.PASS_SCORE)
        else:
            lines.append("❌ Пока не сдал: нужно %d из 10. Пересдача — в любой "
                         "момент, ограничений нет." % exam_mod.PASS_SCORE)
        full = int(result.get("correct_full") or 0)
        lines.append("💪 Полных ответов (2 балла): %d из %d."
                     % (full, int(result.get("questions") or 0)))
        mistakes = int(result.get("mistakes") or 0)
        lines.append("📝 Ошибок в разборе: %d." % mistakes)
        failed = int(result.get("unverified") or 0)
        if failed:
            # честно: за такие ответы больше 1 балла не давали
            lines.append("🔍 Не разобрано ответов: %d (за них не выше 1 балла)."
                         % failed)
        return "\n".join(lines)

    def _on_lesson_finished(self, session):
        """Урок доигран до конца: засчитываем и обновляем карту."""
        user_id = (self.current_user or {}).get("id")
        # Ответ учителя на последнюю реплику ещё В ПУТИ: не показываем итог
        # сейчас, иначе он встанет РАНЬШЕ реплики и оборвёт её озвучку
        # (живой баг 25.10.2026: фото пришло раньше ответа, Вербот запнулся).
        # Дождёмся конца ответа — см. _run_deferred_finish.
        if getattr(self, "_reply_in_flight", False):
            self._deferred_finish = session
            try:
                self.window.after(
                    int(getattr(config, "LESSON_TAIL_FALLBACK_MS", 20000)),
                    self._run_deferred_finish)
            except Exception:
                pass
            return
        exam_result = getattr(self, "_exam_last", None)
        # на экзамене урок засчитывается ТОЛЬКО при сданном балле (решение:
        # балл нужен для перехода вперёд, пересдач без ограничений)
        if exam_result is not None and not exam_result.get("passed"):
            self.add_message(self.teacher_name, self.exam_summary_text(exam_result))
            self._end_lesson()
            self._refresh_side_views()
            self._lesson_state("thinking")
            return
        try:
            profile_store.record_lesson_completed(session.lesson_id, user_id)
        except Exception as exc:
            print("⚠️ Не удалось засчитать урок: %s" % exc)

        if exam_result is not None:
            self.add_message(self.teacher_name, self.exam_summary_text(exam_result))
            self._end_lesson()
            self._refresh_side_views()
            self._lesson_state("happy")
            return

        # Итог обычного занятия (25.10.2026): счётчики копились в сессии,
        # но нигде не показывались. Балла тут нет — только реплики,
        # подсказки, ошибки и похвала; подсказки НЕ наказывают.
        block_done = ""
        try:
            profile = self._active_profile()
            if (session.point_id
                    and self.progress_map.get_point_state(session.point_id, profile)
                    == progress_map.COMPLETED):
                block_done = session.block_title or session.point_id
        except Exception:
            block_done = ""
        text = lesson_summary.summary_text(session, block_title=block_done)
        self.add_message(self.teacher_name, text)
        # Голосом — короткая АНГЛИЙСКАЯ похвала: русский итог английским
        # голосом читать нельзя (цель проекта — говорение).
        praise = lesson_summary.praise_text(session)
        self.add_message(self.teacher_name, praise)
        # Похвала — тоже ПОСЛЕ речи: tts.speak() глушит текущую реплику, и
        # последний ответ обрывался на полуслове (баг 26.10.2026).
        if getattr(self, "_speech_busy", False):
            self._say_after_current(praise)
        else:
            self._say(praise)
        self._end_lesson()
        self._refresh_side_views()
        self._lesson_state("happy")
        # Задание с картинкой — В КОНЦЕ урока (решение ученика): фото
        # приходит репликой преподавателя, ответ голосом или письмом.
        # Выгружаем ТОЛЬКО когда Вербот досказал: иначе фото и просьба
        # влезали посреди реплики/похвалы (баг 26.10.2026).
        self._wait_for_speech(self._start_picture_task)

    # ---------- задание с картинкой ----------
    def _picture_level(self):
        """Уровень ученика для порога букв ("" → порог как у A2)."""
        return (self.current_user or {}).get("level") or ""

    def _start_picture_task(self):
        """Показать фото и включить порог букв. Одно фото за заход.

        Ответ принимается и голосом, и письмом — путь один (текст
        реплики), поэтому проверка тоже одна (_picture_reply).
        """
        task = picture_task.describe_task(self._picture_level())
        if not task:
            print("ℹ️ Фото для задания не найдено (§18: assets/pictures)")
            return False
        self._picture = task
        # Текст задания — ПО-АНГЛИЙСКИ (просьба ученика 26.10.2026):
        # русская реплика учителя в истории переключает урок на русский.
        text = ("📷 New task: describe what you see in the photo. "
                "Say or write at least %d letters."
                % task["threshold"])
        mark = self.add_message(self.teacher_name, text, picture=task["path"])
        try:
            self.input_bar.set_counter(task["threshold"])
        except Exception:
            pass
        # Просьбу говорим ПОСЛЕ текущей речи (иначе обрываем её на полуслове),
        # а у самой реплики появляется значок 🔊 — как у прочих ответов (§43).
        self._say_after_current(
            "New task. Describe what you see in the photo. Say or write at"
            " least %d letters." % task["threshold"], mark=mark)
        return True

    def _picture_reply(self, text):
        """Проверить описание фото. True — реплику модель НЕ получает."""
        task = self._picture or {}
        level = task.get("level") or self._picture_level()
        result = picture_task.check_description(text, level)
        try:
            self.input_bar.set_counter(result["threshold"])
        except Exception:
            pass
        if result["ok"]:
            self._picture = None
            try:
                self.input_bar.clear_counter()
            except Exception:
                pass
            mark = self.add_message(
                self.teacher_name,
                "✅ Task accepted: %d letters of %d. Well done!"
                % (result["letters"], result["threshold"]))
            # Голосом тоже: раньше задание было «немым» (§43).
            self._say_after_current(
                "Task accepted. %d letters of %d. Well done!"
                % (result["letters"], result["threshold"]), mark=mark)
            # Грамматику смотрим ВДОГОНКУ и не наказываем за неё: задание уже
            # засчитано, исправленный вариант придёт отдельной репликой (§42).
            self._start_picture_check(text)
            return True
        self.add_message(self.teacher_name, self._picture_hint(result))
        return True

    def _picture_hint(self, result):
        """Почему описание не принято — простыми словами (по-английски)."""
        reason = result.get("reason")
        if reason == "repeated":
            return ("🔁 One word repeats too often (%d %%). "
                    "Say the same thing in OTHER words."
                    % int(round(result.get("top_share", 0) * 100)))
        if reason == "few_words":
            return ("🔁 Too few different words: %d, need at least %d. "
                    "Add a couple more phrases."
                    % (result.get("unique", 0), result.get("want_unique", 0)))
        missing = max(0, result["threshold"] - result["letters"])
        return ("✏️ %d letters of %d — add %d more. "
                "Say or write a couple more sentences."
                % (result["letters"], result["threshold"], missing))

    # ---------- мягкая проверка грамматики описания (§42) ----------
    def _start_picture_check(self, text):
        """Проверить грамматику описания — в ФОНЕ, после зачёта задания.

        Задание уже принято по длине (picture_task), поэтому проверка ничего
        не отменяет: она приходит вдогонку подсказкой. Модель просим вернуть
        ИСПРАВЛЕННЫЙ ТЕКСТ, изменения считает код (замер §18: так ложных
        правок почти нет).
        """
        if not getattr(config, "PICTURE_CHECK_ENABLED", True):
            return False
        if not str(text or "").strip():
            return False
        try:
            threading.Thread(target=self._picture_check_worker, args=(text,),
                             daemon=True).start()
        except Exception as exc:
            print("⚠️ Проверка грамматики не запустилась: %s" % exc)
            return False
        return True

    def _picture_check_worker(self, text):
        """Фон: один короткий запрос к модели за исправленным текстом."""
        level = (self._picture or {}).get("level") or self._picture_level()
        try:
            ok, raw = self.llm.complete(
                photo_check.build_messages(text, level),
                max_tokens=getattr(config, "PICTURE_CHECK_MAX_TOKENS", 220),
                temperature=0.0,
                timeout=getattr(config, "PICTURE_CHECK_TIMEOUT", 45))
        except Exception as exc:
            print("⚠️ Проверка грамматики: %s" % exc)
            return
        if not ok:
            print("⚠️ Проверка грамматики не удалась: %s" % raw)
            return
        self._dispatch(lambda: self._apply_picture_check(text, raw))

    def _apply_picture_check(self, text, raw):
        """Главный поток: показать исправленный текст и запомнить правки.

        Если ответ модели не похож на исправление (переписала текст, ответила
        пустым) — молчим: лучше тишина, чем чужой текст вместо правки.
        """
        data = photo_check.report(text, raw)
        if not data.get("ok"):
            print("ℹ️ Проверка грамматики: ответ модели не похож на исправление"
                  " — не показываю")
            return
        # Текст с раскраской (§43, §44): зелёным горят ТОЛЬКО слова, которые
        # изменил Вербот, и они стоят внутри предложения ученика; красные
        # ошибки — в его собственной реплике (_mark_student_text).
        mark = self.add_message(self.teacher_name, data.get("text") or "",
                                spans=data.get("spans") or [])
        spoken = data.get("spoken") or ""
        if spoken:
            self._say_after_current(spoken, mark=mark)
        self._mark_student_text(text, data)
        self._remember_photo_mistakes(text, data)
        return data

    def _mark_student_text(self, text, data):
        """Подсветить ошибки КРАСНЫМ в реплике самого ученика (§43).

        Ученик просил, чтобы ошибки сразу бросались в глаза: красным в его
        тексте и зелёным в исправлении. Если метки реплики нет (чат чистили,
        текст не совпал) — молча выходим: подсветка не обязательна.
        """
        view = getattr(self, "chat_view", None)
        if view is None or not data:
            return 0
        try:
            mark = view.last_user_mark()
            if not mark or view.message_text(mark) != text:
                return 0
            spans = photo_check.spans_for_changes(text, data.get("changes") or [])
            if not spans:
                return 0
            view.mark_message(mark, spans)
            return len(spans)
        except Exception as exc:
            print("⚠️ Подсветка ошибок в реплике ученика: %s" % exc)
            return 0

    def _remember_photo_mistakes(self, text, data):
        """Правки из описания — в профиль ученика (та же копилка ошибок)."""
        try:
            analysis = photo_check.analysis_from(data)
            user_id = (self.current_user or {}).get("id")
            profile_store.record_analysis(analysis, text, "", user_id)
        except Exception as exc:
            print("⚠️ Ошибки из описания фото не записались: %s" % exc)

    def _on_lesson_aborted(self, session):
        """Ученик вышел раньше: урок не засчитан (прогресс уже записан)."""
        self.add_message(self.teacher_name, "⏸ Урок прерван — он не засчитан. Ошибки из разбора сохранены.")
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
        self._story_context = False     # рассказ был частью урока
        self._exam = None               # экзамен закрыт вместе с занятием
        self._exam_pending = []
        self._lesson_payload = None     # §36: словарь урока больше не нужен
        self._last_student_text = ""
        try:
            self.chat.set_exam_asked(None)   # счёт вопросов экзамена сброшен
        except Exception:
            pass
        self.lesson_bar.clear()
        self.input_bar.set_locked(False)
        self.control_bar.set_record_enabled(True)
        try:
            self.chat.set_lesson(None)
        except Exception:
            pass

    def _register_lesson_reply(self, text=""):
        """Учесть реплику ученика в занятии (голос и текст — одинаково).

        На ЭКЗАМЕНЕ текст ответа откладываем: балл считается сразу после
        разбора Аналитика (он приходит чуть позже и знает ошибки), иначе
        правило «2 ошибки и больше → 1 балл» никогда бы не срабатывало.
        """
        exam = self._exam_session()
        if exam is not None and exam.is_active and str(text or "").strip():
            try:
                self._exam_pending.append(str(text))
            except Exception:
                self._exam_pending = [str(text)]
        if self.lesson.is_active:
            try:
                self.lesson.register_reply()
            except Exception as exc:
                print("⚠️ Счёт занятия сбился: %s" % exc)
        # после реплики ученика номер вопроса сдвинулся (экзамен)
        if exam is not None and exam.is_active:
            self._sync_exam_asked()

    # ---------- задания урока (§36, 26.10.2026) ----------
    def _sync_lesson_prompt(self, just_credited=False, closing=False):
        """Пересобрать словарь урока для промпта (номер задания, фаза).

        just_credited=True — задание только что засчитано: преподаватель
        должен СРАЗУ дать следующее (в этой же реплике).
        closing=True — эта реплика ЗАКРЫВАЕТ урок: спрашивать больше нельзя,
        только подтвердить ответ и похвалить (просьба ученика 26.10.2026).
        """
        session = self.lesson.current()
        payload = getattr(self, "_lesson_payload", None)
        if session is None or not isinstance(payload, dict):
            return
        merged = dict(payload)
        try:
            merged.update(session.task_prompt())
        except Exception as exc:
            print("⚠️ Задания урока не попали в промпт: %s" % exc)
            return
        if just_credited:
            merged["task_done_now"] = True
        if closing:
            merged["lesson_closing"] = True
        self._lesson_payload = merged
        try:
            self.chat.set_lesson(merged)
        except Exception:
            pass

    def _mark_lesson_closing(self):
        """Реплика закрывает урок → сказать модели «без вопросов»."""
        session = self.lesson.current()
        if session is None or not session.is_active:
            return False
        try:
            closing = bool(session.should_finish)
        except Exception:
            return False
        if not closing:
            return False
        self._sync_lesson_prompt(closing=True)
        return True

    def _credit_task_by_text(self, text):
        """Вариант В: ученик ПОВТОРИЛ исправление — засчитать задание сразу.

        Проверка текстовая (вхождение/difflib), без модели, поэтому вызывается
        ДО ответа учителя: он уже знает, что задание сдано, и даёт следующее
        в той же реплике. Синонимы («скажи иначе») этот путь не ловит — для
        них вариант Б, разбор Аналитика (_task_from_analysis).
        """
        session = self.lesson.current()
        if session is None or not session.is_active or not session.has_tasks:
            return False
        try:
            matched = session.says_fix(text)
        except Exception as exc:
            print("⚠️ Проверка повтора сбилась: %s" % exc)
            return False
        if not matched:
            return False
        return self._credit_task(session, text, marked=False)

    def _credit_task(self, session, text="", marked=False):
        """Засчитать задание: полоса, промпт, а последнее — закрыть урок."""
        try:
            session.credit_task(text, marked=marked)
        except Exception as exc:
            print("⚠️ Зачёт задания не получился: %s" % exc)
            return False
        self._sync_lesson_prompt(just_credited=True)
        try:
            self.lesson_bar.set_progress(session.progress_text())
        except Exception:
            pass
        if session.all_tasks_done:
            self._close_lesson_after_credit()
        return True

    def _close_lesson_after_credit(self):
        """Урок закрылся зачётом задания: итог — ПОСЛЕ речи учителя (§32)."""
        if getattr(self, "_speech_busy", False):
            # преподаватель ещё говорит: итог ждёт конца озвучки
            self._reply_in_flight = True
        self.lesson.credit_finished()

    def _credit_rest_tasks(self, session):
        """Урок закрывается по пределу реплик: остаток заданий — с пометкой.

        Решение ученика 26.10.2026 (вариант Б): иначе итог говорил «Заданий:
        2 из 3», а урок всё равно засчитывался — цифры не сходились.
        """
        if session is None or not getattr(session, "has_tasks", False):
            return 0
        if getattr(session, "all_tasks_done", False):
            return 0
        try:
            added = session.credit_rest(marked=True)
        except Exception as exc:
            print("⚠️ Остаток заданий не засчитан: %s" % exc)
            return 0
        if added:
            print("ℹ️ Предел реплик: заданий добрано с подсказкой — %d" % added)
        return added


    def _task_from_analysis(self, result):
        """Вариант Б: разбор Аналитика решает, сдано ли задание (§36).

        Второго вызова модели НЕТ: те же поля, что и раньше, плюс
        answer_state. Нужен там, где сравнение текстом бессильно: ученик
        сказал ту же мысль ДРУГИМИ словами («I am going to» вместо «I will»).
        """
        session = self.lesson.current()
        if session is None or not session.is_active or not session.has_tasks:
            return False
        if not result or not result.get("ok"):
            return False
        text = getattr(self, "_last_student_text", "")
        if session.already_credited(text):
            return False          # этот же ответ уже засчитан по тексту (В)
        state = str(result.get("answer_state") or "").strip().lower()
        if session.task_phase == lesson_mod.TASK_FIX:
            if state == lesson_mod.ANSWER_REPEAT_OK:
                return self._credit_task(session, text, marked=False)
            if session.note_task_attempt() >= lesson_mod.MAX_TASK_ATTEMPTS:
                # ученик так и не повторил верно: засчитываем С ПОМЕТКОЙ,
                # иначе урок висел бы вечно (решение ученика 26.10.2026)
                return self._credit_task(session, text, marked=True)
            return False
        # фаза «первый ответ»: либо задание сдано, либо просим повторить
        if state == lesson_mod.ANSWER_CORRECT:
            return self._credit_task(session, text, marked=False)
        errors = result.get("errors") or []
        corrections = [item.get("correct") for item in errors
                       if isinstance(item, dict)]
        if state == lesson_mod.ANSWER_NEEDS_FIX or corrections:
            session.expect_repeat(corrections)
            self._sync_lesson_prompt()   # «ждём верный повтор этой фразы»
            # первую ошибку попыткой НЕ считаем: попытки — это неудачные
            # ПОВТОРЫ (иначе 3 ошибки подряд «съедали» задание сразу)
            return False
        # Ответ НЕ ПО ЗАДАНИЮ (болтовня, «hello», разбор не удался — unclear):
        # попытка всё равно считается. Без этого задание висело до самого
        # предела реплик, и урок закрывался с «Заданий: 2 из 3» (§41).
        if session.note_task_attempt() >= lesson_mod.MAX_TASK_ATTEMPTS:
            return self._credit_task(session, text, marked=True)
        return False

    # ---------- экзамен ----------
    def _sync_exam_asked(self):
        """Сказать модели, какой вопрос экзамена идёт по счёту.

        Без этого она не знает, сколько уже спросила, и закрывает экзамен
        раньше времени (живой прогон 25.10.2026: закрыла на 8-м ответе
        из 10). Считаем по репликам сессии: затравка = вопрос 1.
        """
        try:
            chat = getattr(self, "chat", None)
            if chat is None:
                return              # чат ещё не создан (старт приложения)
            exam = getattr(self, "_exam", None)
            if exam is None:
                chat.set_exam_asked(None)
                return
            session = self.lesson.current()
            replies = int(getattr(session, "replies", 0) or 0)
            asked = min(exam_mod.QUESTIONS, replies + 1)
            chat.set_exam_asked(asked)
        except Exception as exc:
            print("Счёт вопросов экзамена сбился: %s" % exc)

    # ---------- экзамен ----------
    def _exam_session(self):
        """Текущая сессия экзамена (None — занятие не экзамен)."""
        exam = getattr(self, "_exam", None)
        if exam is None:
            return None
        if not self.lesson.is_active and not exam.aborted:
            return None
        return exam

    def _exam_score_answer(self, result=None):
        """Оценить отложенный ответ экзамена (после разбора Аналитика)."""
        exam = self._exam_session()
        if exam is None or not exam.is_active:
            return None
        pending = getattr(self, "_exam_pending", None) or []
        if not pending:
            return None
        text = pending.pop(0)
        # Ошибки знает только Аналитик. Если разбор не удался (дважды — он
        # повторяется в контроллере), ошибки НЕИЗВЕСТНЫ: передаём None, и
        # exam даёт не больше 1 балла. Раньше сбой разбора дарил 2 балла
        # (решение ученика 25.10.2026).
        errors = None
        if result and result.get("ok"):
            errors = len(result.get("errors") or [])
        step = exam.answer(text, errors=errors, used_hint=False)
        try:
            self.lesson_bar.set_progress(exam.progress_text)
        except Exception:
            pass
        return step

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
    def add_message(self, sender, text, picture=None, spans=None):
        """Показать реплику; возвращает метку (для Джейн — можно обновить).

        picture — путь к фото: реплика показывается с картинкой
        (задание «опиши фото», §18).
        spans — [(начало, конец, "err"/"ok")] в тексте реплики (§43).
        """
        # spans — раскраска текста (§43): ошибки красным, исправления зелёным
        mark = self.chat_view.add_message(sender, text, picture=picture,
                                          spans=spans)
        # запоминаем метку последней реплики ПРЕПОДАВАТЕЛЯ: к ней привяжем
        # кнопку «прослушать повторно», когда озвучка закончится. Метку
        # возвращает только преподавательская реплика (для «Вы» — None),
        # поэтому сравнивать имя не нужно: оно теперь настраивается.
        if mark:
            self._jane_mark = mark
        # разбор в словарь-подсказку — в фоне и только в паузе. Реплики
        # УЧЕНИКА тоже: на письме он хочет проверить и свои слова
        # (решение 25.10.2026, было — только преподаватель).
        try:
            self.glossary_controller.request(text)
        except Exception:
            pass
        return mark

    # ---------------- подсказки-переводы по наведению (25.10.2026) -------------
    def _glossary_idle(self):
        """Приложение свободно? Перевод-подсказка ждёт именно такой паузы.

        Приоритет ученика: ответ учителя и озвучка. Пока идёт «Думает…»,
        распознавание или звук — разбор реплики не начинаем.
        """
        if self.busy or self._speech_busy:
            return False
        recording = getattr(self, "recording", None)
        if recording is True:
            return False
        return True

    def _speak_word(self, word, slow):
        """Клик по слову в подсказке: Вербот произносит его по-английски.

        slow=False — обычный темп, slow=True — вдвое медленнее (скорость
        задаёт сама edge-tts, поэтому тон голоса не «плывёт», как при
        замедлении готового mp3). Решение ученика 25.10.2026.
        """
        word = str(word or "").strip()
        if not word:
            return
        self._say(word, rate=tts.WORD_SLOW_RATE if slow else None)

    def _hover_translation(self, text, position):
        """Курсор над словом в реплике преподавателя: (en, ru) или None.

        Модель НЕ вызывается — только словарь в памяти, ответ мгновенный.
        """
        try:
            return self.glossary.lookup(text, position)
        except Exception:
            return None
    def _show_greeting(self):
        """Показать приветствие и запомнить его метку.

        Метка нужна, чтобы после теста уровня ЗАМЕНИТЬ строку «уровень пока не
        определён» прямо в этом сообщении, а не дописывать вторую реплику.
        """
        self._greeting_mark = self.add_message(self.teacher_name, self._greeting())
        return self._greeting_mark

    def _update_greeting_level(self):
        """Обновить строку уровня в приветствии. True — если получилось."""
        mark = getattr(self, "_greeting_mark", None)
        if not mark:
            return False
        try:
            return bool(self.chat_view.update_message(mark, self._greeting()))
        except Exception as exc:
            print("⚠️ Строка уровня в приветствии не обновилась: %s" % exc)
            return False

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
    # Подсказка перевода (RU → EN)
    # -----------------------------------------------------
    def _wants_translation(self, text):
        """Нужна ли подсказка: есть русские буквы и перевод включён."""
        if not getattr(config, "TRANSLATE_ENABLED", True):
            return False
        return translate.has_cyrillic(text)

    def _show_translation_hint(self, text):
        """Перевести слово/фразу в фоне и показать подсказку."""
        self.hint_bar.show_status("💡 Перевожу…")
        threading.Thread(target=self._translate_worker, args=(text,),
                         daemon=True).start()

    def _translate_worker(self, text):
        """Фон: перевод коротким вызовом модели (~0.3 с).

        Одно слово → до трёх значений с примерами; фраза → одна строка.
        """
        single = translate.is_single_word(text)
        try:
            if single:
                ok, result = self.translator.translate_word(text)
            else:
                ok, result = self.translator.translate(text)
        except Exception as exc:
            print("⚠️ Перевод не удался: %s" % exc)
            ok, result = False, ["перевод недоступен"] if single else "перевод недоступен"
        self._dispatch(lambda: self._apply_translation(text, ok, result, single))

    def _apply_translation(self, source, ok, result, single=False):
        """Главный поток: показать перевод или понятную ошибку."""
        if not ok:
            reason = result[0] if isinstance(result, list) and result else result
            self.hint_bar.show_status(
                "💡 Не удалось перевести: %s. Попробуй иначе." % reason)
            return
        if single:
            self.hint_bar.show_meanings(result, source)
        else:
            self.hint_bar.show_translation(result, source)
        # ОДИНОЧНОЕ слово копится в словарь повторения САМО, без кнопок.
        # Заодно запоминаем карточку: её пример станет эталоном произношения,
        # значит при вердикте GOOD «+1» получит именно она.
        self._pron_card = self._remember_vocabulary(source, result) if single else None
        self._remember_pron_reference(result, single)
        self._character_state("thinking")

    def _hint_insert(self, english):
        """Кнопка ↺: вставить перевод в поле ввода В МЕСТО КУРСОРА.

        Ничего не отправляем: ученик может дописать фразу, поправить её
        или сказать вслух. Набранный текст сохраняется.
        """
        return self.input_bar.insert_at_cursor(english)

    def _hint_listen(self, english):
        """Нажатие на слово/пример в подсказке: озвучить ровно этот текст."""
        self._say(english)

    # -----------------------------------------------------
    # Словарь для повторения (см. vocabulary.py)
    # -----------------------------------------------------
    def _remember_vocabulary(self, source, meanings):
        """Запомнить значения переведённого слова → (слово, значение) первой карточки.

        Копится САМО, без кнопок «сохранить»: ученик перевёл слово — оно уже
        в словаре. Дубликаты не появляются, выученное слово не сбрасывается
        (это делает vocabulary.add_meanings).

        Возвращает пару (русское слово, английское значение) ПЕРВОЙ карточки:
        её пример становится эталоном произношения, поэтому при вердикте GOOD
        «+1» должен достаться именно ей.
        """
        if not getattr(config, "VOCAB_ENABLED", True):
            return None
        try:
            parsed = vocabulary.parse_meanings(meanings)
            if not parsed:
                return None
            # «привет.» и «привет» — одно слово: точку/запятую снимаем,
            # иначе в словаре заводились две карточки на одно слово
            word = translate.normalize_word(source) or str(source or "").strip()
            added = profile_store.add_vocabulary(
                word, meanings, (self.current_user or {}).get("id"))
            if added:
                print("📚 В словарь: «%s» (+%d карточ.)" % (word, len(added)))
            return (word, parsed[0]["en"])
        except Exception as exc:
            print("⚠️ Слово не записано в словарь: %s" % exc)
            return None

    def _vocabulary_success(self):
        """Вердикт GOOD: +1 к уровню карточки, чей пример был эталоном."""
        key = getattr(self, "_pron_card", None)
        if not key or not getattr(config, "VOCAB_ENABLED", True):
            return
        word, en = key
        try:
            card = profile_store.update_vocabulary_card(
                word, en, True, (self.current_user or {}).get("id"))
        except Exception as exc:
            print("⚠️ Успех слова не записан: %s" % exc)
            return
        if card:
            print("📚 «%s» → уровень %s" % (en, card.get("level")))

    # -----------------------------------------------------
    # Окно «Повторение» (этап B): открывает сама Джейн
    # -----------------------------------------------------
    def maybe_review_vocabulary(self):
        """Открыть окно повторения, если сегодня ещё не было и есть слова.

        Порядок при запуске: профиль → модель → тест уровня → повторение.
        Окно НЕ открываем: без микрофона, во время урока, поверх теста,
        второй раз за день и когда повторять нечего.
        """
        if not getattr(config, "VOCAB_ENABLED", True):
            return
        if not getattr(config, "VOCAB_REVIEW_ON_START", True):
            return
        if not self.profile_ready:
            return
        if self.lesson.is_active:
            return                      # идёт урок — повторение перенесём
        if self.vocab_panel is not None:
            return
        user_id = (self.current_user or {}).get("id")
        try:
            if vocabulary.session_today(profile_store.vocab_last_session(user_id)):
                return                  # сегодня уже повторяли — не чаще раза в день
            cards = profile_store.vocabulary_cards(user_id)
        except Exception as exc:
            print("⚠️ Слова для повторения не прочитаны: %s" % exc)
            return
        due = vocabulary.due_cards(cards)
        if not due:
            return                      # повторять нечего — и строки в чат нет
        ready, _message = self._microphone_ready()
        if not ready:
            if self.stt_state == "loading":
                self._vocab_wanted = True    # начнём, когда Whisper будет готов
            return
        self._vocab_wanted = False
        self.add_message(self.teacher_name,
                         "📚 Давай повторим %s." % ru_text.words(len(due)))
        self._open_vocab_panel()

    def review_vocabulary(self):
        """«📚 Повторить слова» в окне блока: повторение по требованию.

        Отличие от автозапуска (maybe_review_vocabulary): НЕ смотрим «сегодня
        уже повторяли» и «есть ли слова на сегодня» — окно открывается всегда,
        чтобы его можно было проверить в любой момент. Если повторять нечего,
        окно само это скажет. Автозапуск урока после такого захода НЕ взводим:
        ученик пришёл с карты, а не поздоровался в чате.
        """
        if not getattr(config, "VOCAB_ENABLED", True):
            self.add_message(self.teacher_name, "📚 Повторение слов выключено в настройках.")
            return None
        if not self.profile_ready:
            self.add_message(self.teacher_name, SETUP_HINT)
            return None
        if self.vocab_panel is not None:
            return self.vocab_panel        # окно уже открыто — второе не нужно
        if self.lesson.is_active:
            self.add_message(self.teacher_name, "⚠️ Сначала заверши урок — повторение открою после.")
            return None
        return self._open_vocab_panel(allow_empty=True)

    def _open_vocab_panel(self, allow_empty=False):
        """Показать окно повторения (модальное, поверх главного окна).

        allow_empty — открыть окно даже без слов (кнопка с карты): тогда оно
        покажет «повторять нечего» и объяснит почему.
        """
        try:
            self.vocab.start()
        except Exception as exc:
            print("⚠️ Заход повторения не собрался: %s" % exc)
            return None
        if not self.vocab.is_active and not allow_empty:
            return None
        empty_text = "" if self.vocab.is_active else self._vocab_empty_note()
        try:
            self.vocab_panel = VocabPanel(
                self.window, self.palette, self.vocab,
                on_record_start=self._vocab_record_start,
                on_record_stop=self._vocab_record_stop,
                on_say=self._say,
                on_finish=self._vocab_finished,
                empty_text=empty_text)
        except Exception as exc:
            print("⚠️ Окно повторения не открылось: %s" % exc)
            self.vocab_panel = None
            return None
        # Пока окно открыто, ученик говорит ТОЛЬКО по-английски: жёсткий язык
        # спасает короткие слова, где автоопределение ошибается (27.10.2026).
        try:
            self.stt.set_language("en")
        except Exception:
            pass
        return self.vocab_panel

    @staticmethod
    def _vocab_empty_note():
        """Объяснение для окна «повторять нечего» — простыми словами."""
        try:
            cards = profile_store.vocabulary_cards()
        except Exception:
            cards = []
        if not cards:
            return ("В словаре пока пусто. Переведи слово в чате — "
                    "оно само сюда попадёт.")
        try:
            due = vocabulary.due_cards(cards)
        except Exception:
            due = []
        if not due:
            return ("Сегодня повторять нечего: все слова ждут своего дня "
                    "(лестница 1 → 3 → 7 → 21 день).")
        return ""

    def _vocab_record_start(self):
        """«Запись» в окне повторения: тот же push-to-talk, что и в чате."""
        self._start_recording()

    def _vocab_record_stop(self):
        self._stop_recording()

    def _vocab_finished(self, summary):
        """Окно повторения закрылось: обновить «Профиль» и забыть окно."""
        self.vocab_panel = None
        # В обычном чате язык снова определяем сами (русское слово в поле
        # должно уходить в перевод, а не в английскую сверку).
        try:
            self.stt.set_language(None)
        except Exception:
            pass
        print("📚 Повторение закончено: %s" % (summary or {}))
        self._refresh_side_views()
        if self._arm_after_vocab:
            # заход был частью запуска (после теста уровня) — теперь урок
            self._arm_after_vocab = False
            self._arm_auto_lesson()

    # -----------------------------------------------------
    # Автозапуск урока: Джейн сама ведёт занятие (этап B+)
    # -----------------------------------------------------
    def _review_then_arm(self):
        """Повторение слов → взвод автозапуска урока (порядок §14.5).

        Порядок запуска: профиль → модель → тест уровня → повторение слов →
        урок. Повторение всегда идёт раньше: слова ученик вспоминает на
        разогреве, а не посреди занятия.
        """
        try:
            self.maybe_review_vocabulary()
        except Exception as exc:
            print("⚠️ Повторение не открылось: %s" % exc)
        finally:
            self._after_vocab_review()

    def _after_vocab_review(self):
        """Повторение закончилось (или не понадобилось) → взводим урок."""
        if self.vocab_panel is not None:
            # окно открыто: взведём урок, когда его закроют (_vocab_finished)
            self._arm_after_vocab = True
            return
        self._arm_auto_lesson()

    def _arm_auto_lesson(self):
        """Взвести автозапуск: урок начнётся с ПЕРВОЙ реплики ученика.

        Так Джейн ведёт занятие сама (решение §14.5): не спрашиваем «Начнём
        урок 1.2? Да / Позже», а просто начинаем следующий урок по карте.
        Условия: профиль полон, модель готова, урок не идёт, окно повторения
        закрыто, есть непройденный урок. Одна попытка за запуск.
        """
        if not getattr(config, "LESSON_AUTO_START", True):
            return False
        if self._auto_lesson_used or self._auto_lesson_armed:
            return False
        if not self.profile_ready or self.lesson.is_active:
            return False
        if self.vocab_panel is not None:
            return False            # сначала повторение слов, потом урок
        if not self.server_ready:
            return False            # модель грузится — взведём, когда будет готова
        try:
            lesson_id = self.progress_map.next_lesson(self._active_profile())
        except Exception as exc:
            print("⚠️ Следующий урок не определён: %s" % exc)
            return False
        if not lesson_id:
            self._auto_lesson_used = True          # начинать нечего
            self.add_message(self.teacher_name, ALL_LESSONS_NOTE)
            return False
        if self._test_tail_flag():
            # 🧪 ТЕСТ: не ждём реплику ученика — сразу начинаем урок
            # (он тут же встанет на последний шаг, см. _jump_to_lesson_tail)
            self._auto_lesson_used = True
            self._auto_lesson_armed = False
            test_id = self._test_lesson_id() or lesson_id
            print("🧪 ТЕСТ: начинаю урок %s сразу (без реплики ученика)" % test_id)
            self.start_lesson(test_id, auto=True)
            return True
        self._auto_lesson_armed = True
        print("🎓 Автозапуск урока взведён: следующий — %s" % lesson_id)
        return True

    def _maybe_start_auto_lesson(self, text, sender="Вы"):
        """Первая реплика ученика → сразу начинаем следующий урок по карте.

        Возвращает True, если урок начат (или причина уже сказана): тогда
        реплику дальше не обрабатываем — она уходит в затравку урока, а не в
        обычный диалог. False — всё как раньше (свободное общение).
        """
        if not self._auto_lesson_armed:
            return False
        self._auto_lesson_armed = False
        self._auto_lesson_used = True
        if self.lesson.is_active or not self.profile_ready:
            return False
        try:
            lesson_id = self.progress_map.next_lesson(self._active_profile())
        except Exception as exc:
            print("⚠️ Автозапуск: урок не определён (%s)" % exc)
            return False
        if not lesson_id:
            return False
        # реплика ученика видна в чате, а дальше Джейн начинает урок
        self.add_message(sender, text)
        print("🎓 Автозапуск: начинаю урок %s" % lesson_id)
        self.start_lesson(lesson_id, student_text=text, auto=True)
        return True

    # -----------------------------------------------------
    # Сверка произношения (см. pronunciation.py)
    # -----------------------------------------------------
    def _remember_pron_reference(self, result, single=False):
        """Запомнить английскую подсказку как эталон для сверки произношения.

        Дальше ученик должен произнести эту фразу в микрофон — тогда программа
        скажет, похоже ли получилось. Работает без модели и без сети.
        """
        if not getattr(config, "PRON_CHECK_ENABLED", True):
            return
        try:
            import pronunciation
            english = result[0] if isinstance(result, list) and result else result
            ref = pronunciation.reference_from_hint(english, single=bool(single))
        except Exception as exc:
            print("⚠️ Эталон произношения не сохранён: %s" % exc)
            return
        self._pron_ref = ref or ""
        self._pron_at = time.monotonic() if self._pron_ref else 0.0

    def _pron_forget(self):
        """Подсказку закрыли — забываем эталон (дальше идёт обычный диалог)."""
        self._pron_ref = ""
        self._pron_at = 0.0
        self._pron_card = None

    def _pronunciation_report(self, text):
        """Сверить услышанное с подсказкой, если она ещё «в силе»."""
        if not getattr(config, "PRON_CHECK_ENABLED", True) or not self._pron_ref:
            return None
        try:
            memory = float(getattr(config, "PRON_MEMORY_SECONDS", 150.0) or 0)
        except (TypeError, ValueError):
            memory = 150.0
        if memory > 0 and (time.monotonic() - self._pron_at) > memory:
            self._pron_forget()               # подсказка устарела
            return None
        try:
            import pronunciation
            return pronunciation.compare(self._pron_ref, text)
        except Exception as exc:
            print("⚠️ Сверка произношения не удалась: %s" % exc)
            return None

    def _show_pronunciation(self, text):
        """Показать вердикт сверки. True — реплику в диалог НЕ отправляем.

        «Похоже» — показываем и продолжаем обычный разговор с Джейн (она
        похвалит и поведёт урок дальше). «Почти»/«Попробуй ещё» — ученик
        остаётся на этой фразе: 🔊 послушать, как надо, и повторить.
        """
        report = self._pronunciation_report(text)
        if report is None or not report.show:
            return False
        if report.verdict == "good":
            self._vocabulary_success()      # +1 к уровню слова (до _pron_forget!)
            self._note_hint()               # подсказка + произнёс вслух = в счёт
            self._pron_forget()
            self.hint_bar.show_note("✅ Похоже! «%s»" % report.reference,
                                    report.reference)
            self._character_state("happy")
            return False
        self.hint_bar.show_note(
            str(report.message) + "\n   нажми на фразу, чтобы послушать, и повтори",
            report.reference)
        self._character_state("thinking")
        return True

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
        """Начать «игру лицом» по тексту ответа: настроение по предложениям.

        Ставит лицо для ПЕРВОГО куска; дальше эмоции меняет колбэк из
        tts.py ровно в момент начала звука каждого следующего куска.
        """
        try:
            import mood as mood_mod
            plan = mood_mod.plan_reply(response)
        except Exception as exc:
            print("⚠️ Настроение не разобрано: %s" % exc)
            plan = None
        self._mood_plan = plan
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

    def _mood_speech(self):
        """Параметры speak() для точной синхронизации лица с озвучкой.

        Отдаём озвучке готовые ЧАСТИ реплики: tts сам скажет, когда начинается
        звук каждой (колбэк _on_mood_part). Раньше момент смены эмоции считался
        «символы ÷ скорость речи» и опаздывал до 1-2 секунд.
        """
        plan = self._mood_plan
        if plan is None or not plan.segments:
            return {}
        return {"parts": [seg.text for seg in plan.segments],
                "on_part": self._on_mood_part}

    def _on_mood_part(self, index):
        """Поток озвучки: началась очередная часть реплики → сменить лицо."""
        try:
            self._dispatch(lambda i=index: self._apply_mood_part(i))
        except Exception as exc:
            print("⚠️ Настроение: часть не передана в окно (%s)" % exc)

    def _apply_mood_part(self, index):
        """Главный поток: поставить лицо по куску плана настроения."""
        plan = self._mood_plan
        if plan is None or not plan.segments:
            return
        if index < 0 or index >= len(plan.segments):
            return
        self._character_state(self._mood_state(plan, index))

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
    # Состояния БЕЗ речи (happy / smile / idle …) держат рот ЗАСТЫВШИМ
    # (StateConfig.static_mouth или talk=False). Если озвучка идёт в таком
    # состоянии, ученик СЛЫШИТ речь, а рот стоит — живой баг 26.10.2026:
    # похвала и задание к фото читались «без рта» (лицо было happy, §37/§40).
    _TALKING_FACE = {"happy": "speak_happy", "smile": "speak_happy",
                     "scorn": "speak_happy", "sad": "speak_sad",
                     "angry": "speak_sad", "surprised": "speak_surprised",
                     "thinking": "speak_thinking", "listening": "speaking",
                     "idle": "speaking", "story_end": "speaking"}
    _SPEAKING_STATES = ("speaking", "speak_happy", "speak_sad",
                        "speak_surprised", "speak_thinking", "speak_story")

    def _keep_mouth_moving(self, char):
        """Пока идёт озвучка, лицо обязано быть «говорящим» (§41).

        Иначе рот замирает: у happy/smile/idle static_mouth или talk=False.
        """
        state = getattr(char, "state", None)
        if getattr(self, "_speech_busy", False):
            if state in self._SPEAKING_STATES:
                return
            target = self._TALKING_FACE.get(state)
            if target and self._character_state(target):
                self._face_auto = target
        else:
            # маска, которую мы сами поставили ради речи, — вернуть покой
            auto = getattr(self, "_face_auto", None)
            self._face_auto = None
            if auto and auto == state:
                self._character_state("idle")


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
            self._keep_mouth_moving(getattr(self, "character", None))
            char = getattr(self, "character", None)
            if char is not None and getattr(char, "available", False):
                # не дёргаем лицо, если уровень почти не изменился
                if abs(level - self._last_char_level) > 1.5 or speaker != self._last_char_speaker:
                    self._last_char_level = level
                    self._last_char_speaker = speaker
                    char.set_level(level, speaking=(speaker == "jane" and level > 2.0))
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
        # Ответ пришёл — отложенный итог урока больше не «ждёт модель»
        # (покажем его, когда речь доиграет: см. _finish_speech).
        self._reply_in_flight = False
        session = self.lesson.current()
        # ЭКЗАМЕН закрываем в _on_analysis: там уже посчитан балл последнего
        # ответа (разбор Аналитика приходит после ответа преподавателя).
        exam = self._exam_session()
        if (session is not None and session.is_active and session.should_finish
                and exam is None):
            # §32: итог НЕ встаёт перед озвучкой этого ответа. Поднимаем флаг
            # «ответ ещё звучит» — покажет итог _finish_speech.
            self._reply_in_flight = True
            self._credit_rest_tasks(session)
            # credit_rest мог сам закрыть сессию (задания кончились) —
            # тогда finish() промолчал бы и итог НЕ показался бы
            if session.is_active:
                self.lesson.finish()
            else:
                self.lesson.credit_finished()

        # «актёрская игра»: настроение её собственного текста
        self._start_mood_play(response)
        # «конец рассказа» — ТОЛЬКО в контексте рассказа (не любой длинный ответ)
        is_story = bool(self._story_context
                        and self._mood_plan is not None
                        and self._mood_plan.story)
        mark = self._jane_mark
        def _after_speech(m=mark, story=is_story):
            # «доиграла»: для рассказа — закрыть глаза на 3 с (конец истории)
            self._dispatch(lambda: self._finish_speech(m, story))

        self._say(response, on_done=_after_speech, **self._mood_speech())
        self.visualizer.reset()

    def _finish_speech(self, mark, story):
        """Речь Джейн закончилась: кнопка повтора и «конец рассказа»."""
        # Последняя реплика урока досказана — теперь можно показать итог
        # и задание с фото (живой баг 25.10.2026: они влезали раньше).
        self._run_deferred_finish()
        if mark:
            try:
                self.chat_view.enable_replay(mark)
            except Exception:
                pass
        if not story:
            # обычный ответ досказан: возвращаем спокойное лицо, иначе
            # робот остаётся с радостным выражением до следующего события
            plan = self._mood_plan
            if plan is not None and any(s.mood != "neutral" for s in plan.segments):
                self._mood_plan = None
                self._character_state("idle")
            return
        # досказала историю — закрывает глаза на пару секунд (STORY_END).
        # Защита от повтора: колбэк окончания речи может прийти дважды
        # (например, при повторном прослушивании) — иначе 3 секунды
        # запускались бы заново.
        now = time.monotonic()
        char = getattr(self, "character", None)
        if char is not None and getattr(char, "state", None) == "story_end":
            return
        if now - self._story_end_at < 6.0:
            return
        self._story_end_at = now
        self._mood_plan = None              # план больше не нужен
        self._character_state("story_end")

    def _replay_reply(self, text):
        """Кнопка «прослушать повторно»: озвучить ту же реплику заново.

        План настроения строим заново — повтор звучит с той же «игрой лицом».
        """
        self._start_mood_play(text)
        self._say(text, **self._mood_speech())

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
        # ошибки копятся для ИТОГА занятия (по ходу ученику не показываем)
        if result and result.get("ok"):
            errors = result.get("errors") or []
            if errors:
                self._note_mistakes(len(errors))
        # §36: разбор решает, сдано ли ТЕКУЩЕЕ задание урока (вариант Б)
        self._task_from_analysis(result)
        # ЭКЗАМЕН: разбор пришёл — теперь можно поставить балл за ответ
        step = self._exam_score_answer(result)
        if step is not None and step.get("finished"):
            self._finish_exam()          # 10-й ответ: итог и запись в профиль

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


    def _say(self, text, on_done=None, parts=None, on_part=None, rate=None):
        """Озвучка в фоне — окно ждать не должно.

        on_done вызывается (тоже в фоне) сразу после того, как звук доиграл;
        UI-обновления внутри него обязаны уйти через dispatch в главный поток.

        parts / on_part — части реплики и колбэк «началась часть № N»: по нему
        лицо робота меняет эмоцию ровно вместе со звуком (см. _mood_speech).

        rate — НЕОБЯЗАТЕЛЬНО: скорость на эту реплику ("-50%" — вдвое
        медленнее). Нужно для медленного повтора слова по клику.
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
            self._speech_busy = True
            try:
                ok = tts.speak(text, name=name, name_latin=name_latin,
                               parts=parts, on_part=on_part, rate=rate)
                if ok is False:
                    # Джейн не смогла озвучить (например, edge-tts ответил 403)
                    self._dispatch(self._notify_no_voice)
                else:
                    self._dispatch(self._clear_no_voice)
            finally:
                self._speech_busy = False
                if on_done:
                    try:
                        on_done()
                    except Exception:
                        pass

        # Флаг ставим ДО запуска потока: иначе гонка — следующий _say успеет
        # включиться раньше и оборвёт эту реплику (tts.speak глушит старое).
        self._speech_busy = True
        threading.Thread(target=_worker, daemon=True).start()

    # Примечание: _say объявлен выше (в блоке обратной связи), здесь пусто.

    def _on_recording_changed(self, recording):
        # запись идёт из окна повторения — подсветить кнопку и там
        panel = self.vocab_panel
        if panel is not None:
            try:
                panel.set_recording(recording)
            except Exception:
                pass
        self.control_bar.set_recording(recording)
        # слушает ученика: улыбка, кивки, моргание
        self._character_state("listening" if recording else "idle")

    def _on_recognized(self, text, lang):
        self.current_lang = lang
        self.chat.set_language(lang)
        # открыто окно повторения — сказанное идёт В НЕГО, а не в чат
        panel = self.vocab_panel
        if panel is not None and panel.is_open:
            panel.accept_text(text)
            return
        # первая реплика голосом тоже запускает урок (до проверки языка)
        if self._maybe_start_auto_lesson(text, "Вы (голос)"):
            return
        # сказал по-русски — тоже показываем подсказку, а не пишем в чат
        if self._wants_translation(text):
            self._show_translation_hint(text)
            return
        # сверка произношения: ученик произносит фразу из подсказки
        if self._show_pronunciation(text):
            return
        self.add_message("Вы (голос)", text)
        self._handle_text(text)

    def _on_server_state(self, state, message):
        self.server_state = state
        self.server_ready = (state == "ready")
        self._refresh_status()
        self._refresh_input_state()
        if self.server_ready and not (self._auto_lesson_armed
                                       or self._auto_lesson_used):
            # модель готова — урок можно начинать (если ещё не взведён)
            self.window.after(300, lambda: self._arm_auto_lesson())
        return state

    def _stt_hotwords(self):
        """Слова-подсказки для Whisper: имя ученика и слово из карточки.

        Имена — главная «жертва» распознавания («Дамиль» легко услышать как
        что-то другое). В окне повторения добавляем ЦЕЛЕВОЕ слово и пример:
        Whisper режет составные слова («flatbread» слышит как «flat bread»),
        а с подсказкой он знает, какое слово ждут (замер и жалоба 27.10.2026).
        Возвращаем строку через запятую; вызывается из фонового потока
        распознавания, поэтому только ЧИТАЕМ данные.
        """
        u = self.current_user or {}
        parts = [u.get("name"), u.get("name_latin")]
        card = self._vocab_stt_card()
        if card:
            parts.append(card.get("en"))
            parts.append(card.get("example"))
        return ", ".join(p for p in parts if p)

    def _vocab_stt_card(self):
        """Карточка, которая сейчас на экране повторения (или None)."""
        panel = self.vocab_panel
        if panel is None:
            return None
        try:
            return self.vocab.current()
        except Exception:
            return None

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
        # повторение слов ждало микрофон — теперь можно открыть окно
        if self.stt_ready and self._vocab_wanted:
            self._vocab_wanted = False
            self.window.after(200, self._review_then_arm)

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
        # Урок «только голосом»: английское сообщение в чат НЕ отправляется,
        # но РУССКОЕ слово перевести можно — в этом и смысл подсказки: ученик
        # увидит английский вариант и произнесёт его вслух (решение 23.10.2026).
        # Решаем ДО автозапуска урока: в занятии он всё равно не нужен, а
        # русское слово не должно приниматься за первую реплику.
        if self.input_bar.is_locked:
            ctrl = getattr(self, "lesson", None)
            session = ctrl.current() if ctrl is not None else None
            # На ЭКЗАМЕНЕ словаря нет: русское слово тоже не переводим.
            dict_ok = session is None or session.allows_dictionary()
            if dict_ok and self._wants_translation(text):
                self.input_bar.clear_text()
                self._show_translation_hint(text)
            elif dict_ok:
                self.add_message(self.teacher_name, LOCKED_TEXT_NOTE)
            else:
                self.add_message(self.teacher_name, EXAM_NO_HINT_NOTE)
            return
        self.input_bar.clear_text()
        # Первая реплика запускает урок (ДО переводчика: русское «привет»
        # тоже должно начинать занятие — см. грабли №28)
        if self._maybe_start_auto_lesson(text, "Вы"):
            return
        # Русская фраза НЕ пишется в чат: она уходит в подсказку перевода
        # (решение ученика — переписать, произнести или отправить как есть).
        if self._wants_translation(text):
            self._show_translation_hint(text)
            return
        self.add_message("Вы", text)
        self._handle_text(text)

    def _handle_text(self, text, skip_translate=False):
        """Ввод пользователя — текстом или голосом (разницы нет).

        Сначала проверяем команду смены режима («урок», «перерыв»…):
        её выполняем локально, к модели не ходим и сервер не требуем.
        """
        # пока профиль не заполнен — общение невозможно (гейт)
        if not self.profile_ready:
            self.add_message(self.teacher_name, SETUP_HINT)
            return
        # пользователь что-то делает — гасим текущую речь Джейн
        tts.stop()

        # Голосовых команд режима («урок», «перерыв», «друг») здесь больше нет:
        # это рудимент консольной версии. В окне режим ставят сами — урок
        # включает его в _begin_lesson, а вручную переключают в «Настройках».
        # Заодно русская фраза больше не перехватывается: слово «друг»
        # спокойно переводится в подсказке, как и любое другое.

        # Задание с картинкой: пока порог букв не набран, реплика в модель
        # не уходит — преподаватель отвечает сам (порог ЖЁСТКИЙ).
        if self._picture is not None and not skip_translate:
            if self._picture_reply(text):
                return

        if _asks_for_story(text):
            self._story_context = True      # ученик просит историю/сказку
        if self.server_ready:
            self._send_to_teacher(text)
            return
        # сервер молчит: сначала «ожидание», и только если долго — «не отвечает»
        self._run_when_server_ready(lambda: self._send_to_teacher(text))

    def _send_to_teacher(self, text):
        """Отправить реплику учителю (в занятии — учесть её в счёте)."""
        # Порядок важен: считаем реплику ДО отправки (на экзамене текст нужен
        # для балла), но помечаем, что ответ учителя ещё в пути — иначе итог
        # урока встанет раньше ответа (живой баг 25.10.2026).
        self._reply_in_flight = True
        self._last_student_text = text       # за какую реплику придёт разбор
        self._register_lesson_reply(text)    # на экзамене текст нужен для балла
        # Реплика, которая закрывает урок: спрашивать больше НЕЛЬЗЯ — иначе
        # бот задаёт новый вопрос и тут же уходит в итог с фото (баг 26.10.2026).
        self._mark_lesson_closing()
        # §36 (вариант В): ученик повторил исправление — задание сдано ДО
        # ответа учителя, поэтому он сразу даёт следующее в той же реплике.
        self._credit_task_by_text(text)
        self.chat.send(text)

    def _run_deferred_finish(self):
        """Показать отложенный итог урока (ответ учителя уже прозвучал).

        Вызывается из _finish_speech (речь доиграла) и как страховка — по
        таймеру из _on_lesson_finished (модель могла не ответить вовсе).
        """
        session = getattr(self, "_deferred_finish", None)
        if session is None:
            return
        # Страховочный таймер мог сработать РАНЬШЕ, чем доиграла реплика
        # (до первого звука бывает 10 с, плюс сам ответ). Пока Вербот
        # говорит, итог не показываем — иначе похвала глушит речь на
        # полуслове (tts.speak сначала делает tts.stop), а фото выгружается
        # посреди ответа. Живой баг 26.10.2026.
        if getattr(self, "_speech_busy", False) and self._speech_wait_left() > 0:
            try:
                self.window.after(200, self._run_deferred_finish)
                return
            except Exception:
                pass            # окна нет (проверки) — показываем как раньше
        self._deferred_finish = None
        self._deferred_deadline = None
        self._reply_in_flight = False        # защита от второго откладывания
        self._on_lesson_finished(session)

    def _say_after_current(self, text, mark=None):
        """Озвучить, когда ТЕКУЩАЯ речь доиграет.

        tts.speak() в начале глушит предыдущую реплику (tts.stop()), поэтому
        просьба про фото, сказанная сразу после похвалы, обрывала её на
        полуслове — «Вербот запнулся» (баг 25.10.2026).
        """
        def _done():
            # значок 🔊 у реплики — как у обычного ответа Вербот (§43)
            if mark:
                self._dispatch(lambda: self.chat_view.enable_replay(mark))

        def _say_now():
            self._say(text, on_done=_done if mark else None)

        def _check(left):
            # _speech_busy снимается по окончании звука; ждём не дольше 30 с
            # (зависшая озвучка не должна съесть просьбу совсем).
            if not getattr(self, "_speech_busy", False) or left <= 0:
                _say_now()
                return
            try:
                self.window.after(150, lambda: _check(left - 1))
            except Exception:
                _say_now()          # окна нет (проверки) — говорим сразу

        _check(200)

    def _speech_wait_left(self):
        """Сколько ещё можно ждать конца озвучки (страховка от зависания)."""
        if getattr(self, "_deferred_deadline", None) is None:
            margin = getattr(config, "LESSON_SPEECH_WAIT_MS", 90000) / 1000.0
            self._deferred_deadline = time.monotonic() + margin
        return self._deferred_deadline - time.monotonic()

    def _wait_for_speech(self, action, step_ms=200):
        """Выполнить действие, когда озвучка ДОИГРАЕТ (не обрывая реплику).

        tts.speak() в начале глушит предыдущую речь, поэтому итог урока,
        похвала и задание с фото не должны запускаться, пока Вербот говорит
        (живой баг 26.10.2026: реплика оборвалась, а задание с фото уже
        выгрузилось). Страховка: ждём не дольше LESSON_SPEECH_WAIT_MS.
        """
        deadline = time.monotonic() + getattr(
            config, "LESSON_SPEECH_WAIT_MS", 90000) / 1000.0

        def _fire():
            try:
                action()
            except Exception as exc:
                print("⚠️ Действие после речи не выполнилось: %s" % exc)

        def _tick():
            if (not getattr(self, "_speech_busy", False)
                    or time.monotonic() >= deadline):
                _fire()
                return
            try:
                self.window.after(step_ms, _tick)
            except Exception:
                _fire()          # окна нет (проверки) — не ждём

        _tick()

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
            self.add_message(self.teacher_name, NOT_READY_OFFLINE)
            self._set_status("● Сервер не отвечает", "err")
            if task.get("on_timeout") is not None:
                self._safe_call(task["on_timeout"])
            return
        if status == ServerWaiter.ANNOUNCE:
            self._set_status("● Ожидаю сервер…", "warn")
            self.add_message(self.teacher_name, "⏳ Ожидаю LLM-сервер…")
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
        self.hint_bar.clear()
        self.input_bar.set_locked(False)
        self.control_bar.set_record_enabled(True)
        self._picture = None            # задание с картинкой сброшено
        try:
            self.input_bar.clear_counter()
        except Exception:
            pass
        # Раньше «Очистить» оставлял пустое окно. Возвращаем приветствие —
        # в нём актуальный уровень, и метка снова известна.
        self._show_greeting()

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

        new_voice = self.right_panel.get_voice()
        if new_voice and new_voice != tts.VOICE_EN:
            self._apply_voice(new_voice)

        self.close_panel()

    def _apply_voice(self, voice_id):
        """Смена английского голоса: сразу, без перезапуска сервера.

        Меняется только английская речь — русские куски по-прежнему читает
        Светлана. Сразу проговариваем короткий образец, чтобы ученик услышал
        новый голос (и «h» в «Hi») не дожидаясь реплики учителя.
        """
        voice_id = tts.set_voice(voice_id)
        settings_store.set_voice_en(voice_id)
        label = next((lb for vid, lb in tts.voices() if vid == voice_id), voice_id)
        self.add_message(self.teacher_name, "🎧 Голос: %s." % label)
        threading.Thread(target=tts.speak, args=("Hi! How are you today?",),
                         daemon=True).start()

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
        self.add_message(self.teacher_name, "🔄 Перезапускаю модель: %s. Это займёт до минуты." % label)
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
            self.add_message(self.teacher_name, "✅ Модель загружена.")
        else:
            self.add_message(self.teacher_name, "⚠️ Модель не загрузилась. "
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
        self.add_message(self.teacher_name, f"⚙️ Режим изменён на {commands.MODE_LABELS.get(mode, mode)}")

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
        self.hint_bar.apply_theme(p)
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
        for stopper in (self.monitor.stop, self.dispatcher.stop,
                        self.glossary_controller.stop):
            try:
                stopper()
            except Exception:
                pass
        if self.recorder.is_recording:
            self.recorder.stop()
        if self.character is not None:
            self.character.stop_idle()
        try:
            ui_fonts.release_all()          # отпускаем шрифты, взятые у GDI
        except Exception:
            pass
        self.window.destroy()
