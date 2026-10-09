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

import config
import profile_store
import prompt_builder
import rag
import user_manager

_log = logging.getLogger(__name__)


class ChatController:
    def __init__(self, llm, dispatch=None, mode="lesson", lang="en", user_id=None,
                 analyst=None):
        self.llm = llm
        self._dispatch = dispatch or (lambda fn: fn())
        self.mode = mode
        self.current_lang = lang
        self.user_id = user_id
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

        # --- колбэки, которые выставляет интерфейс ---
        self.on_message = None    # (sender, text)      — добавить сообщение в чат
        self.on_status = None     # (text, color_key)   — статус-бейдж
        self.on_busy = None       # (busy: bool)        — блокировка кнопки отправки
        self.on_response = None   # (user_text, reply)  — удачный ответ (TTS и пр.)
        self.on_analysis = None   # (result: dict)      — разбор от Аналитика (или None)

    # -----------------------------------------------------
    # Публичный интерфейс
    # -----------------------------------------------------
    def set_user(self, user_id):
        """Переключить ученика: история диалога у каждого своя, поэтому чистим."""
        self.user_id = user_id
        self.history = []
        profile_store.set_active_user(user_id)

    def set_mode(self, mode):
        self.mode = mode

    def set_language(self, lang):
        self.current_lang = lang

    def clear_history(self):
        self.history = []

    def send(self, user_text):
        """Отправляет реплику и асинхронно получает ответ."""
        if self.busy:
            return False
        self.busy = True
        self._emit(self.on_busy, True)
        self._emit(self.on_status, "● Джейн думает...", "warn")
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
        level = user.get("level")
        student = {"name": user.get("name"), "gender": user.get("gender")}
        # методические заметки (RAG) — только для режима урока
        context = self._rag_context(user_text) if self.mode == "lesson" else ""
        system_prompt = prompt_builder.build_system_prompt(
            self.mode, profile_store.load(self.user_id), lang,
            level=level, student=student, context=context)
        prompt = prompt_builder.build_conversation_prompt(system_prompt, self.history, user_text, lang)

        print(f"📤 Язык ответа: {'РУССКИЙ' if lang == 'ru' else 'ENGLISH'}")

        ok, raw = self.llm.complete(
            prompt,
            max_tokens=config.LLM_CHAT_MAX_TOKENS,
            temperature=0.5,
            stop=["<|thought|>", "<end_of_turn>"],
        )
        if not ok:
            return False, raw

        cleaned = prompt_builder.clean_response(raw)
        if not cleaned:
            cleaned = prompt_builder.fallback_response(lang)
        return True, cleaned

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
        self._emit(self.on_message, "Джейн", response)
        self._emit(self.on_response, user_text, response)

    def _finish_error(self, payload):
        """Главный поток: ошибка Учителя.

        Учитель всегда «отвечает» ученику — пусть и сообщением об ошибке;
        Аналитик в этом случае не запускается вовсе.
        """
        self.busy = False
        self._emit(self.on_busy, False)
        self._emit(self.on_message, "Джейн", f"[Ошибка] {payload}")
        self._emit(self.on_status, "● Ошибка", "err")

    def _safe_analyze(self, user_text, reply):
        """Разбор реплики Аналитиком. Любая проблема → None (без исключений)."""
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
        notes = self._record(user_text, response, analysis)
        if notes:
            _log.debug("прогресс: %s", notes)
        self._emit(self.on_analysis, analysis)

        self.history.append(f"Student: {user_text}")
        self.history.append(f"Assistant: {response}")
        if len(self.history) > 10:
            self.history = self.history[-8:]

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
