# -*- coding: utf-8 -*-
# =========================================================
# LAUNCHER.PYW — запуск English Teacher как обычной программы
# =========================================================
# Что делает:
#   1) Включает UTF-8 на весь процесс. Без этого запуск двойным кликом
#      падал с UnicodeEncodeError на первом же print() с эмодзи
#      (консоль Windows = cp1251) ещё до появления окна.
#   2) Поднимает llama-server в фоне БЕЗ окна консоли
#      (CREATE_NO_WINDOW в server_manager.py) и ждёт загрузку модели.
#   3) Пишет вывод приложения в logs\app.log, вывод сервера —
#      в logs\llama-server.log.
#   4) Показывает нормальное окно с ошибкой вместо мгновенного закрытия.
#   5) Запрещает запуск второй копии.
#
# Запускать так:
#   English Teacher.vbs   (двойной клик — вообще без консоли)
#   run_teacher.bat       (то же самое)
#   run_teacher.bat debug (с консолью, для отладки)
# =========================================================

import os
import sys
import threading
import traceback
import datetime

# ---------- рабочая папка = папка проекта ----------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# ---------- UTF-8 на весь процесс ----------
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

LOG_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")


class _LogStream:
    """Замена sys.stdout/stderr: пишет в utf-8-файл, не падает на эмодзи."""

    def __init__(self, fh):
        self._fh = fh

    def write(self, data):
        try:
            self._fh.write(data)
        except Exception:
            pass
        return len(data)

    def flush(self):
        try:
            self._fh.flush()
        except Exception:
            pass

    @property
    def encoding(self):
        return "utf-8"

    def isatty(self):
        return False

    def fileno(self):
        raise OSError("log stream has no file descriptor")


_log_fh = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
sys.stdout = _LogStream(_log_fh)
sys.stderr = _LogStream(_log_fh)
_log_fh.write("\n" + "=" * 70 + "\n")


def _log(msg):
    print("[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


MB_TOPMOST = 0x40000      # сообщение поверх всех окон (иначе его не видно)


def _msgbox(title, text, flags=0x10):
    """Окно с сообщением (0x10 = иконка ошибки, 0x40 = инфо).

    Всегда поверх остальных окон: раньше диалог мог уйти за другие окна, и
    казалось, что приложение «зависло».
    """
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(text), str(title),
                                         flags | MB_TOPMOST)
    except Exception:
        _log("MessageBox недоступен: %s" % traceback.format_exc())


MUTEX_NAME = "EnglishTeacherApp_SingleInstance_v2"
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9


def _find_app_window():
    """Ищет верхнее окно, в заголовке которого есть «English Teacher».

    Возвращает (hwnd, pid) или (None, None). Нужно, чтобы отличать РАБОТАЮЩЕЕ
    приложение от зависшего процесса: у живого приложения окно есть, а у
    «застрявшего» (процесс остался, окно закрыто) — нет.
    """
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        found = {}

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                         wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if "English Teacher" in buf.value:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                found["hwnd"], found["pid"] = hwnd, pid.value
                return False        # дальше искать не нужно
            return True

        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        return found.get("hwnd"), found.get("pid")
    except Exception:
        _log("Поиск окна приложения не удался: %s" % traceback.format_exc())
        return None, None


