# -*- coding: utf-8 -*-
# =========================================================
# SERVER_MANAGER.PY — запуск и контроль локального llama-server
# =========================================================
# Проверенные на этой машине факты (важно для логики ниже):
#   * модель Gemma-4-E4B грузится ~30 секунд;
#   * первые ~14 с порт 8080 вообще закрыт (отказ соединения);
#   * дальше и до конца загрузки /health отдаёт
#         503 {"error":{"message":"Loading model"}}
#     и только после загрузки — 200 {"status":"ok"};
#   * llama-server — консольная программа, поэтому запускать её надо
#     с флагом CREATE_NO_WINDOW, иначе вылезает окно терминала.
#
# Поэтому "сервер не отвечает" ≠ "сервер не запущен":
# есть три состояния — ready / loading / offline.
# =========================================================

import atexit
import os
import socket
import subprocess
import time

import requests

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
SERVER_LOG = os.path.join(LOG_DIR, "llama-server.log")

SERVER_PATH = getattr(config, "SERVER_EXE_PATH", r"D:\llama.cpp\llama-server.exe")
MODEL_PATH = getattr(config, "MODEL_PATH", "")
HOST = getattr(config, "LLM_HOST", "127.0.0.1")
PORT = int(getattr(config, "LLM_PORT", 8080))
BASE_URL = getattr(config, "LLM_BASE_URL", "http://%s:%d" % (HOST, PORT))
HEALTH_URL = getattr(config, "LLM_HEALTH_URL", BASE_URL + "/health")
CONTEXT = int(getattr(config, "SERVER_CONTEXT", 4096))
STARTUP_TIMEOUT = int(getattr(config, "SERVER_STARTUP_TIMEOUT", 240))

# Windows: не создавать окно консоли для дочернего процесса
CREATE_NO_WINDOW = 0x08000000
_NO_WINDOW = dict(creationflags=CREATE_NO_WINDOW) if os.name == "nt" else {}

# Запросы к localhost не должны уходить в системный прокси (VPN/Amnezia и т.п.)
_session = requests.Session()
_session.trust_env = False

server_process = None      # Popen нашего процесса (если мы его запускали)
owns_server = False        # True = сервер запустили мы и должны его закрыть
last_error = None          # текст последней ошибки — для окна сообщения


# ---------------------------------------------------------
# Диагностика
# ---------------------------------------------------------
def get_last_error():
    return last_error


def tail_log(lines=15):
    """Последние строки logs\\llama-server.log — чтобы понять, почему упал."""
    try:
        with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
            data = fh.read().strip().splitlines()
        return "\n".join(data[-lines:]) if data else "(лог пуст)"
    except Exception:
        return "(лог недоступен)"


