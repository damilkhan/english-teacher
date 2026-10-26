# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_LESSON.PY — логика занятия по карте (lesson.py)
# =========================================================
#   python tests\test_lesson.py   (без окна, без модели)
#
# Проверяем:
#   1) типы уроков и каналы ответа (speaking/chat/listening/mixed);
#   2) подсказки к полю ввода и кнопке записи;
#   3) сессию занятия: старт, счёт реплик, автозавершение по лимиту;
#   4) ранний выход (abort) — занятие НЕ засчитывается;
#   5) подписи (label/progress_text) и снимок состояния;
#   6) безопасность: пустые/чужие значения не ломают логику.
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

import lesson as L                                          # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


def main():
    print("=" * 60)
    print("Проверка логики занятия (lesson.py)")
    print("=" * 60)

    # ---------- 1. Типы и каналы ----------
    print("\n[1] Типы уроков и каналы ответа")
    check("speaking → только голос", L.allowed_inputs("speaking") == {"voice"},
          L.allowed_inputs("speaking"))
    check("listening → только голос", L.allowed_inputs("listening") == {"voice"},
          L.allowed_inputs("listening"))
    check("chat → только текст", L.allowed_inputs("chat") == {"text"},
          L.allowed_inputs("chat"))
    check("mixed → и голос, и текст", L.allowed_inputs("mixed") == {"voice", "text"},
          L.allowed_inputs("mixed"))
    check("неизвестный тип → как speaking", L.allowed_inputs("чухня") == {"voice"},
          L.allowed_inputs("чухня"))
    check("пустой тип → speaking", L.allowed_inputs(None) == {"voice"})

    check("микрофон нужен для speaking", L.needs_microphone("speaking") is True)
    check("микрофон НЕ нужен для chat", L.needs_microphone("chat") is False)
    check("текст разрешён только в chat/mixed",
          L.needs_text("chat") and not L.needs_text("speaking")
          and not L.needs_text("listening"))

    check("подпись типа: speaking", L.type_label("speaking") == "говорение")
    check("подпись типа: chat", L.type_label("chat") == "текст")
    check("подпись типа: listening", L.type_label("listening") == "аудирование")
    check("подпись типа: неизвестный → говорение", L.type_label(None) == "говорение")

    # ---------- 2. Подсказки ----------
    print("\n[2] Подсказки интерфейсу")
    check("замок для speaking", "микрофон" in L.locked_hint("speaking").lower(),
          L.locked_hint("speaking"))
    check("замок для listening про слушание",
          "слуша" in L.locked_hint("listening").lower(), L.locked_hint("listening"))
    check("подсказка голосом для speaking", L.voice_hint("speaking").startswith("🎤"),
          L.voice_hint("speaking"))
    check("подсказка голосом для listening содержит наушники",
          L.voice_hint("listening").startswith("🎧"), L.voice_hint("listening"))

    # ---------- 3. Сессия: старт и счёт ----------
    print("\n[3] Сессия: старт и счёт реплик")
    s = L.LessonSession("1.1", point_id="point_1", lesson_type="speaking",
                        title="Hello / Hi", topic="greetings", block_number=1,
                        block_title="Greetings & Hello")
    check("id урока", s.lesson_id == "1.1")
    check("тип — speaking", s.lesson_type == "speaking")
    check("занятие активно на старте", s.is_active is True)
    check("старт: 0 из лимита", s.progress == (0, L.DEFAULT_REPLY_TARGET), s.progress)
    check("текст заблокирован (speaking)", s.allows_text() is False and s.allows_voice())
    check("метка урока", s.label() == "Урок 1.1 · Hello / Hi", s.label())
    # §36 (26.10.2026): у обычного урока счётчик — ЗАДАНИЯ, а не реплики.
    # По репликам теперь считаются только экзамен и аудирование.
    check("прогресс урока — задания: «Задание 1/3»",
          s.progress_text() == "Задание 1/3", s.progress_text())
    check("урок-аудирование — по репликам: «0/12»",
          L.LessonSession("x", lesson_type="listening").progress_text()
          == "0/12"
          and L.LessonSession("x", lesson_type="lecture").progress_text()
          == "Задание 1/3")

    st = s.register_reply()
    check("после реплики — 1", st["replies"] == 1, st)
    check("занятие всё ещё активно", s.is_active is True)
    check("автозавершение ещё не сработало", s.should_finish is False)

    # ---------- 4. Автозавершение по лимиту ----------
    print("\n[4] Автозавершение по лимиту")
    t = L.LessonSession("2.1", lesson_type="speaking", reply_target=3)
    t.register_reply(); t.register_reply()
    check("2 из 3 — ещё не завершено", t.is_active and not t.finished, t.state())
    t.register_reply()
    check("3 из 3 — завершено", t.finished is True and t.is_active is False, t.state())
    check("should_finish True", t.should_finish is True)
    extra = t.register_reply()
    check("после завершения реплики не считаются", extra["replies"] == 3, extra)
    check("ожидаемое завершение (finish) снимает abort", True)
    t2 = L.LessonSession("2.2", reply_target=2)
    t2.abort(); t2.finish()
    check("finish после abort → завершено и не прервано",
          t2.finished is True and t2.aborted is False, t2.state())

    # ---------- 5. Ранний выход ----------
    print("\n[5] Ранний выход (abort) — урок НЕ засчитан")
    a = L.LessonSession("3.1", lesson_type="speaking", reply_target=10)
    a.register_reply()
    a.abort()
    check("прерван", a.aborted is True)
    check("не завершён", a.finished is False, a.state())
    check("занятие неактивно", a.is_active is False)
    check("реплики сохранились (прогресс уже записан)",
          a.state()["replies"] == 1, a.state())
    after = a.register_reply()
    check("после выхода реплики не считаются", after["replies"] == 1, after)

    # ---------- 6. chat-урок ----------
    print("\n[6] chat-урок: текст разрешён, микрофон не нужен")
    c = L.LessonSession("1.3", lesson_type="chat", title="How are you?")
    check("текст разрешён", c.allows_text() is True)
    check("голос запрещён", c.allows_voice() is False)
    check("микрофон не нужен", c.needs_microphone() is False)
    check("каналы ровно {text}", c.allowed_inputs() == {"text"}, c.allowed_inputs())

    # ---------- 7. Безопасность ----------
    print("\n[7] Безопасность входных данных")
    z = L.LessonSession("")
    check("пустой id не роняет", z.lesson_id == "" and z.title == "")
    check("лимит минимум 1", L.LessonSession("x", reply_target=0).reply_target == 1)
    check("отрицательный лимит → 1", L.LessonSession("x", reply_target=-5).reply_target == 1)
    check("строковый лимит приводится к числу",
          L.LessonSession("x", reply_target="7").reply_target == 7)
    check("лимит из config по умолчанию",
          L.LessonSession("x").reply_target == L.DEFAULT_REPLY_TARGET)
    check("состояние — словарь с ключами",
          set(["lesson_id", "type", "replies", "target", "finished", "aborted"]).issubset(z.state().keys()))

    # ---------- 8. LessonController ----------
    print("\n[8] LessonController: колбэки и порядок событий")
    from controllers.lesson_controller import LessonController
    events = []
    ctrl = LessonController(
        dispatch=lambda fn: fn(),               # без Tk: зовём сразу
        on_started=lambda s: events.append(("started", s.lesson_id)),
        on_reply=lambda st: events.append(("reply", st["replies"])),
        on_finished=lambda s: events.append(("finished", s.lesson_id)),
        on_aborted=lambda s: events.append(("aborted", s.lesson_id)),
    )
    check("сначала занятия нет", ctrl.is_active is False and ctrl.lesson_id is None)
    check("register_reply без занятия → None", ctrl.register_reply() is None)

    sess = ctrl.start("1.1", point_id="point_1", lesson_type="speaking",
                      title="Hello / Hi", reply_target=2)
    check("старт вернул сессию", sess is not None and sess.lesson_id == "1.1")
    check("занятие активно", ctrl.is_active is True)
    check("событие started", events[0] == ("started", "1.1"), events)
    check("повторный start игнорируется (занятие уже идёт)",
          ctrl.start("2.1") is None)

    ctrl.register_reply()
    check("событие reply 1", ("reply", 1) in events, events)
    check("после 1 реплики занятие ещё активно", ctrl.is_active is True)
    ctrl.register_reply()
    check("на лимите пришло finished", ("finished", "1.1") in events, events)
    check("после завершения занятие неактивно", ctrl.is_active is False)

    # прерывание
    ev2 = []
    ctrl2 = LessonController(dispatch=lambda fn: fn(),
                             on_aborted=lambda s: ev2.append(s.lesson_id))
    ctrl2.start("3.1", reply_target=5)
    ctrl2.register_reply()
    ctrl2.abort()
    check("abort сообщил о прерывании", ev2 == ["3.1"], ev2)
    check("после abort занятие неактивно", ctrl2.is_active is False)
    check("abort не засчитал урок (finished False)", ctrl2.current().finished is False)
    ctrl2.reset()
    check("reset забыл занятие", ctrl2.current() is None)

    # ошибка в колбэке не ломает контроллер
    bad = LessonController(dispatch=lambda fn: fn(),
                           on_started=lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    check("ошибка колбэка не пробрасывается",
          bad.start("9.9", reply_target=2) is not None)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} → {FAILED}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
