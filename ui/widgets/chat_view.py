# -*- coding: utf-8 -*-
"""ui.widgets.chat_view — область чата.

Редизайн: сообщения получили отступы (lmargin), воздух между репликами
(spacing1/spacing3), ник окрашен по роли — Джейн акцентом, «Вы» цианом.

Эмодзи теперь рисуются картинками (ui/emoji_render.py): Tk выводит цветной
глиф Segoe UI Emoji чёрным контуром, поэтому в чате вместо 😊 был плоский
значок, а на тёмной теме он почти не читался.
"""

import tkinter as tk
from datetime import datetime

import customtkinter as ctk

import theme
from ui import emoji_render

USER_SENDERS = ("Вы", "Вы (голос)")
DOT = "·"
EMOJI_PAD = 1          # px воздуха вокруг картинки-эмодзи, чтобы не липла к буквам


class ChatView(ctk.CTkFrame):
    def __init__(self, parent, palette, greeting=None, corner_radius=None):
        super().__init__(parent, fg_color=palette["chat_bg"],
                         corner_radius=corner_radius or theme.R["card"],
                         border_width=1, border_color=palette["border"],
                         height=140)   # запрос «минимум», растёт за счёт expand
        self.palette = palette

        # область текста внутри карточки
        self.text = tk.Text(
            self,
            wrap="word",
            font=theme.FONT_BODY,
            bg=palette["chat_bg"],
            fg=palette["text"],
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            padx=10,
            pady=10,
            insertbackground=palette["accent"],
            selectbackground=palette["accent_soft"],
            selectforeground=palette["text_strong"],
            cursor="arrow",
            height=6,          # 6 строк запроса; фактическую высоту даст expand
        )
        self.text.pack(side="left", fill="both", expand=True)

        self.scrollbar = ctk.CTkScrollbar(
            self, command=self.text.yview, width=8,
            fg_color="transparent",
            button_color=palette["btn"],
            button_hover_color=palette["btn_hover"],
        )
        self.scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=6)
        self.text.configure(yscrollcommand=self.scrollbar.set)

        # --- цветные эмодзи ---
        # Tk не умеет цветные шрифты, поэтому эмодзи подменяются картинками.
        # _image_tokens помнит, какой символ стоит за каждой картинкой, —
        # иначе get_text() вернул бы текст без эмодзи.
        self._emoji = emoji_render.EmojiImages(size=self._emoji_size(),
                                               master=self.text)
        self._image_tokens = {}
        self._image_seq = 0
        if not emoji_render.available():
            print("ℹ️ Цветные эмодзи недоступны (нет Pillow или эмодзи-шрифта) — "
                  "в чате будут обычные символы")

        self._configure_tags(palette)
        if greeting:
            sender, text = greeting
            self.add_message(sender, text, stamp=None)
        self.text.configure(state="disabled")

    # ---------- API ----------
    def add_message(self, sender, text, stamp=None):
        """Рисует реплику и прокручивает чат вниз."""
        is_user = sender in USER_SENDERS
        head_tag = "head_user" if is_user else "head"
        body_tag = "body_user" if is_user else "body"

        header = f"{sender}  {DOT}  {stamp}" if stamp else sender

        self.text.configure(state="normal")
        self.text.insert("end", header + "\n", head_tag)
        self._insert_text(text, body_tag)
        self.text.insert("end", "\n", body_tag)
        self.text.configure(state="disabled")
        self.text.see("end")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("0.0", "end")
        self.text.configure(state="disabled")
        # картинок в тексте больше нет — и имена их символов не нужны
        self._image_tokens.clear()
        self._emoji.clear()

    def get_text(self):
        """Весь текст чата. Эмодзи-картинки возвращаются своими символами.

        Через Text.dump(), потому что картинка для Tk — не текст: обычный
        get() её просто пропустил бы, и в «сыром» чате терялись бы эмодзи.
        """
        parts = []
        for key, value, _index in self.text.dump("0.0", "end", text=True, image=True):
            if key == "text":
                parts.append(value)
            elif key == "image":
                parts.append(self._image_tokens.get(value, ""))
        return "".join(parts)

    # ---------- внутреннее ----------
    def _insert_text(self, text, tag):
        """Вставляет текст реплики, подменяя эмодзи цветными картинками.

        Если картинку получить не удалось (нет Pillow, не нашёлся шрифт,
        глиф оказался не цветным) — символ пишется текстом, как было до
        ui/emoji_render.py.
        """
        if not text:
            return
        for is_emoji, chunk in emoji_render.split(text):
            if not is_emoji:
                self.text.insert("end", chunk, tag)
                continue

            photo = self._emoji.photo(chunk, master=self.text)
            if photo is None:
                self.text.insert("end", chunk, tag)
                continue

            self._image_seq += 1
            name = f"emj{self._image_seq}"
            self.text.image_create("end", image=photo, name=name,
                                   align=emoji_render.ALIGN, padx=EMOJI_PAD)
            # картинку тоже помечаем тегом реплики: если эмодзи стоит первым
            # символом строки, отступ абзаца (lmargin1) Tk берёт именно с него
            self.text.tag_add(tag, name)
            self._image_tokens[name] = chunk

    def _emoji_size(self):
        """Размер картинок-эмодзи под шрифт чата (в пикселях, не «на глаз»)."""
        try:
            import tkinter.font as tkfont
            font = tkfont.Font(root=self, font=theme.FONT_BODY)
            points = abs(font.actual("size"))
            scaling = float(self.tk.call("tk", "scaling"))
            return emoji_render.size_from_font(points, scaling)
        except Exception:
            return emoji_render.DEFAULT_PX

    # ---------- оформление ----------
    def apply_theme(self, palette):
        self.palette = palette
        self.configure(fg_color=palette["chat_bg"], border_color=palette["border"])
        self.text.configure(bg=palette["chat_bg"], fg=palette["text"],
                            insertbackground=palette["accent"],
                            selectbackground=palette["accent_soft"],
                            selectforeground=palette["text_strong"])
        self.scrollbar.configure(button_color=palette["btn"],
                                 button_hover_color=palette["btn_hover"])
        self._configure_tags(palette)
        # картинки-эмодзи перерисовывать не нужно: фон у них прозрачный,
        # поэтому они одинаково ложатся на светлую и тёмную палитру.

    def _configure_tags(self, palette):
        common = dict(lmargin1=14, lmargin2=14, rmargin=14)
        self.text.tag_configure("head", foreground=palette["accent"],
                                font=theme.FONT_HEAD, spacing1=8, **common)
        self.text.tag_configure("head_user", foreground=palette["cyan"],
                                font=theme.FONT_HEAD, spacing1=8, **common)
        self.text.tag_configure("body", foreground=palette["text"],
                                font=theme.FONT_BODY, spacing3=10, **common)
        self.text.tag_configure("body_user", foreground=palette["text_strong"],
                                font=theme.FONT_BODY, spacing3=10, **common)
