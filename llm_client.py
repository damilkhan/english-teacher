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


# Вид ошибки «не влезло в память модели». Сервер llama.cpp НЕ обрезает
# запрос сам: при переполнении он отвечает 400 с телом
#   {"error":{"code":400,"type":"exceed_context_size_error",
#            "message":"request (5215 tokens) exceeds the available context
#                       size (4096 tokens)","n_prompt_tokens":5215,"n_ctx":4096}}
# Раньше это превращалось в безликое «Error: 400», и ученик слышал
# заглушку «Sorry, I can't respond.» без объяснения. Теперь такой ответ
# помечается CONTEXT_PREFIX: вызывающий код (ChatController) повторяет
# запрос с укороченной историей (см. config.CONTEXT_RETRY_LINES).
CONTEXT_PREFIX = "context:"


def is_context_error(message) -> bool:
    """Причина ошибки — переполнение памяти модели (а не сбой сети/сервера)?"""
    return str(message or "").startswith(CONTEXT_PREFIX)


# ---------- картинки (vision) ----------
# llama.cpp принимает картинку в OpenAI-формате: content сообщения — СПИСОК
# кусков, картинка идёт как
#   {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
# Файл читает и кодирует вызывающий код (picture_task.py): здесь только
# формат запроса, чтобы llm_client оставался тонким сетевым слоем.

IMAGE_MIME = "image/jpeg"


def image_data_url(image):
    """'data:image/jpeg;base64,...' или голый base64 → data URL. Пусто → None."""
    text = str(image or "").strip()
    if not text:
        return None
    if text.startswith("data:"):
        return text
    return "data:%s;base64,%s" % (IMAGE_MIME, text)


def content_with_images(content, images):
    """Текст + картинки → content-список OpenAI (текст всегда ПЕРВЫМ куском)."""
    parts = [{"type": "text", "text": str(content or "")}]
    for image in images or []:
        url = image_data_url(image)
        if url:
            parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


def attach_images(messages, images):
    """Копия messages, где к ПОСЛЕДНЕЙ реплике пользователя добавлены картинки.

    Исходный список НЕ меняется: история диалога в контроллере остаётся
    текстовой, иначе base64 копился бы в памяти на каждом ходу.
    """
    urls = [u for u in (image_data_url(i) for i in (images or [])) if u]
    if not urls:
        return messages
    result = list(messages)
    index = None
    for i in range(len(result) - 1, -1, -1):
        if str(result[i].get("role") or "") == "user":
            index = i
            break
    if index is None:                  # картинок без реплики не бывает
        return messages
    msg = dict(result[index])
    msg["content"] = content_with_images(msg.get("content"), urls)
    result[index] = msg
    return result


def _context_overflow(response):
    """Разобрать ответ 4xx: это переполнение контекста? None — если нет.

    Возвращает короткий словарь {"prompt": …, "ctx": …} для сообщения.
    Смотрим и JSON (тип/код ошибки), и текст тела — формат у llama.cpp
    может отличаться от версии к версии.
    """
    try:
        data = response.json()
    except Exception:                              # noqa: BLE001
        data = None
    payload, message = {}, ""
    if isinstance(data, dict):
        payload = data
        err = data.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or "")
            kind = str(err.get("type") or "")
            if kind == "exceed_context_size_error":
                return {"prompt": err.get("n_prompt_tokens"),
                        "ctx": err.get("n_ctx")}
        elif err:
            message = str(err)
    low = message.lower()
    if "context" in low and ("exceed" in low or "too long" in low):
        return {"prompt": payload.get("n_prompt_tokens"),
                "ctx": payload.get("n_ctx")}
    return None


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
    def complete(self, messages, max_tokens=None, temperature=None, stop=None,
                 timeout=60, images=None):
        """Отправляет сообщения и возвращает (ok, текст_или_ошибка).

        messages: список {"role": ..., "content": ...} ИЛИ строка (тогда она
                  считается ОДНОЙ репликой пользователя — мелкое удобство).

        ok=True  → второй элемент: ответ модели;
        ok=False → второй элемент: человекочитаемая причина.
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        if images:
            messages = attach_images(messages, images)
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
            overflow = _context_overflow(resp)
            if overflow is not None:
                prompt, ctx = overflow.get("prompt"), overflow.get("ctx")
                if prompt and ctx:
                    return False, ("%s запрос (%s токенов) больше памяти модели "
                                   "(%s)." % (CONTEXT_PREFIX, prompt, ctx))
                return False, CONTEXT_PREFIX + " запрос не влез в память модели."
            return False, f"Error: {resp.status_code}"

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            return False, f"Error: некорректный ответ сервера ({exc})"
        return True, (content or "").strip()
