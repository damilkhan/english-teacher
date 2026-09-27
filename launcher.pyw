# -*- coding: utf-8 -*-
# =========================================================
# LAUNCHER.PYW — запуск English Teacher как обычной программы
# =========================================================
# Зачем нужен:
#   1) Принудительно включает UTF-8 для вывода. Без этого запуск
#      двойным кликом падает с UnicodeEncodeError на первом же
#      print() с эмодзи (консоль Windows = cp1251), ещё до того
#      как появится окно.
#   2) Запускает llama-server и ждёт его готовности, не блокируя GUI.
#   3) Пишет весь вывод и ошибки в logs\app.log (терминала-то нет).
#   4) Показывает понятное окно с ошибкой вместо мгновенного закрытия.
#   5) Запрещает запуск второй копии приложения.
#
# Запускать так:  run_teacher.bat   (двойной клик)
#            или: pythonw.exe launcher.pyw
#            или: python launcher.pyw  (с консолью, для отладки)
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


def _msgbox(title, text, flags=0x10):
    """Окно с ошибкой (0x10 = иконка ошибки). Работает даже без tkinter."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), flags)
    except Exception:
        _log("MessageBox недоступен: %s" % traceback.format_exc())


def _single_instance():
    """Не даём запустить вторую копию. Возвращает handle или None."""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, "EnglishTeacherApp_SingleInstance_v1")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return None
        return handle
    except Exception:
        _log("Проверка единственного экземпляра не удалась: %s" % traceback.format_exc())
        return "no-check"


def main():
    _log("Запуск English Teacher")
    _log("Python %s | %s" % (sys.version.split()[0], sys.executable))
    _log("Рабочая папка: %s" % APP_DIR)

    mutex = _single_instance()
    if mutex is None:
        _msgbox("English Teacher",
                "Приложение уже запущено.\n\n"
                "Найдите окно «English Teacher — Jane»\n"
                "на панели задач.", 0x30)
        return

    # ---------- 1. Проверка файлов моделей ----------
    try:
        import config
        if not config.check_paths():
            _msgbox("English Teacher",
                    "Не найдены файлы моделей.\n\n"
                    "Проверьте папку models\\ и пути в config.py.\n"
                    "Подробности: logs\\app.log", 0x10)
            return
        _log("Проверка путей config.py: OK")
    except Exception:
        _log(traceback.format_exc())
        _msgbox("English Teacher",
                "Ошибка при чтении config.py:\n\n%s" % traceback.format_exc(limit=2))
        return

    # ---------- 2. Запуск llama-server в фоне ----------
    state = {"ready": False, "error": None}

    def _boot_server():
        try:
            import server_manager
            if server_manager.is_server_ready():
                _log("llama-server уже отвечает на /health — старт не нужен")
                state["ready"] = True
                return
            _log("Старт llama-server...")
            if not server_manager.start_server():
                state["error"] = ("llama-server.exe или .gguf не найдены.\n"
                                  "Проверьте SERVER_PATH и MODEL_PATH в server_manager.py")
                return
            _log("Ожидание готовности модели (до 180 с)...")
            if server_manager.wait_for_server(timeout=180):
                state["ready"] = True
                _log("llama-server готов")
            else:
                state["error"] = "Модель не ответила за 180 секунд."
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
        counter[0] += 1
        try:
            if state["ready"]:
                app.check_server()
                app.window.title("English Teacher — Jane")
                _log("Интерфейс активен, сервер готов")
                return
            if state["error"]:
                app.check_server()
                app.window.title("English Teacher — Jane ⚠ сервер недоступен")
                _log("Сервер не поднялся: %s" % state["error"])
                _msgbox("English Teacher",
                        "LLM-сервер не запустился:\n\n%s\n\n"
                        "Приложение работает, но ответов не будет.\n"
                        "Лог: logs\\app.log" % state["error"])
                return
            app.window.title("English Teacher — Jane  ⏳ загрузка модели...")
            if counter[0] < 250:
                app.window.after(2000, _watch)
        except Exception:
            _log(traceback.format_exc())

    app.window.after(2000, _watch)

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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log(traceback.format_exc())
        _msgbox("English Teacher", "Критическая ошибка:\n\n%s" % traceback.format_exc(limit=3))
    finally:
        try:
            _log_fh.close()
        except Exception:
            pass
