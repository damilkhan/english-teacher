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

try:
    from ui.widgets import tooltip as _tooltip
except Exception:               # подсказка необязательна
    _tooltip = None

USER_SENDERS = ("Вы", "Вы (голос)")
DOT = "·"
EMOJI_PAD = 1          # px воздуха вокруг картинки-эмодзи, чтобы не липла к буквам

# Отступы полосы прокрутки от правого края области чата. Держим их
# константами: те же значения прибавляет резерв под робота-персонажа
# (set_character_reserve), иначе полоса «отклеилась» бы от текста.
SCROLL_PAD_X = 8
SCROLL_PAD_Y = 12

# Кнопка «прослушать повторно» (появляется рядом с именем Джейн ПОСЛЕ того,
# как реплика впервые озвучена до конца, и повторяет её по клику).
REPLAY_ICON = "\U0001F50A"          # 🔊 динамик
REPLAY_TOOLTIP = "Прослушать повторно"


class ChatView(ctk.CTkFrame):
    def __init__(self, parent, palette, greeting=None, corner_radius=None,
                 on_replay=None):
        # Свою рамку карточки НЕ рисуем: у левой карточки (left_frame) она уже
        # есть, и две скруглённые рамки друг над другом читались как
        # «раздвоенный border-right» и «лишние радиусы». Отделяем чат цветом.
        super().__init__(parent, fg_color=palette["chat_bg"],
                         corner_radius=corner_radius or theme.R["card"],
                         border_width=0,
                         height=140)   # запрос «минимум», растёт за счёт expand
        self.palette = palette
        self.on_replay = on_replay    # callback(text) — озвучить реплику повторно

        # «Прослушать повторно»: помним текст каждой реплики Джейн и её метку
        # в тексте (метка стоит сразу после имени — туда и вставим кнопку).
        self._msg_text = {}          # mark → текст реплики
        self._msg_widgets = {}       # mark → tk.Label с иконкой динамика
        self._replay_marks = set()   # для кого кнопка уже создана
        self._msg_seq = 0
        self._replay_icon = None     # держим ссылку на PhotoImage (иначе пропадёт)

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
            # отступы по краям: прямые углы tk.Text не упираются в скругление
            # карточки, поэтому «второй радиус» у углов больше не виден
            padx=16,
            pady=12,
            insertbackground=palette["accent"],
            selectbackground=palette["accent_soft"],
            selectforeground=palette["text_strong"],
            cursor="arrow",
            height=6,          # 6 строк запроса; фактическую высоту даст expand
        )
        self.text.pack(side="left", fill="both", expand=True)

        # Ползунок — узкий, скруглённый и приглушённый: широкий светлый «btn»
        # вплотную к краю читался как вторая рамка справа.
        self.scrollbar = ctk.CTkScrollbar(
            self, command=self.text.yview, width=6, corner_radius=3,
            fg_color="transparent",
            button_color=palette["muted"],
            button_hover_color=palette["btn_hover"],
        )
        self.scrollbar.pack(side="right", fill="y", padx=(0, SCROLL_PAD_X), pady=SCROLL_PAD_Y)
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
        """Рисует реплику и прокручивает чат вниз.

        Для реплик Джейн возвращает метку (mark) сразу после имени — по ней
        потом вставляется кнопка «прослушать повторно». Для «Вы» — None.
        """
        is_user = sender in USER_SENDERS
        head_tag = "head_user" if is_user else "head"
        body_tag = "body_user" if is_user else "body"

        header = f"{sender}  {DOT}  {stamp}" if stamp else sender

        self.text.configure(state="normal")
        self.text.insert("end", header, head_tag)
        mark = None
        if not is_user:
            # метка «end» после имени с гравитацией влево: следующая вставка
            # (\n) уйдёт ВПРАВО от неё, и точка останется сразу после имени
            mark = "replay_%d" % self._msg_seq
            self._msg_seq += 1
            self.text.mark_set(mark, "end-1c")   # СРАЗУ после имени (не за \n)
            self.text.mark_gravity(mark, tk.LEFT)
            self._msg_text[mark] = text
        self.text.insert("end", "\n", head_tag)
        self._insert_text(text, body_tag)
        self.text.insert("end", "\n", body_tag)
        self.text.configure(state="disabled")
        self.text.see("end")
        return mark

    def enable_replay(self, mark):
        """Показать кнопку «прослушать повторно» для реплики с меткой mark.

        Вызывается ПОСЛЕ того, как реплика впервые озвучена до конца. Если
        метка неизвестна/уже включена — ничего не делаем.
        """
        if not mark or mark in self._replay_marks:
            return
        if mark not in self._msg_text:
            return
        if not self._mark_exists(mark):
            return
        widget = self._make_replay_button(mark)
        if widget is None:
            return
        try:
            self.text.configure(state="normal")
            self.text.window_create(mark, window=widget, padx=4, align="center")
            self.text.configure(state="disabled")
        except Exception as exc:
            print("⚠️ Кнопка прослушивания не вставилась: %s" % exc)
            return
        self._replay_marks.add(mark)
        self._msg_widgets[mark] = widget

    def set_character_reserve(self, bottom=0):
        """Освободить место под персонажа внизу области чата.

        Робот стоит в правом нижнем углу области чата, но ПОВЕРХ неё: полоса
        прокрутки остаётся у правого края (и не режет чат пополам), а текст
        просто заканчивается выше робота — реплики его не задевают. Ширину
        текста НЕ сужаем: он идёт во всю ширину области, потому что робот
        находится ниже полосы текста.

        Почему это внешний pad-отступ упаковки, а не padx/pady самого tk.Text:
        в Tk 8.6 у Text они принимают ТОЛЬКО одно число, поэтому «снизу 181»
        иначе не задать.
        """
        bottom = max(0, int(bottom))
        try:
            # Узкая «запрошенная» ширина: фактическую даёт expand. Иначе запрос
            # текста в 80 символов мог бы влиять на раскладку карточки.
            self.text.configure(width=20)
            self.text.pack_configure(pady=(0, bottom))
            # Полосу прокрутки подрезаем снизу по тексту: она заканчивается
            # над роботом и не заходит на картинку.
            self.scrollbar.pack_configure(pady=(SCROLL_PAD_Y,
                                                SCROLL_PAD_Y + bottom))
        except Exception as exc:
            print("⚠️ Место под персонажа не зарезервировано: %s" % exc)

    def _mark_exists(self, mark):
        try:
            self.text.index(mark)
            return True
        except Exception:
            return False

    def _make_replay_button(self, mark):
        """Небольшая иконка-динамик с подсказкой; клик — повторная озвучка."""
        p = self.palette
        try:
            label = tk.Label(self.text, bd=0, highlightthickness=0,
                             bg=p["chat_bg"], cursor="hand2")
        except Exception:
            return None
        icon = self._ensure_replay_icon()
        if icon is not None:
            label.configure(image=icon)
        else:
            # Pillow/шрифта нет — оставим текстовый значок цветом темы
            label.configure(text=REPLAY_ICON, fg=p["accent"], font=theme.FONT_HEAD)
        if _tooltip is not None:
            _tooltip.ToolTip(label, REPLAY_TOOLTIP, p)
        label.bind("<Button-1>", lambda _e, m=mark: self._replay_clicked(m))
        return label

    def _ensure_replay_icon(self):
        """PhotoImage динамика (в цвете акцента). Кэшируем и держим ссылку."""
        if self._replay_icon is not None:
            return self._replay_icon
        if not emoji_render.available():
            return None
        try:
            from PIL import ImageTk
        except Exception:
            return None
        try:
            rgb = emoji_render.hex_to_rgb(self.palette["accent"])
            ink = emoji_render.render_mono(REPLAY_ICON, self._icon_size(),
                                           color=rgb + (255,))
            if ink is None:
                return None
            self._replay_icon = ImageTk.PhotoImage(ink, master=self.text)
        except Exception as exc:
            print("⚠️ Иконка прослушивания не нарисовалась: %s" % exc)
            self._replay_icon = None
        return self._replay_icon

    def _icon_size(self):
        """Размер иконки динамика — чуть больше шрифта имени (в пикселях)."""
        try:
            import tkinter.font as tkfont
            font = tkfont.Font(root=self, font=theme.FONT_HEAD)
            points = abs(font.actual("size")) + 3
            scaling = float(self.tk.call("tk", "scaling"))
            return emoji_render.size_from_font(points, scaling)
        except Exception:
            return emoji_render.DEFAULT_PX

    def _replay_clicked(self, mark):
        """Клик по кнопке: озвучить реплику повторно."""
        text = self._msg_text.get(mark)
        if text and self.on_replay is not None:
            try:
                self.on_replay(text)
            except Exception as exc:
                print("⚠️ Повторное прослушивание не удалось: %s" % exc)

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("0.0", "end")
        self.text.configure(state="disabled")
        # картинок в тексте больше нет — и имена их символов не нужны
        self._image_tokens.clear()
        self._emoji.clear()
        # метки реплик и кнопки повтора тоже устарели
        self._msg_text.clear()
        self._msg_widgets.clear()
        self._replay_marks.clear()

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
        self.configure(fg_color=palette["chat_bg"])          # рамки у карточки нет
        self.text.configure(bg=palette["chat_bg"], fg=palette["text"],
                            insertbackground=palette["accent"],
                            selectbackground=palette["accent_soft"],
                            selectforeground=palette["text_strong"])
        self.scrollbar.configure(button_color=palette["muted"],
                                 button_hover_color=palette["btn_hover"])
        self._configure_tags(palette)
        # картинки-эмодзи перерисовывать не нужно: фон у них прозрачный,
        # поэтому они одинаково ложатся на светлую и тёмную палитру.
        # А кнопки повтора — обычные Label: у них фон под цвет чата и иконка
        # в цвете акцента, поэтому перекрашиваем под новую палитру.
        self._replay_icon = None
        icon = self._ensure_replay_icon()
        for mark, widget in self._msg_widgets.items():
            try:
                widget.configure(bg=palette["chat_bg"])
                if icon is not None:
                    widget.configure(image=icon, text="")
                else:
                    widget.configure(text=REPLAY_ICON, fg=palette["accent"])
            except Exception:
                pass

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
