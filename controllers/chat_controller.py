# -*- coding: utf-8 -*-
# =========================================================
# CHAT_CONTROLLER.PY — оркестрация диалога с Джейн
# =========================================================
# Что переехало сюда из gui.py:
#   ask_jane, _process_input, _get_response, _display_response,
#   сборка промпта, чистка тегов, история диалога, запись в профиль.
#
# Вариант B: контроллер знает user_id активного ученика и все обращения
# к прогрессу (load / record_from_dialogue) делает С ЯВНЫМ user_id.
# Так прогресс каждого ученика лежит в своём файле, а контроллер не
# зависит от «глобального» активного пользователя.
#
# GUI теперь знает только это:
#   chat.set_user(user_id)
#   chat.send("текст")  →  колбэки on_message / on_status / on_busy / on_response
#
# Все колбэки вызываются в ГЛАВНОМ потоке (dispatch = window.after),
# потому что Tk не потокобезопасен.
# =========================================================

import logging
import threading
from datetime import datetime

import config
import llm_client
import profile_store
import exam as exam_mod
import prompt_builder
import vocabulary
import rag
import user_manager

_log = logging.getLogger(__name__)


class ChatController:
    def __init__(self, llm, dispatch=None, mode="lesson", lang="en", user_id=None,
                 analyst=None, planner=None):
        self.llm = llm
        self._dispatch = dispatch or (lambda fn: fn())
        self.mode = mode
        self.current_lang = lang
        self.user_id = user_id
        # Имя преподавателя у ЭТОГО ученика (поле профиля teacher_name, пусто →
        # config.TEACHER_NAME). Обновляется при смене ученика и на каждом
        # запросе: имя видно и в чате (подпись реплики), и в промпте.
        self.teacher = user_manager.teacher_name(user_manager.get_user(user_id))
        self.history = []
        self.busy = False
        # роль-Аналитик (необязательна): разбирает реплики ПОСЛЕ ответа Учителя
        self.analyst = analyst

        # RAG (необязателен): методические заметки в промпт Учителя (режим урока)
        self.rag = None
        if config.RAG_ENABLED:
            try:
                self.rag = rag.RAG()
            except Exception as exc:
                print(f"⚠️ RAG недоступен: {exc}")

        # роль-Планировщик (необязательна): план урока в промпт Учителя.
        # План строится ОДИН раз за сессию В ФОНЕ (после первого ответа),
        # чтобы НЕ задерживать текст ответа: сам вызов модели небыстрый.
        self.planner = planner
        self._plan_text = ""
        self._plan_started = False

        # идущее ЗАНЯТИЕ по карте (lesson.py): {"title","type","topic"} или None.
        # В промпт подмешивается отдельным блоком (prompt_builder._lesson_block).
        self._lesson = None
        # ЭКЗАМЕН: сколько вопросов блока уже задано (None — не экзамен или
        # счёт ещё не начался). Число уходит в промпт: иначе модель не знает,
        # какой вопрос по счёту задаёт, и закрывает экзамен раньше времени
        # (живой прогон 25.10.2026 — закрыла на 8-м ответе из 10).
        self._exam_asked = None
        # True, пока Джейн отвечает на служебную реплику-затравку в начале
        # занятия: её нельзя считать ответом ученика (ни разбор, ни прогресс).
        self._opening = False

        # --- колбэки, которые выставляет интерфейс ---
        self.on_message = None    # (sender, text)      — добавить сообщение в чат
        self.on_status = None     # (text, color_key)   — статус-бейдж
        self.on_busy = None       # (busy: bool)        — блокировка кнопки отправки
        self.on_response = None   # (user_text, reply)  — удачный ответ (TTS и пр.)
        self.on_analysis = None   # (result: dict)      — разбор от Аналитика (или None)
        self.on_plan = None       # (plan_text: str)    — план урока построен (или "")

    # -----------------------------------------------------
    # Публичный интерфейс
    # -----------------------------------------------------
    def set_user(self, user_id):
        """Переключить ученика: история диалога у каждого своя, поэтому чистим."""
        self.user_id = user_id
        self.teacher = user_manager.teacher_name(user_manager.get_user(user_id))
        self.history = []
        self._reset_plan()
        profile_store.set_active_user(user_id)

    def set_mode(self, mode):
        self.mode = mode

    def set_language(self, lang):
        self.current_lang = lang

    def set_exam_asked(self, asked=None):
        """Сколько вопросов экзамена уже задано (None — счётчик не нужен)."""
        if asked is None:
            self._exam_asked = None
            return
        try:
            self._exam_asked = max(0, int(asked))
        except (TypeError, ValueError):
            self._exam_asked = None

    def set_lesson(self, lesson=None):
        """Задать идущее занятие (словарь {"title","type","topic"} или None).

        Только влияет на промпт Учителя: логика занятия живёт в app.py и
        lesson.py, контроллер остаётся «переговорщиком» с моделью.
        """
        self._lesson = dict(lesson) if isinstance(lesson, dict) else (
            {"title": str(lesson)} if lesson else None)

    def begin_lesson(self, lesson=None, student_text=""):
        """Джейн начинает занятие ПЕРВОЙ (служебная реплика, не ответ ученика).

        Ученик только что открыл урок и ещё не сказал ни слова — без этого
        он не знал бы, что делать. Затравка НЕ попадает ни в разбор Аналитика,
        ни в прогресс, ни в историю диалога (см. _opening).

        student_text — первая реплика ученика (когда Джейн начинает урок САМА,
        ученик уже поздоровался). Тогда просим модель сначала ответить на неё,
        а потом перейти к уроку, — иначе приветствие ученика потеряется.
        Пустая строка (по умолчанию) оставляет прежнюю затравку байт-в-байт.
        """
        if self.busy:
            return False
        if lesson is not None:
            self.set_lesson(lesson)
        title = (self._lesson or {}).get("title") or "the lesson"
        said = str(student_text or "").strip()
        intro = ""
        if said:
            # ЖАЛОБА УЧЕНИКА 25.10.2026: он сказал «hello», а преподаватель
            # попросил поздороваться ещё раз — потому что первое задание урока
            # «Hello / Hi» и есть приветствие. Теперь приветствие ученика
            # считается сделанным: реагируем и идём ДАЛЬШЕ по уроку.
            intro = (" The student has just said: \"%s\" — answer that briefly "
                     "first, then move on to the lesson. The greeting is already "
                     "done: do NOT ask the student to greet you again and do NOT "
                     "ask them to repeat a greeting word."
                     % said.replace('"', "'")[:200])
        self._opening = True
        return self.send(
            "[START OF LESSON] Topic: %s. Greet the student warmly in English "
            "and give the FIRST small task of this lesson (one thing at a time).%s"
            % (title, intro))

    def clear_history(self):
        self.history = []
        self._lesson = None
        self._opening = False
        self._exam_asked = None
        self._reset_plan()

    def _reset_plan(self):
        """Сбросить план урока: новый ученик/новая сессия → новый план."""
        self._plan_text = ""
        self._plan_started = False
        self._dispatch(lambda: self._emit(self.on_plan, ""))

    def send(self, user_text):
        """Отправляет реплику и асинхронно получает ответ."""
        if self.busy:
            return False
        self.busy = True
        self._emit(self.on_busy, True)
        self._emit(self.on_status, "● %s думает..." % self.teacher, "warn")
        threading.Thread(target=self._worker, args=(user_text,), daemon=True).start()
        return True

    # -----------------------------------------------------
    # Внутреннее
    # -----------------------------------------------------
    def _worker(self, user_text):
        """Фоновый поток: сеть не должна морозить окно.

        Роли вызываются ПОСЛЕДОВАТЕЛЬНО, но независимо: сначала Учитель
        (его ответ показываем сразу), затем Аналитик. Сбой Аналитика не
        мешает ответу Учителя (см. _safe_analyze / _record).
        """
        ok, payload = self._request(user_text)
        if not ok:
            self._dispatch(lambda: self._finish_error(payload))
            return
        # ответ Учителя — в окно сразу, не ждём Аналитика
        self._dispatch(lambda: self._show_reply(user_text, payload))
        analysis = self._safe_analyze(user_text, payload)
        self._dispatch(lambda: self._finish(user_text, payload, analysis))

    def _request(self, user_text):
        """Сборка промпта → запрос к модели → чистка ответа."""
        # Язык ответа выбирает САМА модель (мягкая политика в промпте). Здесь
        # лишь обновляем подсказку по ТЕКУЩЕЙ реплике и НЕ «залипаем»: раньше
        # одного русского вопроса хватало, чтобы Джейн отвечала по-русски до
        # конца сессии — даже на английские реплики.
        lang = "ru" if _is_russian(user_text) else "en"
        self.current_lang = lang

        # прогресс ИМЕННО этого ученика
        # уровень ученика учитывается при сборке промпта (A1..C1)
        # личность ученика (имя/пол) — чтобы Джейн знала имя и НЕ путала
        # грамматический род ученика со своим (женским)
        user = user_manager.get_user(self.user_id) or {}
        self.teacher = user_manager.teacher_name(user)   # имя из профиля
        level = user.get("level")
        student = {"name": user.get("name"),
                   "name_latin": user.get("name_latin"),
                   "gender": user.get("gender")}
        # методические заметки (RAG) и план урока (Планировщик) — только урок
        context = self._rag_context(user_text) if self.mode == "lesson" else ""
        # план читаем БЕЗ ожидания: если он ещё строится — отвечаем без него
        plan_text = self._plan_text if self.mode == "lesson" else ""
        lesson_block = self._lesson if self.mode == "lesson" else None
        # ЭКЗАМЕН (проверка блока): отдельный блок промпта «ровно 10 вопросов,
        # не учить, не подсказывать». Без флага промпт прежний байт-в-байт.
        exam_mode = bool((lesson_block or {}).get("exam"))
        # слова ученика (этап C): 1-2 из них Джейн может вплести в разговор
        words = self._prompt_words()
        # «сейчас» и «не повторяйся» — так Джейн знает дату/время и не задаёт
        # один и тот же вопрос про завтрак при каждом знакомстве
        system_prompt = prompt_builder.build_system_prompt(
            self.mode, profile_store.load(self.user_id), lang,
            level=level, student=student, context=context, plan=plan_text,
            lesson=lesson_block, now=datetime.now(), variety=True,
            english_only=bool(getattr(config, "ENGLISH_ONLY", False)),
            american=bool(getattr(config, "AMERICAN_ENGLISH", True)),
            words=words, teacher=self.teacher,
            exam=exam_mode, exam_questions=(exam_mod.QUESTIONS if exam_mode else None),
            hesitation=True,
            word_forms=True,          # lie/lay и прочие слова с двумя значениями
            exam_asked=(self._exam_asked if exam_mode else None))   # повтор — не ошибка

        print(f"📤 Язык ответа: {'РУССКИЙ' if lang == 'ru' else 'ENGLISH'}")

        ok, raw = self._ask_model(system_prompt, user_text)
        if not ok and llm_client.is_context_error(raw):
            # Запрос не влез в память модели. Сервер сам ничего не обрезает —
            # повторяем с КОРОТКОЙ историей (и, если надо, без RAG), чтобы
            # ученик получил ответ, а не бессмысленную заглушку.
            print("✂️ Не влезло в память модели → повторяю с короткой историей")
            system_prompt = prompt_builder.build_system_prompt(
                self.mode, profile_store.load(self.user_id), lang,
                level=level, student=student,
                context="" if getattr(config, "CONTEXT_RETRY_RAG", True) else context,
                plan=plan_text,
                lesson=lesson_block, now=datetime.now(), variety=True,
                english_only=bool(getattr(config, "ENGLISH_ONLY", False)),
                american=bool(getattr(config, "AMERICAN_ENGLISH", True)),
                words=words, teacher=self.teacher,
            exam=exam_mode, exam_questions=(exam_mod.QUESTIONS if exam_mode else None),
            hesitation=True,
            word_forms=True,          # lie/lay и прочие слова с двумя значениями
            exam_asked=(self._exam_asked if exam_mode else None))   # повтор — не ошибка
            ok, raw = self._ask_model(system_prompt, user_text, short_history=True)
        if not ok:
            return False, self._explain(raw)

        cleaned = prompt_builder.clean_response(raw)
        if not cleaned:
            cleaned = prompt_builder.fallback_response(lang)
        return True, cleaned

    def _ask_model(self, system_prompt, user_text, short_history=False):
        """Один вызов Учителя: промпт + история + реплика ученика.

        short_history=True — оставить только последние строки истории
        (config.CONTEXT_RETRY_LINES): так делаем повтор, если запрос не
        влез в память модели.
        """
        history = self.history
        if short_history:
            keep = max(0, int(getattr(config, "CONTEXT_RETRY_LINES", 2) or 0))
            history = self.history[-keep:] if keep else []
        messages = prompt_builder.build_messages(system_prompt, history, user_text)
        return self.llm.complete(
            messages,
            max_tokens=config.LLM_CHAT_MAX_TOKENS,
            temperature=0.5,
            stop=["<|thought|>", "<end_of_turn>"],
        )

    @staticmethod
    def _explain(raw):
        """Причина сбоя понятными словами (было: безликое «Error: 400»).

        Повтор с короткой историей не помог — значит, запрос не влезает в
        память модели сам по себе. Ученику нужно знать, что делать.
        """
        if llm_client.is_context_error(raw):
            return ("⚠️ Ответ не уместился в память модели даже с короткой "
                    "историей. Скажи короткую фразу или начни урок с карты — "
                    "история диалога сбросится.")
        return raw

    def _prompt_words(self):
        """Слова ученика для необязательного блока промпта (этап C).

        Пусто, если система слов выключена, этап C выключен или слов нет —
        тогда промпт остаётся прежним. Ошибка чтения профиля не должна
        ломать ответ: молча отвечаем без блока.
        """
        if not getattr(config, "VOCAB_ENABLED", True):
            return []
        if not getattr(config, "VOCAB_IN_PROMPT", True):
            return []
        try:
            cards = profile_store.vocabulary_cards(self.user_id)
            return vocabulary.prompt_words(
                cards, limit=getattr(config, "VOCAB_PROMPT_LIMIT", 4))
        except Exception as exc:
            print("⚠️ Слова для промпта не прочитаны: %s" % exc)
            return []

    def _ensure_plan_async(self):
        """Построить план урока В ФОНЕ (не блокируя ответ Учителя).

        Планировщик — тяжёлый вызов модели (несколько секунд), поэтому
        запускаем его ОТДЕЛЬНЫМ потоком ПОСЛЕ первого ответа, пока ученик
        читает. План появится к следующей реплике. Строится один раз.
        """
        if self.planner is None or self._plan_started or self._plan_text:
            return
        self._plan_started = True
        threading.Thread(target=self._build_plan_bg, daemon=True).start()

    def _build_plan_bg(self):
        """Фон: собрать план урока и запомнить текст. Сбой не критичен."""
        try:
            user = user_manager.get_user(self.user_id) or {}
            context = self._rag_context("lesson design task cycle feedback scaffolding")
            plan = self.planner.plan(profile_store.load(self.user_id),
                                     level=user.get("level"), mode="lesson",
                                     context=context)
            self._plan_text = self.planner.format_plan(plan)
            if self._plan_text:
                self._dispatch(lambda: self._emit(self.on_plan, self._plan_text))
        except Exception as exc:
            print(f"⚠️ Планировщик недоступен: {exc}")
            self._plan_text = ""

    def _rag_context(self, query):
        """Методический контекст (RAG) для промпта Учителя.

        Пусто, если RAG выключен/недоступен или ничего не нашлось — тогда
        промпт не меняется. Сбой RAG не должен мешать ответу Учителя.
        """
        if self.rag is None:
            return ""
        try:
            return self.rag.build_context(query, top_k=config.RAG_TOP_K)
        except Exception as exc:
            print(f"⚠️ RAG: контекст не собран ({exc})")
            return ""

    def _show_reply(self, user_text, response):
        """Главный поток: показать ответ Учителя как можно раньше."""
        self._emit(self.on_message, self.teacher, response)
        self._emit(self.on_response, user_text, response)

    def _finish_error(self, payload):
        """Главный поток: ошибка Учителя.

        Учитель всегда «отвечает» ученику — пусть и сообщением об ошибке;
        Аналитик в этом случае не запускается вовсе.
        """
        self.busy = False
        self._emit(self.on_busy, False)
        self._emit(self.on_message, self.teacher, f"[Ошибка] {payload}")
        self._emit(self.on_status, "● Ошибка", "err")

    def _safe_analyze(self, user_text, reply):
        """Разбор реплики Аналитиком. Любая проблема → None (без исключений)."""
        if self._opening:            # служебная затравка — это не ответ ученика
            return None
        if self.analyst is None or self.mode != "lesson":
            return None
        try:
            level = (user_manager.get_user(self.user_id) or {}).get("level")
            return self.analyst.analyze(user_text, teacher_reply=reply,
                                        mode=self.mode, level=level)
        except Exception as exc:
            print(f"⚠️ Аналитик недоступен: {exc}")
            return None

    def _record(self, user_text, response, analysis):
        """Прогресс: есть разбор Аналитика → структурно, иначе — прежняя эвристика."""
        if analysis and analysis.get("ok"):
            try:
                return profile_store.record_analysis(analysis, user_text, response, self.user_id)
            except Exception as exc:
                print(f"⚠️ Запись разбора не удалась: {exc}")
        return profile_store.record_from_dialogue(user_text, response, self.user_id)

    def _finish(self, user_text, response, analysis):
        """Главный поток: запись прогресса, история, статус, снятие «занят»."""
        self.busy = False
        self._emit(self.on_busy, False)

        # Разбор пишем в профиль, но служебные заметки в чат НЕ показываем:
        # ученику не нужны строки вида «📝 *Разбор: A/P · ошибок 3*» между
        # репликами Джейн. Хочешь вывести — подпишись на on_analysis.
        opening = self._opening
        self._opening = False
        if opening:
            # начало занятия: ни разбора, ни прогресса, ни «грязной» истории
            self._emit(self.on_analysis, None)
            self.history.append(f"Assistant: {response}")
            if len(self.history) > 10:
                self.history = self.history[-8:]
            self._emit(self.on_status, "● Готов", "ok")
            return

        notes = self._record(user_text, response, analysis)
        if notes:
            _log.debug("прогресс: %s", notes)
        self._emit(self.on_analysis, analysis)

        self.history.append(f"Student: {user_text}")
        self.history.append(f"Assistant: {response}")
        if len(self.history) > 10:
            self.history = self.history[-8:]

        # план урока строим В ФОНЕ (после ответа) — чтобы не тормозить текст
        if self.mode == "lesson":
            self._ensure_plan_async()

        self._emit(self.on_status, "● Готов", "ok")

    @staticmethod
    def _emit(callback, *args):
        if callback is None:
            return
        try:
            callback(*args)
        except Exception as exc:
            print(f"⚠️ Ошибка в колбэке чата: {exc}")


_RUSSIAN_CHARS = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")


def _is_russian(text):
    return any(c in _RUSSIAN_CHARS for c in (text or "").lower())
