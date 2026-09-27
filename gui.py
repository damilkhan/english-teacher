# -*- coding: utf-8 -*-
# =========================================================
# GUI.PY — совместимый фасад
# =========================================================
# Раньше здесь был монолит на ~700 строк. После рефакторинга код живёт в:
#
#   ui/app.py                      сборка окна
#   ui/widgets/*                   виджеты (чат, ввод, кнопки, эквалайзер)
#   ui/panels/settings_panel.py    правая панель настроек
#   controllers/chat_controller.py       диалог с Джейн
#   controllers/recording_controller.py  запись и распознавание
#   controllers/server_monitor.py        опрос состояния сервера
#   theme.py                       цвета и шрифты
#   prompt_builder.py              тексты промптов
#   profile_store.py               student_profile.json
#   llm_client.py                  запросы к llama-server
#
# Этот файл оставлен, чтобы не сломать существующие запускатели
# (launcher.pyw делает `import gui`), и чтобы `python gui.py` работал.
# =========================================================

from ui.app import EnglishTeacherApp  # noqa: F401  (реэкспорт для launcher.pyw)

__all__ = ["EnglishTeacherApp"]


if __name__ == "__main__":
    EnglishTeacherApp().run()
