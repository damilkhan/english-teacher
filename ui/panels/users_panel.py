# -*- coding: utf-8 -*-
# =========================================================
# UI/PANELS/USERS_PANEL.PY — правая панель «Пользователи»
# =========================================================
# Одна строка на профиль:  [цветной аватар] Имя · Уровень .... [🎯][✏️][🗑️]
# 🎯 — перепройти тест уровня, ✏️ — редактировать, 🗑️ — удалить.
# Клик по строке делает профиль активным. Внизу — «+ Добавить пользователя».
#
# Данные берёт из user_manager по запросу через refresh(), поэтому после
# любого добавления/удаления достаточно вызвать refresh() — список
# перечитывается с диска и панель всегда честная.
# =========================================================

import tkinter.messagebox as messagebox
import customtkinter as ctk

import theme
import user_manager

try:
    # Цветной аватар: Tk рисует эмодзи однотонным контуром, а через Pillow
    # глиф из Segoe UI Emoji выходит цветным. Пакет нужен только для этого.
    from ui import emoji_render
except Exception:
    emoji_render = None


class UsersPanel(ctk.CTkFrame):
    # --- геометрия строки списка (ОДНА строка) -------------------------
    # Раскладка:  [цветной аватар]  Имя · Уровень  .....  [🎯][✏️][🗑️]
    # Высоту задаём явно: иначе блок текста занимает всю высоту карточки и
    # его подложка перекрывает 1 px рамку активной строки — рамка рвётся.
    ROW_HEIGHT = 46        # высота строки профиля
    ICON_SIZE = 27         # квадрат под кнопку-иконку
    AVATAR_W = 26          # место под аватар
    AVATAR_PX = 24         # размер цветной картинки-аватара
    NAME_SIZE = 15         # кегль имени — главный акцент строки
    MIN_NAME_PX = 48       # столько минимум оставляем имени

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
            height=self.ROW_HEIGHT,
            border_width=1 if active else 0,
            border_color=p["accent"] if active else p["surface"])
        row.pack(fill="x", padx=2, pady=3)
        row.pack_propagate(False)

        # действия — прижаты вправо: [🎯][✏️][🗑️]
        for emoji, command, pad in (
                ("🗑️", lambda u=user: self._delete(u), (1, 0)),
                ("✏️", lambda u=user: self._edit(u), (1, 1)),
                ("🎯", lambda u=user: self._test(u), (1, 1))):
            self._icon_button(row, emoji, command).pack(side="right", padx=pad)

        # аватар — слева. Эмодзи рисуем Pillow-ом (embedded_color): Tk показал
        # бы его однотонным контуром, а нужен цветной.
        avatar_token = str(user.get("avatar") or "🙂")
        avatar = ctk.CTkLabel(row, text="", width=self.AVATAR_W)
        avatar_image = self._avatar_image(avatar_token)
        if avatar_image is not None:
            avatar.configure(image=avatar_image)
        else:
            avatar.configure(text=avatar_token, font=("Segoe UI Emoji", 17))
        avatar.pack(side="left", padx=(6, 0))

        # «Имя · Уровень» — занимает весь остаток строки
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=(2, 0))

        full_name = user.get("name") or "Ученик"
        name = ctk.CTkLabel(info, text=full_name, anchor="w",
                            font=(theme.FONT_UI[0], self.NAME_SIZE, "bold"),
                            text_color=p["text_strong"])
        name.pack(side="left")
        # в одну строку «не определён» не помещается — показываем «—»
        level_text = user_manager.level_label(user.get("level"))
        if level_text not in user_manager.LEVELS:
            level_text = "—"
        meta_text = "· " + level_text
        meta = ctk.CTkLabel(info, text=meta_text, anchor="w",
                            font=theme.FONT_SMALL, text_color=p["muted"])
        meta.pack(side="left", padx=(3, 0))

        # длинное имя (и «не определён») аккуратно вписываем в строку
        info.bind("<Configure>",
                  lambda _e, box=info, n=name, m=meta:
                  self._fit_row_text(box, n, m, full_name, meta_text))

        # клик по строке (и по аватар/имя) — сделать активным
        for widget in (row, avatar, info, name):
            widget.bind("<Button-1>", lambda _e, uid=user["id"]: self._select(uid))
        return row

    def _icon_button(self, parent, text, command):
        """Кнопка-иконка ФИКСИРОВАННОГО размера.

        CTkButton сам подгоняет ширину под глиф эмодзи, а 🗑️/✏️/🎯 в Segoe UI
        Emoji шире заявленных 34 px — кнопки вылезали за границы строки.
        Оборачиваем кнопку в квадрат-контейнер: размер задаёт он, а кнопка
        лишь заполняет его.
        """
        p = self.palette
        holder = ctk.CTkFrame(parent, fg_color="transparent",
                              width=self.ICON_SIZE, height=self.ICON_SIZE)
        holder.pack_propagate(False)
        ctk.CTkButton(
            holder, text=text, command=command,
            font=("Segoe UI Emoji", 13), cursor="hand2",
            fg_color=p["btn"], hover_color=p["btn_hover"],
            text_color=p["text"], corner_radius=theme.R["button"],
        ).pack(fill="both", expand=True)
        return holder

    # -----------------------------------------------------
    # Аватар и подписи
    # -----------------------------------------------------
    def _avatar_image(self, token):
        """Цветная картинка аватара (Pillow, embedded_color) или None.

        Tk рисует эмодзи одним цветом, поэтому аватар выходил бледным
        контуром. ui.emoji_render отдаёт цветной глиф из Segoe UI Emoji;
        результат кэшируем — Tk сам ссылку на картинку не держит.
        """
        if emoji_render is None:
            return None
        cache = getattr(self, "_avatar_cache", None)
        if cache is None:
            cache = {}
            self._avatar_cache = cache
        if token in cache:
            return cache[token]
        image = None
        if emoji_render.available():
            ink = emoji_render.render(token, self.AVATAR_PX)
            if ink is not None:
                try:
                    image = ctk.CTkImage(light_image=ink, dark_image=ink,
                                         size=(ink.width, ink.height))
                except Exception:
                    image = None
        cache[token] = image
        return image

    def _name_font(self):
        """Шрифт имени (один объект на панель — его дёшево мерить)."""
        font = getattr(self, "_name_font_obj", None)
        if font is None:
            try:
                import tkinter.font as tkfont
                # CTk переводит кегль в ПИКСЕЛИ (отрицательный размер).
                # Меряем так же — иначе ширина выходит завышенной и имя
                # обрезается раньше времени.
                font = tkfont.Font(family=theme.FONT_UI[0],
                                   size=-self.NAME_SIZE, weight="bold")
            except Exception:
                font = False
            self._name_font_obj = font
        return font or None

    def _meta_font(self):
        """Шрифт уровня (нужен, чтобы измерить ширину подписи)."""
        font = getattr(self, "_meta_font_obj", None)
        if font is None:
            try:
                import tkinter.font as tkfont
                font = tkfont.Font(family=theme.FONT_SMALL[0],
                                   size=-theme.FONT_SMALL[1])
            except Exception:
                font = False
            self._meta_font_obj = font
        return font or None

    @staticmethod
    def _ellipsize(text, font, max_px):
        """Обрезает строку по ширине, добавляя «…».

        Обрезка нужна только для очень длинных имён и для «не определён»:
        обычные имена помещаются целиком.
        """
        text = str(text or "")
        if font is None or max_px <= 0:
            return text
        if font.measure(text) <= max_px:
            return text
        cut = text
        while cut and font.measure(cut + "…") > max_px:
            cut = cut[:-1]
        return (cut + "…") if cut else "…"

    def _fit_row_text(self, box, name_label, meta_label, name_text, meta_text):
        """Вписывает «Имя · Уровень» в строку: имя приоритетнее уровня."""
        font = self._name_font()
        if font is None:
            return
        total = max(40, box.winfo_width() - 6)
        meta_font = self._meta_font()

        meta_shown = meta_text
        meta_w = meta_font.measure(meta_text) if meta_font else 0
        if total - meta_w < self.MIN_NAME_PX:
            meta_shown = self._ellipsize(meta_text, meta_font,
                                         max(18, total - self.MIN_NAME_PX))
            meta_w = meta_font.measure(meta_shown) if meta_font else 0

        name_shown = self._ellipsize(name_text, font, max(24, total - meta_w - 8))
        if name_label.cget("text") != name_shown:
            name_label.configure(text=name_shown)
        if meta_label.cget("text") != meta_shown:
            meta_label.configure(text=meta_shown)
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
