# -*- coding: utf-8 -*-
# =========================================================
# CONTROLLERS/LEVEL_TEST_CONTROLLER.PY — асинхронная обёртка теста уровня
# =========================================================
# Генерация вопроса ходит в LLM (секунды), поэтому НЕЛЬЗЯ делать это в
# главном потоке Tk. Контроллер гоняет level_test в фоновом потоке и
# возвращает результат через dispatch() — как ChatController, и так же
# не импортирует tkinter (тестируется без окна).
#
# UI знает только эти методы:
#   start(user_id, on_question, on_result, on_error)
#   answer(user_id, answer, on_feedback, on_question, on_result, on_error)
#   cancel(user_id)
# =========================================================

import threading

import level_test


class LevelTestController:
    def __init__(self, dispatch=None):
        self._dispatch = dispatch or (lambda fn: fn())
        self.busy = False

    # -----------------------------------------------------
    def start(self, user_id, on_question, on_result=None, on_error=None):
        """Запускает тест и отдаёт первый вопрос (в главном потоке)."""
        if self.busy:
            return False
        self.busy = True

        def worker():
            try:
                question = level_test.start_test(user_id)
            except Exception as exc:
                self.busy = False
                self._dispatch(lambda: self._emit(on_error, str(exc)))
                return
            self.busy = False
            self._dispatch(lambda: self._emit(on_question, question))

        threading.Thread(target=worker, daemon=True).start()
        return True

    # -----------------------------------------------------
    def answer(self, user_id, answer, on_feedback=None,
               on_question=None, on_result=None, on_error=None):
        """Проверяет ответ и либо задаёт следующий вопрос, либо финал."""
        if self.busy:
            return False
        self.busy = True

        def worker():
            try:
                check = level_test.check_answer(user_id, answer)
                self._dispatch(lambda: self._emit(on_feedback, check))

                nxt = level_test.get_next_question(user_id, answer)
                if nxt.get("finished"):
                    result = level_test.get_result(user_id)
                    self.busy = False
                    self._dispatch(lambda: self._emit(on_result, result))
                else:
                    self.busy = False
                    self._dispatch(lambda: self._emit(on_question, nxt))
            except Exception as exc:
                self.busy = False
                self._dispatch(lambda: self._emit(on_error, str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        return True

    # -----------------------------------------------------
    def cancel(self, user_id):
        """Прервать тест: сессию выкидываем, профиль не трогаем."""
        try:
            return level_test.cancel_test(user_id)
        except Exception:
            return False

    # -----------------------------------------------------
    @staticmethod
    def _emit(callback, *args):
        if callback is None:
            return
        try:
            callback(*args)
        except Exception as exc:
            print("⚠️ Ошибка в колбэке теста уровня: %s" % exc)
