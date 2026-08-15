import subprocess
import atexit
import time
import os
import requests

# Пути к серверу и модели
SERVER_PATH = r"D:\llama.cpp\llama-server.exe"
MODEL_PATH = r"D:\EnglishTeacher\models\gemma\Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"

# URL для проверки статуса
SERVER_URL = "http://127.0.0.1:8080"
HEALTH_URL = f"{SERVER_URL}/health"

server_process = None

def start_server():
    """Запускает сервер в фоне"""
    global server_process
    if not os.path.exists(SERVER_PATH):
        print(f"❌ Сервер не найден: {SERVER_PATH}")
        return False
    if not os.path.exists(MODEL_PATH):
        print(f"❌ Модель не найдена: {MODEL_PATH}")
        return False
    
    print("🚀 Запуск сервера llama.cpp...")
    server_process = subprocess.Popen([
        SERVER_PATH,
        "-m", MODEL_PATH,
        "-c", "4096",
        "--host", "127.0.0.1",
        "--port", "8080",
        "--jinja"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    atexit.register(stop_server)  # ← здесь вызов правильной функции
    time.sleep(5)
    return True

def stop_server():
    """Останавливает сервер"""
    global server_process
    if server_process:
        print("🛑 Остановка сервера...")
        server_process.terminate()
        server_process.wait()
        server_process = None

def is_server_ready():
    """Проверяет, отвечает ли сервер"""
    try:
        response = requests.get(HEALTH_URL, timeout=2)  # ← здесь переменная определена
        return response.status_code == 200
    except:
        return False

def wait_for_server(timeout=10):
    """Ждёт готовности сервера"""
    print("⏳ Ожидание сервера...")
    for i in range(timeout):
        if is_server_ready():
            print("✅ Сервер готов!")
            return True
        time.sleep(1)
        print(f"   ожидание... {i+1}/{timeout}")
    print("❌ Сервер не запустился")
    return False