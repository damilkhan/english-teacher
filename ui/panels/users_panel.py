# -*- coding: utf-8 -*-
# =========================================================
# UI/PANELS/USERS_PANEL.PY — правая панель «Пользователи»
# =========================================================
# Список профилей: аватар + имя + уровень, у каждого строки — кнопки
# ✏️ (редактировать) и 🗑️ (удалить). Клик по строке делает профиль
# активным. Внизу — «+ Добавить пользователя» (неактивна, если 8 профилей).
#
# Данные берёт из user_manager по запросу через refresh(), поэтому после
# любого добавления/удаления достаточно вызвать refresh() — список
# перечитывается с диска и панель всегда честная.
# =========================================================

import tkinter.messagebox as messagebox
import customtkinter as ctk

import theme
import user_manager


class UsersPanel(ctk.CTkFrame):
    def __init__(self, parent, palette, active_id=None,
                 on_add=None, on_edit=None, on_delete=None,
                 on_select=None, on_close=None, on_test=None):
        super().__init__(parent, fg_color=palette["surface"],
                         corner_radius=theme.R["card"],
                         border_width=1, border_color=palette["border"])
        self.palette = palette
        self.active_id = active_id
        self.on_add = on_add
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_select = on_select
        self.on_close = on_close
        self.on_test = on_test
        self._rows = []

        self.title_label = ctk.CTkLabel(self, text="ПОЛЬЗОВАТЕЛИ",
                                        font=theme.FONT_PANEL_TITLE,
                                        text_color=palette["text_strong"])
        self.title_label.pack(anchor="w", padx=20, pady=(20, 2))

        self.count_label = ctk.CTkLabel(self, text="", font=theme.FONT_SMALL,
                                        text_color=palette["muted"])
        self.count_label.pack(anchor="w", padx=20, pady=(0, 8))

        # ---------- список (скроллится, если профилей много) ----------
        self.list_frame = ctk.CTkScrollableFrame(
            self, fg_color=palette["surface_alt"],
            corner_radius=theme.R["block"])
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=(4, 10))

        # ---------- кнопки ----------
        self.close_btn = ctk.CTkButton(
            self, text="Закрыть", command=self.on_close,
            fg_color=palette["btn"], hover_color=palette["btn_hover"],
            width=200, height=42, cursor="hand2", text_color=palette["text"],
            corner_radius=theme.R["button"], border_width=1,
            border_color=palette["border"], font=theme.FONT_UI)
        self.close_btn.pack(side="bottom", pady=(0, 16), padx=20, fill="x")

        self.add_btn = ctk.CTkButton(
            self, text="+  Добавить пользователя", command=self._add,
            fg_color=palette["accent"], hover_color=palette["accent_hover"],
            width=200, height=44, cursor="hand2", text_color="#FFFFFF",
            corner_radius=theme.R["button"], font=theme.FONT_UI)
        self.add_btn.pack(side="bottom", pady=(0, 10), padx=20, fill="x")

        self.refresh()

    # -----------------------------------------------------
    # Список
    # -----------------------------------------------------
    def refresh(self, active_id=None):
        if active_id is not None:
            self.active_id = active_id

        for row in self._rows:
            row.destroy()
        self._rows = []

        users = user_manager.list_users()
        self.count_label.configure(text="Профилей: %d / %d" % (len(users), user_manager.MAX_USERS))

        if not users:
            empty = ctk.CTkLabel(self.list_frame, text="Пока нет ни одного профиля.\n"
                                                       "Добавь первого ученика.",
                                 text_color=self.palette["muted"], font=theme.FONT_SMALL,
                                 justify="left")
            empty.pack(anchor="w", padx=12, pady=12)
            self._rows.append(empty)
        else:
            for user in users:
                self._rows.append(self._build_row(user))

        full = user_manager.is_full()
        self.add_btn.configure(
            state="disabled" if full else "normal",
            fg_color=self.palette["btn"] if full else self.palette["accent"],
            hover_color=self.palette["btn_hover"] if full else self.palette["accent_hover"],
            text_color=self.palette["muted"] if full else "#FFFFFF",
            text="Лимит 8 профилей" if full else "+  Добавить пользователя")

    def _build_row(self, user):
        p = self.palette
        active = (user["id"] == self.active_id)

        row = ctk.CTkFrame(
            self.list_frame,
            fg_color=p["accent_soft"] if active else p["surface"],
            corner_radius=theme.R["block"],
            border_width=1 if active else 0,
            border_color=p["accent"] if active else p["surface"])
        row.pack(fill="x", padx=2, pady=3)

        avatar = ctk.CTkLabel(row, text=user.get("avatar", "🙂"),
                              font=("Segoe UI Emoji", 20), width=34)
        avatar.pack(side="left", padx=(10, 4), pady=8)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        name = ctk.CTkLabel(info, text=user.get("name", "Ученик"), anchor="w",
                            font=(theme.FONT_UI[0], 13, "bold"),
                            text_color=p["text_strong"] if active else p["text"])
        name.pack(anchor="w")
        meta = " · ".join(x for x in (user.get("level"), self._age(user)) if x)
        ctk.CTkLabel(info, text=meta, anchor="w", font=theme.FONT_SMALL,
                     text_color=p["muted"]).pack(anchor="w")

        trash = self._icon_button(row, "🗑️", lambda: self._delete(user))
        trash.pack(side="right", padx=(2, 8))
        pencil = self._icon_button(row, "✏️", lambda: self._edit(user))
        pencil.pack(side="right", padx=2)
        target = self._icon_button(row, "🎯", lambda: self._test(user))
        target.pack(side="right", padx=2)

        # клик по строке (и по аватар/имя) — сделать активным
        for widget in (row, avatar, info, name):
            widget.bind("<Button-1>", lambda _e, uid=user["id"]: self._select(uid))
        return row

    def _icon_button(self, parent, text, command):
        p = self.palette
        return ctk.CTkButton(
            parent, text=text, width=34, height=32, command=command,
            font=("Segoe UI Emoji", 14), cursor="hand2",
            fg_color=p["btn"], hover_color=p["btn_hover"],
            text_color=p["text"], corner_radius=theme.R["button"])

    @staticmethod
    def _age(user):
        age = user.get("age")
        return "%d лет" % age if isinstance(age, int) else ""

    # -----------------------------------------------------
    # Действия
    # -----------------------------------------------------
    def _select(self, user_id):
        if user_id == self.active_id:
            return
        self.active_id = user_id
        if callable(self.on_select):
            self.on_select(user_id)
        self.refresh()

    def _edit(self, user):
        if callable(self.on_edit):
            self.on_edit(user["id"])
        self.refresh()

    def _test(self, user):
        """Перепройти тест уровня для этого профиля."""
        if callable(self.on_test):
            self.on_test(user["id"])
        self.refresh()

    def _add(self):
        if user_manager.is_full():
            return
        if callable(self.on_add):
            self.on_add()
        self.refresh()

    def _delete(self, user):
        name = user.get("name", "профиль")
        if not messagebox.askyesno(
                "Удаление профиля",
                "Удалить профиль «%s»?\n\n"
                "Вместе с ним удалится и его прогресс обучения. "
                "Действие нельзя отменить." % name, parent=self):
            return
        if callable(self.on_delete):
            self.on_delete(user["id"])
        self.refresh()

    # -----------------------------------------------------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["surface"], border_color=palette["border"])
        self.title_label.configure(text_color=palette["text_strong"])
        self.count_label.configure(text_color=palette["muted"])
        self.list_frame.configure(fg_color=palette["surface_alt"])
        self.close_btn.configure(fg_color=palette["btn"], hover_color=palette["btn_hover"],
                                 text_color=palette["text"], border_color=palette["border"])
        self.refresh()
