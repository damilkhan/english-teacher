# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_HESITATION_PROMPT.PY — запинка в речи не ошибка (без экрана)
# =========================================================
#   python tests\test_hesitation_prompt.py
#
# ЗАЧЕМ. Жалоба ученика 25.10.2026: он сказал «sometimes we meet in the city
# center or the park in the park» (запнулся), а преподаватель принял это за
# ошибку и стал объяснять, чего «не надо» повторять.
#
# ЗАМЕР на живой модели (фраза ученика, урок city/1.1, A2, с историей диалога):
#   * учитель БЕЗ правила исправлял запинку 5 раз из 10;
#   * учитель С правилом (этот блок) — 0 из 10;
#   * аналитик БЕЗ правила считал ошибку 4 раза из 4.
#
# Решения ученика: запинку НЕ склеивать, на всех уровнях НЕ замечать.
#
# Проверяем:
#   1) блока нет по умолчанию и при явном False — промпт прежний;
#   2) при True блок есть и стоит В КОНЦЕ (база не тронута, smoke_test цел);
#   3) блок говорит три вещи: не исправлять, не упоминать, отвечать на
#      последнюю версию;
#   4) ChatController реально передаёт флаг (проверяем по system-промпту,
#      который уходит модели, а не по тексту исходника).
# Модель, микрофон и Tk не нужны.
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

import config                                                    # noqa: E402
import prompt_builder                                            # noqa: E402
from controllers.chat_controller import ChatController            # noqa: E402

FAILED = []
MARK = "SPEECH HESITATIONS"


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class GrabLLM:
    """Запоминает system-промпт и возвращает простую реплику."""

    def __init__(self):
        self.system = ""
        self.user = ""

    def complete(self, prompt, max_tokens=None, temperature=None, stop=None,
                 timeout=None):
        if isinstance(prompt, list) and prompt:
            self.system = str((prompt[0] or {}).get("content") or "")
            self.user = str((prompt[-1] or {}).get("content") or "")
        return True, "Nice! What else do you like about the park?"


def base(**kwargs):
    return prompt_builder.build_system_prompt(
        "lesson", {}, "en", level="A2",
        student={"name": "Damil", "name_latin": "Damil", "gender": "male"},
        lesson={"title": "Shall we meet at six?", "type": "speaking",
                "topic": "meeting friends"},
        variety=True, american=True, **kwargs)


def main():
    # ---------- 1. по умолчанию блока нет ----------
    print("[1] По умолчанию промпт прежний")
    default = base()
    explicit_off = base(hesitation=False)
    check("умолчание = явное False (байт-в-байт)", default == explicit_off,
          len(default))
    check("без флага блока нет", MARK not in default)
    check("без флага нет и слова про запинки",
          "hesitation" not in default.lower())

    # ---------- 2. с флагом блок добавлен в конец ----------
    print("\n[2] С флагом — блок в конце")
    on = base(hesitation=True)
    check("блок есть", MARK in on)
    check("база — префикс (блок ТОЛЬКО в конце)", on.startswith(default),
          on[:80])
    check("добавка не пустая (это не подмена промпта)", len(on) > len(default),
          (len(on), len(default)))
    check("блок про запинки закончен (текст не обрезан)",
        on.rstrip().endswith(
            "the meaning of the LAST version of what they said."),
        on[-90:])

    # ---------- 3. что именно сказано в блоке ----------
    print("\n[3] Смысл блока")
    low = on.lower()
    check("запрет исправлять", "do not correct it" in low)
    check("запрет упоминать", "do not mention it" in low)
    check("сказано, что это НЕ ошибка", "not a mistake" in low)
    check("просьба опираться на последнюю версию", "last version" in low)
    check("есть пример запинки", "the park in the park" in low)
    added = on[len(default):].lower()      # только сам блок, не весь промпт
    check("блок по-английски (без кириллицы)",
          not any("а" <= ch <= "я" for ch in added), added[:80])

    # ---------- 4. контроллер реально включает блок ----------
    print("\n[4] ChatController передаёт флаг")
    real_rag = config.RAG_ENABLED
    config.RAG_ENABLED = False        # методические заметки тут не нужны
    try:
        llm = GrabLLM()
        ctrl = ChatController(llm=llm, dispatch=lambda fn: fn(), mode="lesson",
                              user_id=1)
        ok, _reply = ctrl._request(
            "sometimes we meet in the city center or the park in the park")
    finally:
        config.RAG_ENABLED = real_rag
    check("ответ получен", ok is True, ok)
    check("в промпте, ушедшем модели, есть блок про запинки", MARK in llm.system,
          llm.system[:120])
    check("реплика ученика ушла без правок (запинку НЕ склеиваем)",
          "the park in the park" in llm.user, llm.user)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
