# -*- coding: utf-8 -*-
# =========================================================
# TESTS/TEST_TEACHER_NAME.PY — имя преподавателя («Verbot») и название приложения
# =========================================================
#   python tests\test_teacher_name.py   (окно и сеть НЕ нужны)
#
# Зачем: приложение переименовано в «Verbot» (Verba & Bot, 23.10.2026), а имя
# САМОГО преподавателя ученик может задать своё — оно живёт в профиле, в поле
# teacher_name. Раньше «Джейн» было зашито в промпт, в подпись реплик чата, в
# заголовок окна и в приветствие.
#
# Проверяем:
#   1) config: название приложения и имя преподавателя по умолчанию;
#   2) user_manager.teacher_name: профиль / пусто / мусор / пробелы / длина;
#   3) имя сохраняется в профиле и переживает перечитывание с диска;
#   4) промпт: имя подставлено, ЖЕНСКИЙ РОД сохранён, блок ученика знает имя;
#   5) ChatController: имя в подписи реплики, в статусе и в промпте модели;
#   6) ui/app: заголовок окна, подпись шапки, форма профиля, приветствие.
# =========================================================

import inspect
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# консоль Windows по умолчанию cp1251 — без этого падаем на эмодзи
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config                                                    # noqa: E402
import profile_store                                             # noqa: E402
import prompt_builder                                            # noqa: E402
import user_manager                                              # noqa: E402
from controllers.chat_controller import ChatController           # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + name + ("" if ok else "  ← " + str(detail)))
    if not ok:
        FAILED.append(name)
    return ok


class FakeLLM:
    """Всегда отвечает одной строкой; запоминает, что ему передали."""

    def __init__(self, payload="Hello!"):
        self.payload = payload
        self.calls = []

    def complete(self, messages, max_tokens=None, temperature=None, stop=None,
                 timeout=None):
        self.calls.append(messages)
        return True, self.payload


