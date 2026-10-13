# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LLM_CLIENT.PY — клиент llama.cpp (llm_client.py)
# =========================================================
#   python tests\test_llm_client.py
#
# Проверяем БЕЗ сети (подменяем HTTP):
#   1) запрос уходит на OpenAI-совместимый /v1/chat/completions;
#   2) список сообщений передаётся как есть, строка → одно сообщение user;
#   3) max_tokens/temperature из аргументов; стоп-слова — только если заданы;
#   4) флаг «без размышлений» (chat_template_kwargs) ставится/снимается;
#   5) ответ разбирается из choices[0].message.content и обрезается;
#   6) ошибки: код != 200, битый JSON, таймаут, обрыв связи — внятный текст;
#   7) is_health по коду ответа.
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests                    # noqa: E402
import config                      # noqa: E402
from llm_client import LLMClient   # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("нет JSON")
        return self._payload


class FakeHTTP:
    """Подменяет requests.Session: запоминаем запросы, отдаём заданный ответ."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    def get(self, url, timeout=None):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def make_client(response):
    """Клиент с подменённым HTTP (сеть не трогаем)."""
    client = LLMClient()
    http = FakeHTTP(response)
    client._http = http
    return client, http


def ok_payload(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def test_endpoint_and_payload():
    print("\n[1] Эндпоинт и тело запроса")
    client, http = make_client(FakeResponse(200, ok_payload("Привет")))
    ok, text = client.complete([{"role": "user", "content": "hi"}],
                               max_tokens=123, temperature=0.3)
    check("успех и текст", ok is True and text == "Привет", (ok, text))
    call = http.calls[0]
    check("URL — OpenAI-совместимый чат", call["url"].endswith("/v1/chat/completions"), call["url"])
    check("сообщения переданы как есть",
          call["json"]["messages"] == [{"role": "user", "content": "hi"}], call["json"].get("messages"))
    check("max_tokens из аргумента", call["json"]["max_tokens"] == 123, call["json"].get("max_tokens"))
    check("temperature из аргумента", call["json"]["temperature"] == 0.3, call["json"].get("temperature"))
    check("без стоп-слов ключа stop нет", "stop" not in call["json"], call["json"].keys())


def test_string_input():
    print("\n[2] Строка → одно сообщение пользователя")
    client, http = make_client(FakeResponse(200, ok_payload("ok")))
    client.complete("просто строка")
    msgs = http.calls[0]["json"]["messages"]
    check("строка обёрнута в user", msgs == [{"role": "user", "content": "просто строка"}], msgs)


def test_stop_words():
    print("\n[3] Стоп-слова — только когда заданы")
    client, http = make_client(FakeResponse(200, ok_payload("ok")))
    client.complete([{"role": "user", "content": "hi"}], stop=["<end_of_turn>"])
    check("stop ушёл в запрос", http.calls[-1]["json"].get("stop") == ["<end_of_turn>"], http.calls[-1]["json"].get("stop"))

    client2, http2 = make_client(FakeResponse(200, ok_payload("ok")))
    client2.complete([{"role": "user", "content": "hi"}])
    check("по умолчанию стоп-слов нет", "stop" not in http2.calls[-1]["json"], http2.calls[-1]["json"].keys())


def test_thinking_flag():
    print("\n[4] Флаг «без размышлений» (chat_template_kwargs)")
    client, http = make_client(FakeResponse(200, ok_payload("ok")))
    client.complete([{"role": "user", "content": "hi"}])
    kwargs = http.calls[-1]["json"].get("chat_template_kwargs")
    check("флаг enable_thinking=false уходит в запрос",
          kwargs == {"enable_thinking": False}, kwargs)

    real = config.LLM_NO_THINKING
    try:
        config.LLM_NO_THINKING = False
        client2, http2 = make_client(FakeResponse(200, ok_payload("ok")))
        client2.complete([{"role": "user", "content": "hi"}])
        check("при выключенном флаге ключа нет",
              "chat_template_kwargs" not in http2.calls[-1]["json"], http2.calls[-1]["json"].keys())
    finally:
        config.LLM_NO_THINKING = real


def test_response_parsing():
    print("\n[5] Разбор ответа и обрезка пробелов")
    client, _ = make_client(FakeResponse(200, ok_payload("  Ответ модели  ")))
    ok, text = client.complete([{"role": "user", "content": "hi"}])
    check("пробелы обрезаны", ok and text == "Ответ модели", repr(text))

    client2, _ = make_client(FakeResponse(200, {"choices": [{"message": {"content": ""}}]}))
    ok2, text2 = client2.complete([{"role": "user", "content": "hi"}])
    check("пустой content → ok=True, пустая строка", ok2 and text2 == "", (ok2, text2))


def test_errors():
    print("\n[6] Ошибки — внятный текст, без исключений")
    client, _ = make_client(FakeResponse(500, {"error": "boom"}))
    ok, msg = client.complete([{"role": "user", "content": "hi"}])
    check("код != 200 → ошибка", ok is False and "500" in msg, msg)

    client2, _ = make_client(FakeResponse(200, None))       # .json() бросит
    ok2, msg2 = client2.complete([{"role": "user", "content": "hi"}])
    check("битый JSON → ошибка", ok2 is False and "некорректный" in msg2, msg2)

    client3, _ = make_client(requests.exceptions.Timeout("t"))
    ok3, msg3 = client3.complete([{"role": "user", "content": "hi"}])
    check("таймаут → ошибка", ok3 is False and "Таймаут" in msg3, msg3)

    client4, _ = make_client(requests.exceptions.ConnectionError("no"))
    ok4, msg4 = client4.complete([{"role": "user", "content": "hi"}])
    check("обрыв связи → ошибка", ok4 is False and "Connection error" in msg4, msg4)


def test_health():
    print("\n[7] is_health по коду ответа")
    client, _ = make_client(FakeResponse(200, {}))
    check("200 → True", client.is_health() is True)
    client2, _ = make_client(FakeResponse(503, {}))
    check("503 → False", client2.is_health() is False)
    client3, _ = make_client(requests.exceptions.ConnectionError("no"))
    check("нет связи → False", client3.is_health() is False)


def main():
    print("=" * 60)
    print("Проверка клиента llama.cpp (OpenAI-совместимый чат)")
    print("=" * 60)

    test_endpoint_and_payload()
    test_string_input()
    test_stop_words()
    test_thinking_flag()
    test_response_parsing()
    test_errors()
    test_health()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()