def _port_open():
    """Занят ли вообще порт (любым процессом)."""
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect((HOST, PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _llama_server_pids():
    """PID всех запущенных llama-server.exe (в т.ч. чужих/зависших)."""
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(
            ["tasklist", "/fi", "imagename eq llama-server.exe", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=15, **_NO_WINDOW
        ).stdout or ""
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def _kill_pids(pids):
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=15, **_NO_WINDOW)
        except Exception:
            pass


# ---------------------------------------------------------
# Состояние сервера
# ---------------------------------------------------------
def health_state(timeout=2.0):
    """Возвращает (state, пояснение).

    state:
        'ready'   — сервер отвечает, можно работать;
        'loading' — процесс есть, модель ещё грузится (503 или порт занят);
        'offline' — на порту никого нет.
    """
    try:
        resp = _session.get(HEALTH_URL, timeout=timeout)
    except requests.exceptions.RequestException:
        resp = None

    if resp is not None:
        if resp.status_code == 200:
            return "ready", "сервер готов"
        if resp.status_code == 503:
            return "loading", "модель загружается"
        return "loading", "сервер ответил кодом %s" % resp.status_code

    if _port_open():
        return "loading", "порт %d занят, сервер инициализируется" % PORT
    if _llama_server_pids():
        return "loading", "llama-server запущен, идёт загрузка модели"
    return "offline", "порт %d свободен" % PORT


def is_server_ready():
    """Короткий ответ: можно ли уже отправлять промпты."""
    return health_state(timeout=1.0)[0] == "ready"


# ---------------------------------------------------------
# Запуск / остановка
# ---------------------------------------------------------
def start_server():
    """Поднимает llama-server БЕЗ окна консоли. Второй экземпляр не создаёт."""
    global server_process, owns_server, last_error

    state, msg = health_state()
    if state != "offline":
        # Кто-то (мы в прошлый раз или пользователь) уже поднял сервер.
        print("ℹ️ llama-server уже работает (%s) — второй экземпляр не нужен" % msg)
        owns_server = False
        return True

    stray = _llama_server_pids()
    if stray:
        print("⚠️ Найдены незакрытые llama-server (PID %s) — закрываю перед стартом"
              % ", ".join(str(p) for p in stray))
        _kill_pids(stray)
        time.sleep(1.0)

    if not os.path.exists(SERVER_PATH):
        last_error = "Не найден llama-server.exe:\n%s\n\nПроверьте SERVER_EXE_PATH в config.py" % SERVER_PATH
        print("❌ " + last_error)
        return False
    if not os.path.exists(MODEL_PATH):
        last_error = "Не найдена модель:\n%s\n\nПроверьте MODEL_PATH в config.py" % MODEL_PATH
        print("❌ " + last_error)
        return False

    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        log_fh = open(SERVER_LOG, "a", encoding="utf-8", errors="replace", buffering=1)
        log_fh.write("\n" + "=" * 70 + "\n[%s] СТАРТ llama-server\n%s\n"
                     % (time.strftime("%Y-%m-%d %H:%M:%S"), MODEL_PATH))
    except Exception as exc:
        last_error = "Не удалось открыть лог сервера: %s" % exc
        print("❌ " + last_error)
        return False

    args = [SERVER_PATH, "-m", MODEL_PATH, "-c", str(CONTEXT),
            "--host", HOST, "--port", str(PORT), "--jinja"]
    print("🚀 Запуск llama-server (без окна консоли)...")
    try:
        server_process = subprocess.Popen(
            args,
            cwd=os.path.dirname(SERVER_PATH),
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception as exc:
        last_error = "Не удалось запустить llama-server:\n%s" % exc
        print("❌ " + last_error)
        return False

    owns_server = True
    atexit.register(stop_server)
    return True


def wait_for_server(timeout=None, on_progress=None):
    """Ждёт готовности модели.

    on_progress(state, message, elapsed_sec) вызывается при смене состояния —
    удобно, чтобы писать прогресс в статус приложения.
    """
    global last_error
    if timeout is None:
        timeout = STARTUP_TIMEOUT
    started = time.time()
    last_state = None

    while time.time() - started < timeout:
        state, msg = health_state(timeout=1.5)

        if state == "ready":
            print("✅ llama-server готов (%.1f с)" % (time.time() - started))
            last_error = None
            return True

        # Если наш процесс умер — ждать бессмысленно, показываем причину
        if owns_server and server_process is not None:
            code = server_process.poll()
            if code is not None:
                last_error = ("llama-server завершился с кодом %s во время загрузки.\n\n"
                              "Последние строки logs\\llama-server.log:\n%s" % (code, tail_log()))
                print("❌ " + last_error)
                return False

        if on_progress is not None and state != last_state:
            try:
                on_progress(state, msg, time.time() - started)
            except Exception:
                pass
            last_state = state

        time.sleep(0.7)

    last_error = ("Модель не ответила за %d секунд.\n\n"
                  "Последние строки logs\\llama-server.log:\n%s" % (timeout, tail_log()))
    print("❌ " + last_error)
    return False


def stop_server():
    """Закрывает llama-server, но ТОЛЬКО если его запустили мы сами."""
    global server_process, owns_server
    if server_process is None or not owns_server:
        server_process = None
        return
    print("🛑 Остановка llama-server...")
    pid = server_process.pid
    try:
        if server_process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=15, **_NO_WINDOW)
    except Exception:
        try:
            server_process.kill()
        except Exception:
            pass
    try:
        server_process.wait(timeout=5)
    except Exception:
        pass
    server_process = None
    owns_server = False


# Совместимость со старым кодом (main.py)
def is_server_ready_alias():
    return is_server_ready()
