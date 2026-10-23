# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_CONTEXT_LIMIT.PY — что делать, если запрос не влез в память модели
# =========================================================
#   python tests\test_context_limit.py   (окно и сеть НЕ нужны)
#
# Сервер llama.cpp НЕ обрезает длинный запрос сам — он отвечает ошибкой:
#   HTTP 400 {"error":{"type":"exceed_context_size_error",
#                     "message":"request (5215 tokens) exceeds ... (4096 tokens)"}}
# Раньше это превращалось в «Error: 400», и ученик слышал бессмысленную
# заглушку «Sorry, I can't respond.»
#
# Проверяем:
#   1) память модели поднята до 8192 (config, реестр моделей, server_manager);
#   2) клиент РАСПОЗНАЁТ переполнение и говорит числами, а не «Error: 400»;
#   3) обычные ошибки (500, сеть) переполнением НЕ считаются;
#   4) ChatController при переполнении повторяет запрос с короткой историей
#      и без RAG — и отвечает нормально;
#   5) если и повтор не помог — понятная фраза вместо заглушки;
#   6) обычный путь (места хватает) не изменился: один запрос, промпт тот же.
# =========================================================

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                                                   # noqa: E402
import llm_client                                                # noqa: E402
import prompt_builder                                            # noqa: E402
from controllers.chat_controller import ChatController           # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


# ---------- ответы сервера ----------
class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("нет JSON")
        return self._payload


def overflow_payload(prompt=5215, ctx=4096):
    return {"error": {"code": 400, "type": "exceed_context_size_error",
                      "message": "request (%d tokens) exceeds the available "
                                 "context size (%d tokens), try increasing it"
                                 % (prompt, ctx),
                      "n_prompt_tokens": prompt, "n_ctx": ctx}}


def ok_payload(text="Hello!"):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


class FakeHTTP:
    """Отдаёт ответы ПО ОЧЕРЕДИ и запоминает все запросы."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        return self.responses.pop(0) if self.responses else FakeResponse(200, ok_payload())

    def get(self, url, timeout=None):
        return FakeResponse(200, {})


# =========================================================
# 1. Размер памяти модели
# =========================================================
def test_context_size():
    print("\n[1] Память модели поднята до 8192")
    check("config.SERVER_CONTEXT == 8192", config.SERVER_CONTEXT == 8192,
          config.SERVER_CONTEXT)
    model = config.get_model(config.DEFAULT_MODEL_ID)
    check("у модели по умолчанию ctx == 8192", model.get("ctx") == 8192,
          model.get("ctx"))
    check("ctx модели не больше обученного (131072)",
          int(model.get("ctx")) <= 131072, model.get("ctx"))
    import server_manager
    check("server_manager берёт контекст из config",
          "SERVER_CONTEXT" in open(server_manager.__file__, encoding="utf-8").read())


# =========================================================
# 2-3. Клиент: распознать переполнение
# =========================================================
def test_client_detects():
    print("\n[2] Клиент распознаёт переполнение")
    client = llm_client.LLMClient()
    client._http = FakeHTTP([FakeResponse(400, overflow_payload())])
    ok, msg = client.complete([{"role": "user", "content": "hi"}])
    check("ok=False", ok is False, ok)
    check("помечено как переполнение", llm_client.is_context_error(msg), msg)
    check("сказано про токены и память модели",
          "5215" in msg and "4096" in msg, msg)
    check("безликого «Error: 400» больше нет", "Error: 400" not in msg, msg)

    print("\n[3] Прочие ошибки переполнением НЕ считаются")
    for status, label in ((500, "500"), (503, "503")):
        c = llm_client.LLMClient()
        c._http = FakeHTTP([FakeResponse(status, {"error": "boom"})])
        ok, msg = c.complete([{"role": "user", "content": "hi"}])
        check("%s → обычная ошибка" % label,
              ok is False and not llm_client.is_context_error(msg)
              and label in msg, msg)
    c = llm_client.LLMClient()
    c._http = FakeHTTP([FakeResponse(400, {"error": {"code": 400,
                                                     "message": "bad request"}})])
    ok, msg = c.complete([{"role": "user", "content": "hi"}])
    check("400 без упоминания контекста — не переполнение",
          ok is False and not llm_client.is_context_error(msg), msg)
    c = llm_client.LLMClient()
    c._http = FakeHTTP([FakeResponse(400, None)])       # тело не JSON
    ok, msg = c.complete([{"role": "user", "content": "hi"}])
    check("битое тело 400 не роняет клиент",
          ok is False and not llm_client.is_context_error(msg), msg)


# =========================================================
# 4-6. Контроллер: повтор с короткой историей
# =========================================================
class FakeLLM:
    """Модель-заглушка: отдаёт ответы по очереди, помнит запросы."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        return self.results.pop(0) if self.results else (True, "Fine.")


