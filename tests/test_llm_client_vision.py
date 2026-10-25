# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LLM_CLIENT_VISION.PY — картинки в запросе к модели
# =========================================================
#   python tests\test_llm_client_vision.py
#
# Проверяем БЕЗ сети (подменяем HTTP):
#   1) data URL: голый base64 получает префикс, готовый data URL не портится;
#   2) content с картинкой — список кусков, ТЕКСТ первым;
#   3) картинка прикрепляется к ПОСЛЕДНЕЙ реплике пользователя;
#   4) исходный список сообщений не меняется (история остаётся текстовой);
#   5) без картинок тело запроса прежнее (content — строка);
#   6) пустые/None-картинки ничего не ломают.
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

import llm_client                                          # noqa: E402
from llm_client import (LLMClient, attach_images,          # noqa: E402
                        content_with_images, image_data_url)

FAILED = []
B64 = "AAAABBBBCCCC"


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
        return self._payload


class FakeHTTP:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self.response

    def get(self, url, timeout=None):
        return self.response


def make_client():
    client = LLMClient()
    http = FakeHTTP(FakeResponse(200, {"choices": [
        {"message": {"role": "assistant", "content": "A street."}}]}))
    client._http = http
    return client, http


def test_data_url():
    print("\n[1] data URL")
    url = image_data_url(B64)
    check("голый base64 → data:image/jpeg;base64,…",
          url == "data:image/jpeg;base64," + B64, url)
    ready = "data:image/png;base64,XYZ"
    check("готовый data URL не меняется", image_data_url(ready) == ready)
    check("пустая строка → None", image_data_url("") is None)
    check("None → None", image_data_url(None) is None)
    check("пробелы обрезаются",
          image_data_url("  " + B64 + "  ") == "data:image/jpeg;base64," + B64)


def test_content():
    print("\n[2] content: текст первым, картинка вторым")
    parts = content_with_images("What do you see?", [B64])
    check("кусков два", len(parts) == 2, parts)
    check("первый кусок — text", parts[0] == {"type": "text",
                                              "text": "What do you see?"}, parts[0])
    check("второй — image_url", parts[1]["type"] == "image_url", parts[1])
    check("url в data-формате",
          parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
    check("пустой текст допустим", content_with_images(None, [B64])[0]["text"] == "")
    two = content_with_images("x", [B64, B64])
    check("две картинки — три куска", len(two) == 3, len(two))


def test_attach_last_user():
    print("\n[3] картинка уходит к последней реплике пользователя")
    messages = [{"role": "system", "content": "You are a teacher."},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "Hi!"},
                {"role": "user", "content": "describe"}]
    out = attach_images(messages, [B64])
    check("системная реплика осталась строкой",
          out[0]["content"] == "You are a teacher.", out[0]["content"])
    check("первая реплика ученика не тронута",
          out[1]["content"] == "hello", out[1]["content"])
    check("последняя реплика стала списком",
          isinstance(out[3]["content"], list), type(out[3]["content"]))
    check("текст последней реплики сохранён",
          out[3]["content"][0]["text"] == "describe")
    check("исходный список НЕ изменён",
          isinstance(messages[3]["content"], str), type(messages[3]["content"]))
    check("исходный список не вырос", len(messages) == 4, len(messages))


def test_no_images():
    print("\n[4] без картинок всё по-старому")
    messages = [{"role": "user", "content": "hi"}]
    check("пустой список → тот же объект",
          attach_images(messages, []) is messages)
    check("None → тот же объект", attach_images(messages, None) is messages)
    check("пустые строки → тот же объект",
          attach_images(messages, ["", None]) is messages)
    proto = llm_client.__dict__.get("IMAGE_MIME")
    check("модуль отдаёт формат картинки", proto == "image/jpeg", proto)


def test_attach_no_user():
    print("\n[5] нет реплики пользователя — ничего не приклеиваем")
    messages = [{"role": "system", "content": "s"}]
    check("список вернулся как есть", attach_images(messages, [B64]) is messages)


def test_complete_payload():
    print("\n[6] complete(): тело запроса")
    client, http = make_client()
    ok, text = client.complete("What do you see?", images=[B64], max_tokens=80)
    check("ответ разобран", ok and text == "A street.", text)
    body = http.calls[0]["json"]
    content = body["messages"][0]["content"]
    check("content — список кусков", isinstance(content, list), type(content))
    check("кусков два", len(content) == 2, len(content))
    check("картинка на месте", content[1]["type"] == "image_url")
    check("текст запроса на месте", content[0]["text"] == "What do you see?")

    client2, http2 = make_client()
    client2.complete("hello")
    check("без картинок content — строка",
          http2.calls[0]["json"]["messages"][0]["content"] == "hello",
          http2.calls[0]["json"]["messages"][0]["content"])


def main():
    print("=" * 60)
    print("КАРТИНКИ В ЗАПРОСЕ К МОДЕЛИ (llm_client)")
    print("=" * 60)
    test_data_url()
    test_content()
    test_attach_last_user()
    test_no_images()
    test_attach_no_user()
    test_complete_payload()
    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛОВ: %d" % len(FAILED))
        for name in FAILED:
            print("  - " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
