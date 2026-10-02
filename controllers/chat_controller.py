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

import threading

import profile_store
import prompt_builder
import user_manager


class ChatController:
    def __init__(self, llm, dispatch=None, mode="lesson", lang="en", user_id=None):
        self.llm = llm
        self._dispatch = dispatch or (lambda fn: fn())
        self.mode = mode
        self.current_lang = lang
        self.user_id = user_id
        self.history = []
        self.busy = False

        # --- колбэки, которые выставляет интерфейс ---
        self.on_message = None    # (sender, text)      — добавить сообщение в чат
        self.on_status = None     # (text, color_key)   — статус-бейдж
        self.on_busy = None       # (busy: bool)        — блокировка кнопки отправки
        self.on_response = None   # (user_text, reply)  — удачный ответ (TTS и пр.)

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
        """Фоновый поток: сеть не должна морозить окно."""
        ok, payload = self._request(user_text)
        self._dispatch(lambda: self._finish(user_text, ok, payload))

    def _request(self, user_text):
        """Сборка промпта → запрос к модели → чистка ответа."""
        # написал по-русски → отвечаем по-русски (как было в gui.py)
        if _is_russian(user_text):
            self.current_lang = "ru"
        lang = self.current_lang

        # прогресс ИМЕННО этого ученика
        # уровень ученика учитывается при сборке промпта (A1..C1)
        level = (user_manager.get_user(self.user_id) or {}).get("level")
        system_prompt = prompt_builder.build_system_prompt(
            self.mode, profile_store.load(self.user_id), lang, level=level)
        prompt = prompt_builder.build_conversation_prompt(system_prompt, self.history, user_text, lang)

        print(f"📤 Язык ответа: {'РУССКИЙ' if lang == 'ru' else 'ENGLISH'}")

        ok, raw = self.llm.complete(
            prompt,
            max_tokens=120,
            temperature=0.5,
            stop=["<|thought|>", "<end_of_turn>"],
        )
        if not ok:
            return False, raw

        cleaned = prompt_builder.clean_response(raw)
        if not cleaned:
            cleaned = prompt_builder.fallback_response(lang)
        return True, cleaned

    def _finish(self, user_text, ok, payload):
        """Главный поток: показываем результат и обновляем состояние."""
        self.busy = False
        self._emit(self.on_busy, False)

        if not ok:
            self._emit(self.on_message, "Джейн", f"[Ошибка] {payload}")
            self._emit(self.on_status, "● Ошибка", "err")
            return

        response = payload
        self._emit(self.on_message, "Джейн", response)

        # прогресс ученика — бизнес-логика, не дело GUI
        for note in profile_store.record_from_dialogue(user_text, response, self.user_id):
            self._emit(self.on_message, "Джейн", note)

        self.history.append(f"Student: {user_text}")
        self.history.append(f"Assistant: {response}")
        if len(self.history) > 10:
            self.history = self.history[-8:]

        self._emit(self.on_status, "● Готов", "ok")
        self._emit(self.on_response, user_text, response)

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