class temp_profile:
    def __enter__(self):
        import tempfile
        import profile_store
        self.store = profile_store
        self.dir = tempfile.mkdtemp(prefix="et_ctx_")
        self.real = profile_store.PROFILE_PATH
        profile_store.PROFILE_PATH = os.path.join(self.dir, "student_profile.json")
        profile_store.set_active_user(None)
        profile_store.ensure_profile()
        return profile_store.PROFILE_PATH

    def __exit__(self, *exc):
        self.store.PROFILE_PATH = self.real


def make_controller(llm, with_rag=True):
    real_rag = config.RAG_ENABLED
    config.RAG_ENABLED = with_rag
    try:
        ctrl = ChatController(llm=llm, dispatch=lambda fn: fn())
    finally:
        config.RAG_ENABLED = real_rag
    ctrl.mode = "lesson"
    ctrl.history = ["Student: Hello, my name is Damil.",
                    "Assistant: Hi Damil! Nice to meet you.",
                    "Student: I want to tell you about my school.",
                    "Assistant: Great! Tell me more."]
    return ctrl


def test_retry():
    print("\n[4] Переполнение → повтор с короткой историей")
    with temp_profile():
        llm = FakeLLM([(False, llm_client.CONTEXT_PREFIX + " запрос (9000 токенов) "
                                 "больше памяти модели (8192)."),
                       (True, "Hello! Let's start.")])
        ctrl = make_controller(llm)
        ok, reply = ctrl._request("Hello teacher!")
        check("ответ получен", ok is True and reply.startswith("Hello"), (ok, reply))
        check("было ДВА запроса (первый + повтор)", len(llm.calls) == 2, len(llm.calls))
        first, second = llm.calls[0], llm.calls[1]
        check("в первом истории 4 строки", len(first) == 1 + 4 + 1, len(first))
        check("в повторе истории не больше CONTEXT_RETRY_LINES",
              len(second) == 1 + int(config.CONTEXT_RETRY_LINES) + 1, len(second))
        check("реплика ученика в повторе осталась",
              second[-1]["content"] == "Hello teacher!", second[-1])
        check("системный промпт в повторе короче (RAG убран)",
              len(second[0]["content"]) <= len(first[0]["content"]),
              (len(first[0]["content"]), len(second[0]["content"])))

    print("\n[4b] Выключатель CONTEXT_RETRY_RAG=False оставляет RAG")
    real = config.CONTEXT_RETRY_RAG
    try:
        config.CONTEXT_RETRY_RAG = False
        with temp_profile():
            llm = FakeLLM([(False, llm_client.CONTEXT_PREFIX + " переполнение"),
                           (True, "Ok.")])
            ctrl = make_controller(llm)
            ctrl._request("Hi!")
            check("промпт повтора не короче первого",
                  len(llm.calls[1][0]["content"]) >= len(llm.calls[0][0]["content"]) * 0.9,
                  (len(llm.calls[0][0]["content"]), len(llm.calls[1][0]["content"])))
    finally:
        config.CONTEXT_RETRY_RAG = real


def test_retry_failed():
    print("\n[5] Не помогло → понятная фраза, а не заглушка")
    with temp_profile():
        llm = FakeLLM([(False, llm_client.CONTEXT_PREFIX + " переполнение"),
                       (False, llm_client.CONTEXT_PREFIX + " переполнение")])
        ctrl = make_controller(llm)
        ok, message = ctrl._request("Very long text.")
        check("ответ не получен", ok is False, ok)
        check("причина по-русски и без «Error:»",
              "память модели" in message and "Error:" not in message, message)
        check("сказано, что делать", "короткую фразу" in message, message)

    with temp_profile():
        llm = FakeLLM([(False, "Connection error: нет сети")])
        ctrl = make_controller(llm)
        ok, message = ctrl._request("Hi!")
        check("ошибка сети отдаётся как есть",
              ok is False and message == "Connection error: нет сети", message)
        check("повтора при ошибке сети нет", len(llm.calls) == 1, len(llm.calls))


def test_normal_path():
    print("\n[6] Обычный путь не изменился")
    with temp_profile():
        llm = FakeLLM([(True, "Hello!")])
        ctrl = make_controller(llm, with_rag=False)
        ok, reply = ctrl._request("Hi there!")
        check("один запрос", len(llm.calls) == 1, len(llm.calls))
        check("ответ показан", ok is True and reply == "Hello!", reply)
        msgs = llm.calls[0]
        check("структура: система + история + реплика",
              msgs[0]["role"] == "system" and msgs[-1]["content"] == "Hi there!",
              [m["role"] for m in msgs])
        base = prompt_builder.build_system_prompt("lesson", {}, "en")
        check("базовый промпт не тронут (правило §10)",
              base.startswith("You are " + config.TEACHER_NAME)
              and "CONTEXT" not in base, base[:60])


def main():
    print("=" * 60)
    print("Проверка памяти модели и повтора при переполнении")
    print("=" * 60)
    test_context_size()
    test_client_detects()
    test_retry()
    test_retry_failed()
    test_normal_path()

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО: %d → %s" % (len(FAILED), FAILED))
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
