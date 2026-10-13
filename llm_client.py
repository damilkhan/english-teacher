# -*- coding: utf-8 -*-
# =========================================================
# LLM_CLIENT.PY — общение с локальным сервером llama.cpp
# =========================================================
# Здесь живёт весь сетевой слой: ни GUI, ни контроллеры не знают
# про requests, порт и теги Gemma.
#
# Общение идёт через OpenAI-совместимый эндпоинт /v1/chat/completions:
#   * шлём СПИСОК сообщений (messages) — как в OpenAI API:
#         [{"role": "system", "content": ...},
#          {"role": "user", "content": ...}, ...]
#   * разметку под КОНКРЕТНУЮ модель (<start_of_turn>… и т.п.) применяет
#     САМ сервер llama.cpp (запущен с --jinja), поэтому код не зависит от
#     семейства модели и не собирает «сырой» промпт вручную.
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
    """Клиент локальной модели (OpenAI-совместимый эндпоинт llama.cpp)."""

    def __init__(self, url=None, health_url=None, max_tokens=None, temperature=None, stop=None):
        self.url = url or config.LLM_CHAT_URL
        self.health_url = health_url or config.LLM_HEALTH_URL
        self.max_tokens = max_tokens or config.LLM_MAX_TOKENS
        self.temperature = config.LLM_TEMPERATURE if temperature is None else temperature
        # По умолчанию стоп-слов НЕТ: конец ответа модель и так обозначает своим
        # служебным токеном, а шаблон сервер применяет сам. Прежние "Student:"/
        # "\n\n" были артефактом «сырого» /completion и тут только обрезали ответ.
        self.stop_words = list(stop) if stop else []

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
    def complete(self, messages, max_tokens=None, temperature=None, stop=None, timeout=60):
        """Отправляет сообщения и возвращает (ok, текст_или_ошибка).

        messages: список {"role": ..., "content": ...} ИЛИ строка (тогда она
                  считается ОДНОЙ репликой пользователя — мелкое удобство).

        ok=True  → второй элемент: ответ модели;
        ok=False → второй элемент: человекочитаемая причина.
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        payload = {
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
        }
        stop_words = self.stop_words if stop is None else list(stop)
        if stop_words:
            payload["stop"] = stop_words
        # Reasoning-модели (например Gemma-4) могут тратить токены на
        # внутренний «Thinking Process» — он не попадает в content, и ответ
        # приходит пустым. Флаг просит шаблон НЕ включать размышления.
        if getattr(config, "LLM_NO_THINKING", True):
            payload["chat_template_kwargs"] = {"enable_thinking": False}
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
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            return False, f"Error: некорректный ответ сервера ({exc})"
        return True, (content or "").strip()
