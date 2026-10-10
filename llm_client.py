# -*- coding: utf-8 -*-
# =========================================================
# LLM_CLIENT.PY — общение с локальным сервером llama.cpp
# =========================================================
# Здесь живёт весь сетевой слой: ни GUI, ни контроллеры не знают
# про requests, порт и теги Gemma.
#
# Особенности:
#   * запросы идут через Session с trust_env=False — иначе при активном
#     VPN/прокси (Amnezia и т.п.) localhost может «уйти наружу»;
#   * complete() различает ошибку связи и ошибку сервера, чтобы UI мог
#     показать внятное сообщение.
# =========================================================

import threading

import requests

import config


class LLMClient:
    """Клиент для модели Gemma через llama.cpp сервер."""

    def __init__(self, url=None, health_url=None, max_tokens=None, temperature=None, stop=None):
        self.url = url or config.LLM_SERVER_URL
        self.health_url = health_url or config.LLM_HEALTH_URL
        self.max_tokens = max_tokens or config.LLM_MAX_TOKENS
        self.temperature = config.LLM_TEMPERATURE if temperature is None else temperature
        self.stop_words = list(stop) if stop else list(config.LLM_STOP_WORDS)

        self._http = requests.Session()
        self._http.trust_env = False
        # requests.Session НЕ потокобезопасен. Роли (Учитель/Аналитик) и
        # фоновый Планировщик могут звать complete() из разных потоков —
        # сериализуем обращения, иначе ответы могут перемешиваться.
        self._lock = threading.Lock()

    # ---------- проверка связи ----------
    def is_health(self, timeout=2):
        """Есть ли на том конце живой сервер (только 200/ready)."""
        try:
            resp = self._http.get(self.health_url, timeout=timeout)
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    # ---------- основной вызов ----------
    def complete(self, prompt, max_tokens=None, temperature=None, stop=None, timeout=60):
        """Отправляет промпт и возвращает (ok, текст_или_ошибка).

        ok=True  → второй элемент: ответ модели;
        ok=False → второй элемент: человекочитаемая причина.
        """
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "stop": stop if stop is not None else self.stop_words,
        }
        try:
            with self._lock:
                resp = self._http.post(self.url, json=payload, timeout=timeout)
        except requests.exceptions.Timeout:
            return False, "Таймаут: сервер не отвечает"
        except Exception as exc:
            return False, f"Connection error: {exc}"

        if resp.status_code != 200:
            print(f"❌ Сервер вернул ошибку: {resp.status_code}")
            return False, f"Error: {resp.status_code}"

        try:
            content = resp.json().get("content", "")
        except Exception as exc:
            return False, f"Error: некорректный ответ сервера ({exc})"
        return True, (content or "").strip()
