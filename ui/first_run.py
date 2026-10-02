# -*- coding: utf-8 -*-
# =========================================================
# UI/FIRST_RUN.PY — форма первого запуска / редактирования профиля
# =========================================================
# Модальное окно: имя, пол, возраст, уровень (A1–C1), цель, аватар (эмодзи).
# Одна и та же форма работает в двух режимах:
#   • создание  — при первом запуске (профилей ещё нет) либо по кнопке «+»;
#   • редактирование — по кнопке ✏️ в меню «Пользователи» (user передан).
#
# Возвращает словарь с полями профиля или None, если окно закрыли.
# Тема берётся из theme.palette, поэтому форма выглядит как остальное окно.
# =========================================================

import tkinter as tk
import customtkinter as ctk

import theme
import user_manager


class FirstRunForm(ctk.CTkToplevel):
    def __init__(self, parent, palette, user=None):
        super().__init__(parent)
        self.palette = palette
        self.edit_mode = user is not None
        self.result = None
        self._avatar_buttons = {}

        self.title("Профиль ученика")
        self.configure(fg_color=palette["window"])
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._center(parent, 470, 640)

        p = palette
        # ---------- шапка ----------
        head = ctk.CTkFrame(self, fg_color=p["surface"], corner_radius=theme.R["card"])
        head.pack(fill="x", padx=18, pady=(18, 12))
        self.title_lbl = ctk.CTkLabel(
            head,
            text="Редактирование профиля" if self.edit_mode else "Добро пожаловать!",
            font=(theme.FONT_PANEL_TITLE[0], 18, "bold"),
            text_color=p["text_strong"])
        self.title_lbl.pack(anchor="w", padx=18, pady=(16, 2))
        self.sub_lbl = ctk.CTkLabel(
            head, text="Заполни профиль — Джейн подстроит уроки под тебя.",
            font=theme.FONT_SMALL, text_color=p["muted"], justify="left")
        self.sub_lbl.pack(anchor="w", padx=18, pady=(0, 16))

        # ---------- поля ----------
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18)

        self.name_var = ctk.StringVar(value=(user or {}).get("name", ""))
        self.age_var = ctk.StringVar(value=self._age_text((user or {}).get("age")))
        self.goal_var = ctk.StringVar(value=(user or {}).get("goal", ""))
        self.gender_var = ctk.StringVar(value=(user or {}).get("gender", "other"))
        self.level_var = ctk.StringVar(value=(user or {}).get("level", "A1"))
        self.avatar_var = ctk.StringVar(value=(user or {}).get("avatar", user_manager.AVATARS[0]))

        self._section(body, "КАК ТЕБЯ ЗОВУТ?")
        self.name_entry = self._entry(body, self.name_var, "Например: Аня")

        self._section(body, "ПОЛ")
        self.gender_widget = ctk.CTkSegmentedButton(
            body, values=[user_manager.GENDER_LABELS[g] for g in user_manager.GENDERS],
            command=self._on_gender,
            font=theme.FONT_UI, height=34, corner_radius=theme.R["button"],
            selected_color=p["accent"], selected_hover_color=p["accent_hover"],
            unselected_color=p["btn"], unselected_hover_color=p["btn_hover"],
            text_color=p["text"])
        self.gender_widget.pack(fill="x", pady=(6, 0))
        self.gender_widget.set(user_manager.GENDER_LABELS.get(self.gender_var.get(), "Другое"))

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True, padx=(12, 0))

        self._section(left, "ВОЗРАСТ")
        self.age_entry = self._entry(left, self.age_var, "14", width=120)

        self._section(right, "УРОВЕНЬ")
        self.level_widget = ctk.CTkSegmentedButton(
            right, values=list(user_manager.LEVELS), command=lambda v: self.level_var.set(v),
            font=theme.FONT_UI, height=34, corner_radius=theme.R["button"],
            selected_color=p["accent"], selected_hover_color=p["accent_hover"],
            unselected_color=p["btn"], unselected_hover_color=p["btn_hover"],
            text_color=p["text"])
        self.level_widget.set(self.level_var.get())
        self.level_widget.pack(fill="x", pady=(6, 0))

        self._section(body, "ЦЕЛЬ ОБУЧЕНИЯ")
        self.goal_entry = self._entry(body, self.goal_var, "Заговорить свободно / сдать экзамен")

        self._section(body, "АВАТАР")
        self._avatar_grid(body)
        self.custom_avatar = self._entry(body, self.avatar_var, "или впиши свой эмодзи")

        # ---------- низ: ошибка + кнопка ----------
        self.error_lbl = ctk.CTkLabel(self, text="", font=theme.FONT_SMALL,
                                      text_color=p["err"])
        self.error_lbl.pack(anchor="w", padx=36, pady=(8, 0))

        self.submit_btn = ctk.CTkButton(
            self, text="Начать обучение" if not self.edit_mode else "Сохранить",
            command=self._submit, height=46, cursor="hand2",
            fg_color=p["accent"], hover_color=p["accent_hover"],
            text_color="#FFFFFF", corner_radius=theme.R["button"], font=theme.FONT_UI)
        self.submit_btn.pack(fill="x", padx=36, pady=(6, 20))

        for var in (self.name_var, self.age_var, self.avatar_var):
            var.trace_add("write", lambda *_: self._refresh())

        self.after(60, self._grab)
        self._refresh()

    # -----------------------------------------------------
    # Строительные блоки
    # -----------------------------------------------------
    def _section(self, parent, caption):
        ctk.CTkLabel(parent, text=caption, font=theme.FONT_SECTION,
                     text_color=self.palette["muted"]).pack(anchor="w", pady=(14, 0))

    def _entry(self, parent, variable, placeholder, width=None):
        entry = ctk.CTkEntry(
            parent, textvariable=variable, placeholder_text=placeholder,
            height=38, corner_radius=theme.R["input"], font=theme.FONT_UI,
            fg_color=self.palette["input_bg"], border_color=self.palette["border"],
            text_color=self.palette["text"])
        if width:
            entry.configure(width=width)
            entry.pack(anchor="w", pady=(6, 0))
        else:
            entry.pack(fill="x", pady=(6, 0))
        return entry

    def _avatar_grid(self, parent):
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x", pady=(6, 0))
        for i, emoji in enumerate(user_manager.AVATARS):
            btn = ctk.CTkButton(
                grid, text=emoji, width=44, height=40, corner_radius=theme.R["block"],
                font=("Segoe UI Emoji", 18), cursor="hand2",
                fg_color=self.palette["btn"], hover_color=self.palette["btn_hover"],
                text_color=self.palette["text"],
                command=lambda e=emoji: self._pick_avatar(e))
            btn.grid(row=i // 8, column=i % 8, padx=3, pady=3)
            self._avatar_buttons[emoji] = btn

    # -----------------------------------------------------
    # Логика формы
    # -----------------------------------------------------
    @staticmethod
    def _age_text(age):
        return "" if age in (None, "") else str(age)

    def _on_gender(self, label):
        for key, lbl in user_manager.GENDER_LABELS.items():
            if lbl == label:
                self.gender_var.set(key)
                break

    def _pick_avatar(self, emoji):
        self.avatar_var.set(emoji)

    def _refresh(self):
        """Подсветка выбранного аватара + доступность кнопки."""
        current = self.avatar_var.get().strip()
        for emoji, btn in self._avatar_buttons.items():
            chosen = (emoji == current)
            btn.configure(fg_color=self.palette["accent"] if chosen else self.palette["btn"],
                          text_color="#FFFFFF" if chosen else self.palette["text"])

        ok, reason = self._validate()
        self.error_lbl.configure(text="" if ok else reason)
        self.submit_btn.configure(state="normal" if ok else "disabled",
                                  fg_color=self.palette["accent"] if ok else self.palette["btn"],
                                  text_color="#FFFFFF" if ok else self.palette["muted"])

    def _validate(self):
        if not self.name_var.get().strip():
            return False, "Укажи имя."
        age = self.age_var.get().strip()
        if age:
            try:
                if not (5 <= int(age) <= 120):
                    return False, "Возраст должен быть от 5 до 120."
            except ValueError:
                return False, "Возраст — это число."
        if not self.avatar_var.get().strip():
            return False, "Выбери аватар."
        return True, ""

    def _gender_value(self):
        """Ярлык с сегмента («Женский») → ключ («female»)."""
        label = self.gender_widget.get()
        for key, lbl in user_manager.GENDER_LABELS.items():
            if lbl == label:
                return key
        return self.gender_var.get()

    def _submit(self):
        ok, _ = self._validate()
        if not ok:
            return
        # значения берём С ВИДЖЕТОВ: программный .set() не вызывает command
        self.gender_var.set(self._gender_value())
        self.level_var.set(self.level_widget.get())
        self.result = {
            "name": self.name_var.get().strip(),
            "gender": self._gender_value(),
            "age": self.age_var.get().strip() or None,
            "level": self.level_widget.get(),
            "goal": self.goal_var.get().strip(),
            "avatar": self.avatar_var.get().strip(),
        }
        self._close()

    def _cancel(self):
        self.result = None
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    # -----------------------------------------------------
    def _center(self, parent, w, h):
        try:
            parent.update_idletasks()
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 2)
        except Exception:
            x = y = 120
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _grab(self):
        try:
            self.grab_set()
            self.name_entry.focus_set()
            self.lift()
        except Exception:
            pass

    # -----------------------------------------------------
    # Публичный помощник: открыть и дождаться результата
    # -----------------------------------------------------
    @classmethod
    def ask(cls, parent, palette, user=None):
        form = cls(parent, palette, user)
        parent.wait_window(form)
        return form.result