def _raise_window(hwnd):
    """Разворачивает окно и выводит его на передний план."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _acquire_instance():
    """Можно ли стартовать? Возвращает (can_start: bool, handle).

    * мьютекс занят ДРУГИМ процессом, у которого ЕСТЬ окно «English Teacher» —
      окно поднимаем наверх и стартовать нельзя;
    * мьютекс занят, но окна нет: процесс завис/остался без окна — считаем
      прошлый запуск мёртвым и стартуем, чтобы не блокировать запуск навсегда
      (лечение «залипшего» мьютекса — именно из-за него писало «уже запущено»,
      когда приложения фактически не было).
    """
    handle = None
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        already = (kernel32.GetLastError() == ERROR_ALREADY_EXISTS)
    except Exception:
        _log("Проверка единственного экземпляра не удалась: %s" % traceback.format_exc())
        return True, "no-check"

    if not already:
        return True, handle

    hwnd, pid = _find_app_window()
    if hwnd and pid != os.getpid():
        _log("Уже работает другое окно «English Teacher» (pid %s) — поднимаю наверх" % pid)
        _raise_window(hwnd)
        return False, handle

    _log("Мьютекс занят, но окна «English Teacher» нет — прошлый запуск завис, "
         "продолжаю запуск заново")
    return True, handle


def _force_exit(code=0):
    """Мгновенно завершает процесс, не дожидаясь «висящих» потоков."""
    try:
        _log_fh.flush()
    except Exception:
        pass
    os._exit(code)


def main():
    _log("Запуск English Teacher")
    _log("Python %s | %s" % (sys.version.split()[0], sys.executable))
    _log("Рабочая папка: %s" % APP_DIR)

    can_start, mutex = _acquire_instance()
    if not can_start:
        _msgbox("English Teacher",
                "Приложение уже запущено.\n\n"
                "Окно «English Teacher — Jane» выведено\n"
                "на передний план.", 0x40)      # 0x40 = иконка информации
        return

    # ---------- 1. Проверка файлов моделей ----------
    try:
        import config
        if not config.check_paths():
            _msgbox("English Teacher",
                    "Не найдены нужные файлы.\n\n"
                    "Проверьте MODEL_PATH и SERVER_EXE_PATH в config.py,\n"
                    "а также папку models\.\n"
                    "Подробности: logs\\app.log", 0x10)
            return
        _log("Проверка путей config.py: OK")
    except Exception:
        _log(traceback.format_exc())
        _msgbox("English Teacher",
                "Ошибка при чтении config.py:\n\n%s" % traceback.format_exc(limit=2))
        return

    # ---------- 2. llama-server в фоне ----------
    state = {"ready": False, "error": None, "note": "старт"}

    def _on_progress(server_state, message, elapsed):
        state["note"] = "%s (%.0f с)" % (message, elapsed)
        _log("Состояние сервера: %s — %s" % (server_state, message))

    def _boot_server():
        try:
            import server_manager
            _log("Проверка llama-server...")
            if not server_manager.start_server():
                state["error"] = server_manager.get_last_error() or "Не удалось запустить llama-server."
                return
            _log("Ожидание готовности модели (до %d с)..." % server_manager.STARTUP_TIMEOUT)
            if server_manager.wait_for_server(on_progress=_on_progress):
                state["ready"] = True
                _log("llama-server готов")
            else:
                state["error"] = server_manager.get_last_error() or "Модель не ответила."
        except Exception as exc:
            state["error"] = "Ошибка запуска сервера: %s" % exc
            _log(traceback.format_exc())

    threading.Thread(target=_boot_server, daemon=True).start()

    # ---------- 3. Интерфейс ----------
    try:
        import gui
        app = gui.EnglishTeacherApp()
    except Exception:
        _log(traceback.format_exc())
        _msgbox("English Teacher",
                "Не удалось запустить интерфейс:\n\n%s"
                % traceback.format_exc(limit=3))
        return

    def _watch(counter=[0]):
        """Обновляет заголовок окна, пока модель грузится. Индикатор внутри
        приложения обновляется самостоятельно (gui._poll_server)."""
        counter[0] += 1
        try:
            if state["ready"]:
                app.window.title("English Teacher — Jane")
                app.check_server()
                _log("Интерфейс активен, сервер готов")
                return
            if state["error"]:
                app.check_server()
                app.window.title("English Teacher — Jane ⚠ сервер недоступен")
                _log("Сервер не поднялся: %s" % state["error"])
                _msgbox("English Teacher",
                        "LLM-сервер не запустился:\n\n%s\n\n"
                        "Приложение работает, но отвечать не сможет.\n"
                        "Лог сервера: logs\\llama-server.log" % state["error"])
                return
            app.window.title("English Teacher — Jane  ⏳ %s" % state["note"])
            if counter[0] < 400:
                app.window.after(1000, _watch)
        except Exception:
            _log(traceback.format_exc())

    app.window.after(1500, _watch)

    # ---------- 4. Главный цикл ----------
    try:
        app.run()
    except Exception:
        _log(traceback.format_exc())
        _msgbox("English Teacher",
                "Приложение аварийно завершилось:\n\n%s" % traceback.format_exc(limit=3))
        return
    finally:
        _log("Окно закрыто, выход")
        try:
            import server_manager
            server_manager.stop_server()
        except Exception:
            pass
        # Жёсткий выход: если какой-то поток (SDL/порт-аудио и т.п.) остался
        # жив, обычный выход затягивался, процесс висел без окна и держал
        # мьютекс — из-за этого следующий запуск писал «уже запущено».
        _force_exit()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log(traceback.format_exc())
        _msgbox("English Teacher", "Критическая ошибка:\n\n%s" % traceback.format_exc(limit=3))
    finally:
        _log("Процесс завершён")
        try:
            _log_fh.flush()
            _log_fh.close()
        except Exception:
            pass
        os._exit(0)
