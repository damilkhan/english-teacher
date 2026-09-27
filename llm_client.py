# =========================================================
# LLM_CLIENT.PY — Общение с локальным сервером llama.cpp
# =========================================================

import requests
import config

class LLMClient:
    """Клиент для общения с моделью Gemma 4 через llama.cpp сервер"""
    
    def __init__(self):
        self.url = config.LLM_SERVER_URL
        self.max_tokens = config.LLM_MAX_TOKENS
        self.temperature = config.LLM_TEMPERATURE
        self.stop_words = config.LLM_STOP_WORDS
    
    def is_health(self):
        """Проверяет, работает ли сервер"""
        try:
            requests.get("http://127.0.0.1:8080/health", timeout=2)
            return True
        except:
            return False
    
    def generate_response(self, prompt):
        """Отправляет промпт модели и возвращает ответ"""
        try:
            response = requests.post(self.url, json={
                "prompt": prompt,
                "n_predict": self.max_tokens,
                "temperature": self.temperature,
                "stop": self.stop_words
            }, timeout=30)
            
            if response.status_code == 200:
                return response.json().get("content", "").strip()
            else:
                print(f"❌ Ошибка сервера: {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            print("❌ Таймаут: сервер не отвечает")
            return None
        except Exception as e:
            print(f"❌ Ошибка при запросе: {e}")
            return None