class TempProfiles:
    """Временная папка профилей: реальные файлы учеников не трогаем."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="et_name_")
        self.real = (user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE)
        user_manager.PROFILES_DIR = self.dir
        user_manager.LAST_USER_FILE = os.path.join(self.dir, "last_user.txt")
        profile_store.set_active_user(None)
        return self.dir

    def __exit__(self, *exc):
        user_manager.PROFILES_DIR, user_manager.LAST_USER_FILE = self.real
        profile_store.set_active_user(None)
        return False


# =========================================================
# 1. Название приложения и имя по умолчанию
# =========================================================
def test_config():
    print("\n[1] config: название приложения и имя преподавателя")
    check("APP_NAME = Verbot", getattr(config, "APP_NAME", "") == "Verbot",
          getattr(config, "APP_NAME", None))
    check("TEACHER_NAME = Verbot", getattr(config, "TEACHER_NAME", "") == "Verbot",
          getattr(config, "TEACHER_NAME", None))


# =========================================================
# 2. user_manager.teacher_name — правила выбора имени
# =========================================================
def test_teacher_name_rules():
    print("\n[2] teacher_name: профиль → своё имя, иначе общее")
    default = config.TEACHER_NAME
    check("нет профиля → имя по умолчанию",
          user_manager.teacher_name(None) == default, user_manager.teacher_name(None))
    check("пустой профиль → имя по умолчанию",
          user_manager.teacher_name({}) == default, user_manager.teacher_name({}))
    check("пустая строка → имя по умолчанию",
          user_manager.teacher_name({"teacher_name": ""}) == default,
          user_manager.teacher_name({"teacher_name": ""}))
    check("пробелы → имя по умолчанию",
          user_manager.teacher_name({"teacher_name": "   "}) == default,
          user_manager.teacher_name({"teacher_name": "   "}))
    check("своё имя берётся из профиля",
          user_manager.teacher_name({"teacher_name": "Лина"}) == "Лина",
          user_manager.teacher_name({"teacher_name": "Лина"}))
    check("лишние пробелы вокруг имени снимаются",
          user_manager.teacher_name({"teacher_name": "  Лина  "}) == "Лина",
          user_manager.teacher_name({"teacher_name": "  Лина  "}))
    check("имя из одного пробела+буквы не теряется",
          user_manager.teacher_name({"teacher_name": " К "}) == "К",
          user_manager.teacher_name({"teacher_name": " К "}))


# =========================================================
# 3. Имя живёт в профиле и перечитывается с диска
# =========================================================
def test_profile_field():
    print("\n[3] Поле teacher_name в профиле ученика")
    with TempProfiles():
        created = user_manager.create_user(
            "Дамиль", "male", 14, None, "", "🦊", True, "Damil", "Лина")
        check("create_user принимает teacher_name", created is not None, created)
        if created:
            stored = user_manager.get_user(created["id"])
            check("имя в профиле сохранено",
                  stored.get("teacher_name") == "Лина", stored.get("teacher_name"))
            check("teacher_name() вернул своё имя",
                  user_manager.teacher_name(stored) == "Лина",
                  user_manager.teacher_name(stored))

            user_manager.update_user(created["id"], {"teacher_name": "Кэт"})
            again = user_manager.get_user(created["id"])
            check("имя меняется через update_user",
                  user_manager.teacher_name(again) == "Кэт",
                  user_manager.teacher_name(again))

            user_manager.update_user(created["id"], {"teacher_name": ""})
            cleared = user_manager.get_user(created["id"])
            check("пустое имя → снова общее",
                  user_manager.teacher_name(cleared) == config.TEACHER_NAME,
                  user_manager.teacher_name(cleared))

        # старое имя не задано — в профиле пусто, значит берётся config
        plain = user_manager.create_user("Дамиль", "male", 14)
        if plain:
            stored = user_manager.get_user(plain["id"])
            check("новый профиль без имени поля teacher_name не ломается",
                  stored.get("teacher_name") == "", stored.get("teacher_name"))
            check("имя по умолчанию подставляется",
                  user_manager.teacher_name(stored) == config.TEACHER_NAME,
                  user_manager.teacher_name(stored))

        # длинную строку обрезаем: это имя, а не поле для заметок
        long_name = user_manager.get_user(
            user_manager.create_user("Дамиль 2", "male", 14,
                                     teacher_name="Я" * 80)["id"])
        check("длинное имя обрезается до 32 символов",
              len(long_name.get("teacher_name") or "") == 32,
              len(long_name.get("teacher_name") or ""))

        # позиционный вызов из delete_user/_resolve_user не должен сломаться
        old_style = user_manager.create_user("Ученик", "other", None, None, "",
                                             "🙂", complete=False)
        check("старый позиционный вызов работает", old_style is not None, old_style)


# =========================================================
# 4. Промпт: имя подставлено, род остался женским
# =========================================================
def test_prompt():
    print("\n[4] Промпт: имя преподавателя и женский род")
    base = {"mistakes": {}, "strengths": [], "topics_passed": [], "total_lessons": 0}

    default_lesson = prompt_builder.build_system_prompt("lesson", base, "en")
    check("по умолчанию в промпте Verbot",
          default_lesson.startswith("You are %s, a helpful AI assistant."
                                    % config.TEACHER_NAME),
          default_lesson[:60])
    check("женский род в промпте остался",
          "FEMININE GENDER" in default_lesson
          and "я преподавательница" in default_lesson, "нет блока рода")
    check("мужского рода в промпте нет",
          "male AI assistant" not in default_lesson.lower(), default_lesson[:200])

    own = prompt_builder.build_system_prompt("lesson", base, "en", teacher="Лина")
    check("своё имя попало в промпт урока",
          own.startswith("You are Лина, a helpful AI assistant."), own[:60])
    check("своё имя есть в блоке рода", "You are Лина, a female AI assistant" in own,
          own[:200])
    check("своего имени нет в свободном режиме по умолчанию",
          "You are Лина, a friendly AI companion." not in
          prompt_builder.build_system_prompt("free", base, "en"),
          "подстановка протекла в другой режим")
    check("своё имя попало в промпт свободного режима",
          prompt_builder.build_system_prompt("free", base, "en",
                                             teacher="Лина")
          .startswith("You are Лина, a friendly AI companion."))

    student = {"name": "Дамиль", "name_latin": "Damil", "gender": "male"}
    with_student = prompt_builder.build_system_prompt("lesson", base, "ru",
                                                      student=student,
                                                      teacher="Лина")
    check("блок ученика знает имя преподавателя",
          "describe YOU, Лина, not the student" in with_student,
          "нет строки про имя в блоке ученика")
    check("род ученика по-прежнему мужской",
          "MASCULINE forms about the student" in with_student,
          "род ученика потерялся")

    empty_name = prompt_builder.build_system_prompt("lesson", base, "en",
                                                   teacher="   ")
    check("имя из пробелов → имя по умолчанию",
          empty_name.startswith("You are %s," % config.TEACHER_NAME),
          empty_name[:60])


# =========================================================
# 5. ChatController: подпись реплики, статус и промпт
# =========================================================
def test_chat_controller():
    print("\n[5] ChatController: имя в чате, статусе и промпте")
    with TempProfiles():
        created = user_manager.create_user(
            "Дамиль", "male", 14, None, "", "🦊", True, "Damil", "Лина")
        uid = created["id"]

        llm = FakeLLM("Hello there!")
        ctrl = ChatController(llm=llm, mode="lesson", lang="en", user_id=uid)
        check("контроллер знает имя из профиля", ctrl.teacher == "Лина", ctrl.teacher)

        messages, statuses = [], []
        ctrl.on_message = lambda s, t: messages.append((s, t))
        ctrl.on_status = lambda text, color=None: statuses.append(text)
        ctrl.on_busy = lambda busy: None
        ctrl.on_response = lambda *a: None
        ctrl.on_analysis = lambda *a: None
        ctrl.on_plan = lambda *a: None

        ctrl._show_reply("Hi", "Hello there!")
        check("реплика подписана именем преподавателя",
              messages and messages[-1][0] == "Лина", messages[-1:])

        ok, reply = ctrl._request("Hi there")
        check("ответ получен", ok is True and reply == "Hello there!", reply)
        system = llm.calls[-1][0]["content"] if llm.calls else ""
        check("в промпте модели своё имя", "You are Лина," in system, system[:60])
        check("в промпте остался женский род", "FEMININE GENDER" in system,
              "нет блока рода")

        ctrl.send("One more turn")
        deadline = time.time() + 5
        while ctrl.busy and time.time() < deadline:
            time.sleep(0.02)
        check("статус с именем преподавателя",
              any("Лина думает" in s for s in statuses), statuses)

        # профиль БЕЗ своего имени → общее имя из config
        plain = user_manager.create_user("Второй", "male", 12)
        ctrl2 = ChatController(llm=FakeLLM(), mode="free", lang="en",
                               user_id=plain["id"])
        check("без своего имени — имя по умолчанию",
              ctrl2.teacher == config.TEACHER_NAME, ctrl2.teacher)


# =========================================================
# 6. Интерфейс: заголовок окна, шапка, форма, приветствие
# =========================================================
def test_ui_texts():
    print("\n[6] Окно: заголовок, подпись шапки, форма и приветствие")
    import ui.app as app_mod

    title = app_mod.window_title()
    check("в заголовке название приложения", config.APP_NAME in title, title)
    check("имя по умолчанию не дублируется", title.count(config.APP_NAME) == 1, title)
    check("своё имя видно в заголовке",
          app_mod.window_title("Лина") == "%s — Лина" % config.APP_NAME,
          app_mod.window_title("Лина"))
    check("в подписи шапки имя преподавателя",
          "Лина" in app_mod.subtitle_text("Лина"), app_mod.subtitle_text("Лина"))

    # форма профиля отдаёт имя → create_user его принимает (иначе поле теряется)
    form_keys = set(app_mod.EnglishTeacherApp._form_profile({
        "name": "Дамиль", "name_latin": "Damil", "gender": "male",
        "age": "14", "goal": "цель", "avatar": "🦊", "teacher_name": "Лина"}))
    accepted = set(inspect.signature(user_manager.create_user).parameters)
    check("teacher_name есть в полях формы", "teacher_name" in form_keys,
          sorted(form_keys))
    check("create_user принимает все поля формы",
          not (form_keys - accepted), sorted(form_keys - accepted))

    # приветствие берёт имя из профиля (метод не требует живого окна)
    class Stub:
        current_user = {"name": "Дамиль", "avatar": "🦊", "teacher_name": "Лина"}

        @property
        def teacher_name(self):
            return user_manager.teacher_name(self.current_user)

    greeting = app_mod.EnglishTeacherApp._greeting(Stub())
    check("в приветствии имя преподавателя", "Я Лина," in greeting, greeting)
    check("в приветствии нет старого имени", "Джейн" not in greeting, greeting)

    summary = app_mod.profile_summary({"name": "Дамиль", "teacher_name": "Лина"}, {},
                                      (0, 0))
    check("в профиле «Занятий с <имя>»",
          any("Занятий с Лина" in str(heading) for heading, _value in summary),
          summary)


# =========================================================
def main():
    print("=" * 60)
    print("Проверка имени преподавателя (Verbot) и его настройки в профиле")
    print("=" * 60)
    test_config()
    test_teacher_name_rules()
    test_profile_field()
    test_prompt()
    test_chat_controller()
    test_ui_texts()

    print("\n" + "=" * 60)
    if FAILED:
        print("ПРОВАЛЕНО ПРОВЕРОК: %d" % len(FAILED))
        for name in FAILED:
            print("  ❌ " + name)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
