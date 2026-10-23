# -*- coding: utf-8 -*-
"""ui.widgets.chat_view — область чата в стиле мессенджера.

ЧТО ИЗМЕНИЛОСЬ (решение ученика 23.10.2026)
===========================================
Раньше весь чат был ОДНИМ `tk.Text`, а реплики различались цветом текста и
линиями. Облачков в `tk.Text` быть не может: у него нет скруглённых углов,
фона на абзац с отступами и «хвостика». Поэтому чат переписан на список
виджетов:

    ChatView (карточка чата)
      └ tk.Canvas + CTkScrollbar                ← прокрутка
          └ list_frame                          ← все реплики
              └ row (на всю ширину)
                  └ bubble (CTkFrame, скруглённый)
                      ├ header: имя · время · 🔊 (повтор)
                      └ tk.Text: сам текст реплики (+ картинки-эмодзи)

Реплика преподавателя — СЛЕВА (акцентный фон), ученика — СПРАВА (циановый),
плюс маленький треугольник-«хвостик» у нижнего угла облачка.

ПОЧЕМУ ТЕКСТ РЕПЛИКИ — `tk.Text`, А НЕ `tk.Label`
-------------------------------------------------
В сообщениях есть эмодзи, а Tk рисует их одним тоном. Проект подменяет их
картинками (`ui/emoji_render.py`), а картинку внутрь `tk.Label` между буквами
не вставить — только в `tk.Text` (`image_create`). Поэтому текст живёт в
`tk.Text`, но:
  * `wrap="none"` — перенос делает НАШ код (`_wrap_parts`) по метрикам
    шрифта, поэтому облачко обтягивает текст, а не тянется на всю ширину;
  * ширина и высота виджета выставляются в символах/строках по факту;
  * при изменении ширины окна все реплики раскладываются заново.

ЧЕГО БОЛЬШЕ НЕТ (сознательно)
-----------------------------
* Обтекания робота: робот теперь стоит ПОД чатом отдельным блоком
  (`config.ROBOT_IN_CHAT = False`), поэтому правый отступ реплик не нужен.
  Вместе с ним ушла и «прыгающая» разметка при прокрутке (см. PROJECT_STATE
  §12): облачко — отдельный виджет, его ширина считается один раз.
* Выделения текста сразу через несколько реплик: каждая реплика — свой
  `tk.Text`. Внутри одной реплики выделение работает как обычно.
"""

import math
import re
import tkinter as tk
import tkinter.font as tkfont
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

# Отступы полосы прокрутки от правого края области чата.
SCROLL_PAD_X = 8
SCROLL_PAD_Y = 12
SCROLLBAR_WIDTH = 12   # было 6 px — ученик её просто не находил глазами

# Кнопка «прослушать повторно» (появляется рядом с именем преподавателя
# ПОСЛЕ того, как реплика впервые озвучена до конца).
REPLAY_ICON = "\U0001F50A"          # 🔊 динамик
REPLAY_TOOLTIP = "Прослушать повторно"

# --- геометрия облачков ---
BUBBLE_RADIUS = 14     # скругление облачка
BUBBLE_PADX = 12       # внутренние отступы облачка (текст от края)
BUBBLE_PADY = 8
ROW_PADY = 3           # воздух между репликами
SIDE_PAD = 10          # отступ облачка от края области чата
TAIL_W, TAIL_H = 9, 12  # «хвостик» облачка (треугольник)
# Облачко занимает не больше этой доли ширины чата: так видно, кто говорит,
# и длинные реплики не растягиваются на весь экран.
BUBBLE_MAX_FRAC = 0.66
BUBBLE_MIN_PX = 170    # уже этого текст не переносим (иначе по букве в строке)


class _Message:
    """Одна реплика: всё, что нужно, чтобы её обновить или перекрасить."""

    __slots__ = ("mark", "sender", "text", "is_user", "row", "bubble",
                 "header", "name_lbl", "stamp_lbl", "body", "tail", "replay")

    def __init__(self, mark, sender, text, is_user):
        self.mark = mark
        self.sender = sender
        self.text = text
        self.is_user = is_user
        self.row = None
        self.bubble = None
        self.header = None
        self.name_lbl = None
        self.stamp_lbl = None
        self.body = None
        self.tail = None
        self.replay = None


class ChatView(ctk.CTkFrame):
    def __init__(self, parent, palette, greeting=None, corner_radius=None,
                 on_replay=None):
        super().__init__(parent, fg_color=palette["chat_bg"],
                         corner_radius=corner_radius or theme.R["card"],
                         border_width=0,
                         height=140)   # запрос «минимум», растёт за счёт expand
        self.palette = palette
        self.on_replay = on_replay    # callback(text) — озвучить реплику повторно

        self._messages = {}           # mark → _Message
        self._order = []              # метки в порядке появления
        self._seq = 0
        self._wrap_px = 0             # ширина, под которую разложены реплики
        self._replay_icon = None      # держим ссылку на PhotoImage (иначе пропадёт)
        self._fonts = {}              # (family, size) → tkfont.Font
        self._relayout_job = None

        # --- прокрутка: холст + внутренний фрейм с репликами ---
        self.canvas = tk.Canvas(self, bg=palette["chat_bg"],
                                highlightthickness=0, bd=0, height=6)
        self.scrollbar = ctk.CTkScrollbar(
            self, command=self.canvas.yview,
            width=SCROLLBAR_WIDTH, corner_radius=SCROLLBAR_WIDTH // 2,
            fg_color="transparent",
            button_color=palette["muted"],
            button_hover_color=palette["btn_hover"],
        )
        self.scrollbar.pack(side="right", fill="y", padx=(0, SCROLL_PAD_X),
                            pady=SCROLL_PAD_Y)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # реплики живут внутри холста отдельным фреймом
        self.list_frame = ctk.CTkFrame(self.canvas, fg_color=palette["chat_bg"],
                                       corner_radius=0)
        self._window = self.canvas.create_window((0, 0), window=self.list_frame,
                                                 anchor="nw")
        self.list_frame.bind("<Configure>", self._on_list_configure, add="+")
        self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")
        # колесо мыши над чатом (проверяем, что курсор действительно над нами).
        # ВАЖНО: у CTk-виджетов bind_all ЗАПРЕЩЁН (customtkinter специально
        # бросает AttributeError), поэтому зовём реализацию tk напрямую.
        tk.Misc.bind_all(self, "<MouseWheel>", self._on_wheel, add="+")

        # --- цветные эмодзи ---
        self._emoji = emoji_render.EmojiImages(size=self._emoji_size(),
                                               master=self.canvas)
        if not emoji_render.available():
            print("ℹ️ Цветные эмодзи недоступны (нет Pillow или эмодзи-шрифта) — "
                  "в чате будут обычные символы")

        if greeting:
            sender, text = greeting
            self.add_message(sender, text, stamp=None)

    # =====================================================
    # Публичный API (его зовут ui/app.py и тесты)
    # =====================================================
    def add_message(self, sender, text, stamp=None):
        """Добавить реплику. Возвращает метку (только для реплик преподавателя).

        Метка нужна, чтобы потом включить кнопку «прослушать повторно»
        (`enable_replay`) или заменить текст (`update_message`). Для реплик
        ученика возвращается None — как и раньше.
        """
        sender = str(sender or "")
        text = str(text or "")
        is_user = sender in USER_SENDERS

        self._seq += 1
        mark = "msg_%d" % self._seq
        msg = _Message(mark, sender, text, is_user)
        self._messages[mark] = msg
        self._order.append(mark)

        if self._wrap_px <= 0:
            self._wrap_px = self._content_width()
        self._build_bubble(msg, stamp=stamp)
        self._scroll_to_bottom()
        return None if is_user else mark

    def update_message(self, mark, text, body_tag="body"):
        """Заменить текст УЖЕ показанной реплики, не добавляя новую.

        Нужно, когда данные изменились, а второй реплики быть не должно:
        например, после теста уровня строка «уровень пока не определён» в
        приветствии заменяется на «твой уровень: A2».
        """
        msg = self._messages.get(mark)
        if msg is None or msg.body is None:
            return False
        msg.text = str(text or "")
        self._fill_body(msg)
        self._scroll_to_bottom()
        return True

    def enable_replay(self, mark):
        """Показать кнопку «прослушать повторно» у реплики (ровно одну).

        Вызывается ПОСЛЕ того, как реплика впервые озвучена до конца.
        Неизвестная метка, реплика ученика и повторный вызов — тихо ничего
        не делают.
        """
        msg = self._messages.get(mark)
        if msg is None or msg.is_user or msg.header is None:
            return False
        if msg.replay is not None:
            return False
        widget = self._make_replay_button(msg)
        if widget is None:
            return False
        widget.pack(side="left", padx=(6, 0))
        msg.replay = widget
        return True

    def clear(self):
        """Стереть чат: удалить все реплики и картинки-эмодзи."""
        for msg in self._messages.values():
            self._destroy_message(msg)
        self._messages.clear()
        self._order = []
        self._emoji.clear()
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        self.canvas.yview_moveto(0.0)

    def get_text(self):
        """Весь текст чата: имя отправителя и текст каждой реплики.

        Эмодзи возвращаются СВОИМИ символами (они хранятся вместе с репликой),
        поэтому «сырой» текст совпадает с тем, что отправляла программа.
        """
        out = []
        for mark in self._order:
            msg = self._messages.get(mark)
            if msg is None:
                continue
            out.append("%s\n%s\n" % (msg.sender, msg.text))
        return "\n".join(out)

    def message_text(self, mark):
        """Текст одной реплики (без имени) — удобно тестам и повтору."""
        msg = self._messages.get(mark)
        return msg.text if msg is not None else ""

    # =====================================================
    # Сборка облачка
    # =====================================================
    def _build_bubble(self, msg, stamp=None):
        """Создать ряд, облачко, шапку и текст реплики."""
        p = self.palette
        bg = self._bubble_bg(msg.is_user)

        msg.row = ctk.CTkFrame(self.list_frame, fg_color=p["chat_bg"],
                               corner_radius=0)
        msg.row.pack(fill="x", padx=SIDE_PAD, pady=(ROW_PADY, ROW_PADY))
        # реплики преподавателя слева, ученика справа


        # «хвостик»: треугольник в цвет облачка. Рисуем его ПЕРВЫМ/ПОСЛЕДНИМ
        # по стороне, чтобы он примыкал к нижнему углу облачка.
        msg.tail = tk.Canvas(msg.row, width=TAIL_W, height=TAIL_H, bd=0,
                             highlightthickness=0, bg=p["chat_bg"])
        self._draw_tail(msg.tail, msg.is_user, bg)

        msg.bubble = ctk.CTkFrame(msg.row, fg_color=bg, corner_radius=BUBBLE_RADIUS,
                                  border_width=0)
        # ВАЖНО: pack(side="right") отдаёт место ПЕРВОМУ упакованному, поэтому
        # у реплик ученика хвостик пакуется РАНЬШЕ облачка (он правее), а у
        # реплик преподавателя — позже (он левее). Иначе хвостик оказывался
        # с «чужой» стороны.
        if msg.is_user:
            msg.tail.pack(side="right", anchor="s", padx=(6, 0))
            msg.bubble.pack(side="right", anchor="s")
        else:
            msg.bubble.pack(side="left", anchor="s")
            msg.tail.pack(side="left", anchor="s", padx=(6, 0))

        inner = ctk.CTkFrame(msg.bubble, fg_color=bg, corner_radius=0)
        inner.pack(fill="both", expand=True, padx=BUBBLE_PADX, pady=BUBBLE_PADY)

        # ---- шапка: имя · время · 🔊 ----
        msg.header = ctk.CTkFrame(inner, fg_color=bg, corner_radius=0)
        msg.header.pack(fill="x")
        msg.name_lbl = tk.Label(
            msg.header, text=msg.sender, bd=0, highlightthickness=0, bg=bg,
            fg=p["cyan"] if msg.is_user else p["accent"],
            font=theme.FONT_HEAD, anchor="w")
        msg.name_lbl.pack(side="left")
        if stamp:
            msg.stamp_lbl = tk.Label(
                msg.header, text="%s %s" % (DOT, stamp), bd=0,
                highlightthickness=0, bg=bg, fg=p["muted"],
                font=theme.FONT_HEAD, anchor="w")
            msg.stamp_lbl.pack(side="left", padx=(4, 0))

        # ---- сам текст ----
        msg.body = tk.Text(
            inner, wrap="none", bd=0, highlightthickness=0, bg=bg,
            fg=p["text_strong"] if msg.is_user else p["text"],
            font=theme.FONT_BODY, padx=0, pady=2, cursor="arrow",
            width=10, height=1, spacing1=0, spacing3=0,
            selectbackground=p["accent_soft"],
            selectforeground=p["text_strong"],
        )
        msg.body.pack(fill="x")
        self._fill_body(msg)

    def _fill_body(self, msg):
        """Разложить текст реплики по строкам и вставить в её облачко.

        Перенос считаем САМИ (по метрикам шрифта): у `tk.Text` ширина задаётся
        в символах, и при обычном `wrap="word"` облачко выходило бы либо уже
        текста, либо заметно шире (пустое место справа).
        """
        body = msg.body
        if body is None:
            return
        bg = self._bubble_bg(msg.is_user)
        max_px = self._bubble_max_px()
        font = self._font(theme.FONT_BODY)
        emoji_px = self._emoji.size

        parts = emoji_render.split(msg.text) if msg.text else []
        lines = self._wrap_parts(parts, max_px, font, emoji_px)
        widths = [sum(w for _k, _c, w in line) for line in lines] or [0]
        char0 = max(1.0, font.measure("0"))
        # +1 символ и 6 px запаса: ширина tk.Text задаётся в СИМВОЛАХ, и
        # округление вниз обрезало бы конец строки (wrap="none" не переносит).
        width = max(4, int(math.ceil((max(widths) + 6) / char0)) + 1)

        body.configure(state="normal", bg=bg)
        body.delete("1.0", "end")
        for index, line in enumerate(lines):
            if index:
                body.insert("end", "\n")
            for kind, chunk, _w in line:
                if kind is True:
                    photo = self._emoji.photo(chunk, master=body)
                    if photo is None:
                        body.insert("end", chunk)
                    else:
                        body.image_create("end", image=photo,
                                          align=emoji_render.ALIGN,
                                          padx=EMOJI_PAD)
                else:
                    body.insert("end", chunk)
        body.configure(width=width, height=max(1, len(lines)))
        body.configure(state="disabled")

    def _wrap_parts(self, parts, max_px, font, emoji_px):
        """Разбить реплику на строки по ширине max_px.

        Возвращает список строк, в каждой — куски (эмодзи?, текст, ширина).
        Эмодзи — неделимый кусок (он рисуется картинкой), текст режется по
        словам; слишком длинное слово режется по буквам, иначе вылезло бы
        за облачко.
        """
        tokens = []          # (kind, chunk, width): kind True/False/"nl"
        for is_emoji, chunk in parts:
            if is_emoji:
                tokens.append((True, chunk, emoji_px + 2 * EMOJI_PAD))
                continue
            for piece in re.split(r"(\n)", chunk):
                if piece == "\n":
                    tokens.append(("nl", "", 0.0))
                    continue
                for word in re.findall(r"\S+\s*|\s+", piece):
                    width = float(font.measure(word))
                    if width > max_px and len(word.strip()) > 1:
                        # длинное слово («supercalifragilistic») режем по буквам
                        for char in word:
                            tokens.append((False, char, float(font.measure(char))))
                        continue
                    tokens.append((False, word, width))

        lines, current, current_w = [], [], 0.0
        for kind, chunk, width in tokens:
            if kind == "nl":
                lines.append(current)
                current, current_w = [], 0.0
                continue
            if current and current_w + width > max_px and chunk.strip():
                lines.append(current)
                current, current_w = [], 0.0
            current.append((kind, chunk, width))
            current_w += width
        lines.append(current)
        return lines

    def _destroy_message(self, msg):
        """Убрать виджеты реплики из окна."""
        for widget in (msg.row,):
            if widget is not None:
                try:
                    widget.destroy()
                except Exception:
                    pass
        msg.row = msg.bubble = msg.header = None
        msg.name_lbl = msg.stamp_lbl = msg.body = msg.tail = msg.replay = None

    # =====================================================
    # Кнопка «прослушать повторно»
    # =====================================================
    def _make_replay_button(self, msg):
        """Небольшая иконка-динамик с подсказкой; клик — повторная озвучка."""
        p = self.palette
        try:
            label = tk.Label(msg.header, bd=0, highlightthickness=0,
                             bg=self._bubble_bg(msg.is_user), cursor="hand2")
        except Exception:
            return None
        icon = self._ensure_replay_icon(msg.is_user)
        if icon is not None:
            label.configure(image=icon)
        else:
            label.configure(text=REPLAY_ICON, fg=p["accent"], font=theme.FONT_HEAD)
        if _tooltip is not None:
            _tooltip.ToolTip(label, REPLAY_TOOLTIP, p)
        label.bind("<Button-1>", lambda _e, m=msg.mark: self._replay_clicked(m))
        return label

    def _ensure_replay_icon(self, is_user=False):
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
            colour = self.palette["cyan"] if is_user else self.palette["accent"]
            rgb = emoji_render.hex_to_rgb(colour)
            ink = emoji_render.render_mono(REPLAY_ICON, self._icon_size(),
                                           color=rgb + (255,))
            if ink is None:
                return None
            self._replay_icon = ImageTk.PhotoImage(ink, master=self.canvas)
        except Exception as exc:
            print("⚠️ Иконка прослушивания не нарисовалась: %s" % exc)
            self._replay_icon = None
        return self._replay_icon

    def _replay_clicked(self, mark):
        """Клик по кнопке: озвучить реплику повторно."""
        text = self.message_text(mark)
        if text and self.on_replay is not None:
            try:
                self.on_replay(text)
            except Exception as exc:
                print("⚠️ Повторное прослушивание не удалось: %s" % exc)

    # =====================================================
    # Прокрутка и раскладка
    # =====================================================
    def _on_list_configure(self, _event=None):
        """Содержимое выросло — обновить область прокрутки."""
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    def _on_canvas_configure(self, event=None):
        """Ширина чата изменилась: растянуть реплики и (если надо) разложить.

        Пересчёт переносов нужен только при РЕАЛЬНОМ изменении ширины (окна
        тянут мышью), а не на каждый кадр: между замерами меньше 8 px
        ничего не меняется.
        """
        width = event.width if event is not None else self.canvas.winfo_width()
        try:
            self.canvas.itemconfigure(self._window, width=width)
        except Exception:
            pass
        content = max(BUBBLE_MIN_PX, width - 2 * SIDE_PAD)
        if abs(content - self._wrap_px) < 8:
            return
        self._wrap_px = content
        if not self._messages:
            return
        if self._relayout_job is not None:
            try:
                self.after_cancel(self._relayout_job)
            except Exception:
                pass
        self._relayout_job = self.after(140, self._relayout)

    def _relayout(self):
        """Пересчитать переносы во всех репликах (после изменения ширины)."""
        self._relayout_job = None
        for mark in list(self._order):
            msg = self._messages.get(mark)
            if msg is not None and msg.body is not None:
                self._fill_body(msg)

    def _on_wheel(self, event=None):
        """Колесо мыши: прокручиваем чат, только если курсор над чатом."""
        if event is None:
            return None
        widget = getattr(event, "widget", None)
        if widget is None or not self._is_inside(widget):
            return None
        try:
            delta = int(-1 * (event.delta / 120)) if event.delta else 0
            if delta == 0:
                delta = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(delta, "units")
        except Exception:
            pass
        return "break"

    def _is_inside(self, widget):
        """Принадлежит ли виджет этому чату (для обработчика колеса)."""
        try:
            while widget is not None:
                if widget is self:
                    return True
                widget = widget.master
        except Exception:
            return False
        return False

    def _scroll_to_bottom(self):
        """Прокрутить чат вниз (новая реплика должна быть видна)."""
        try:
            self.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _content_width(self):
        """Ширина, доступная репликам (без полосы прокрутки и отступов)."""
        width = self.canvas.winfo_width()
        if width <= 1:
            width = max(200, self.winfo_width() - SCROLLBAR_WIDTH - SCROLL_PAD_X)
        return max(BUBBLE_MIN_PX, width - 2 * SIDE_PAD)

    def _bubble_max_px(self):
        """Предельная ширина текста внутри облачка."""
        content = self._wrap_px or self._content_width()
        return max(BUBBLE_MIN_PX, int(content * BUBBLE_MAX_FRAC))

    # =====================================================
    # Оформление
    # =====================================================
    def _bubble_bg(self, is_user):
        """Цвет облачка. Ключи живут в theme.py (единственный источник цветов)."""
        key = "bubble_user" if is_user else "bubble_teacher"
        return self.palette.get(key, self.palette["surface"])

    def _draw_tail(self, canvas, is_user, colour):
        """Нарисовать «хвостик» облачка (треугольник в его цвете)."""
        try:
            canvas.delete("all")
            if is_user:
                points = (0, 0, TAIL_W, TAIL_H, 0, TAIL_H)
            else:
                points = (TAIL_W, 0, 0, TAIL_H, TAIL_W, TAIL_H)
            canvas.create_polygon(*points, fill=colour, outline=colour)
        except Exception:
            pass

    def _font(self, spec):
        """tkfont.Font по описанию шрифта (кешируем: measure зовётся часто)."""
        key = tuple(spec)
        font = self._fonts.get(key)
        if font is None:
            font = tkfont.Font(root=self, font=spec)
            self._fonts[key] = font
        return font

    def _icon_size(self):
        """Размер иконки динамика — чуть больше шрифта имени (в пикселях)."""
        try:
            font = self._font(theme.FONT_HEAD)
            points = abs(font.actual("size")) + 3
            scaling = float(self.tk.call("tk", "scaling"))
            return emoji_render.size_from_font(points, scaling)
        except Exception:
            return emoji_render.DEFAULT_PX

    def _emoji_size(self):
        """Размер картинок-эмодзи под шрифт чата (в пикселях, не «на глаз»)."""
        try:
            font = tkfont.Font(root=self, font=theme.FONT_BODY)
            points = abs(font.actual("size"))
            scaling = float(self.tk.call("tk", "scaling"))
            return emoji_render.size_from_font(points, scaling)
        except Exception:
            return emoji_render.DEFAULT_PX

    def apply_theme(self, palette):
        """Перекрасить чат под новую палитру (тёмная ↔ светлая)."""
        self.palette = palette
        self.configure(fg_color=palette["chat_bg"])
        self.canvas.configure(bg=palette["chat_bg"])
        self.list_frame.configure(fg_color=palette["chat_bg"])
        self.scrollbar.configure(button_color=palette["muted"],
                                 button_hover_color=palette["btn_hover"])
        self._replay_icon = None
        for mark in self._order:
            msg = self._messages.get(mark)
            if msg is None or msg.bubble is None:
                continue
            bg = self._bubble_bg(msg.is_user)
            try:
                msg.row.configure(fg_color=palette["chat_bg"])
                msg.bubble.configure(fg_color=bg)
                msg.header.configure(fg_color=bg)
                msg.name_lbl.configure(bg=bg,
                                       fg=palette["cyan"] if msg.is_user
                                       else palette["accent"])
                if msg.stamp_lbl is not None:
                    msg.stamp_lbl.configure(bg=bg, fg=palette["muted"])
                msg.tail.configure(bg=palette["chat_bg"])
                self._draw_tail(msg.tail, msg.is_user, bg)
                msg.body.configure(
                    bg=bg,
                    fg=palette["text_strong"] if msg.is_user else palette["text"],
                    selectbackground=palette["accent_soft"],
                    selectforeground=palette["text_strong"])
                if msg.replay is not None:
                    icon = self._ensure_replay_icon(msg.is_user)
                    msg.replay.configure(
                        **({"image": icon, "text": ""} if icon is not None
                           else {"text": REPLAY_ICON, "fg": palette["accent"]}),
                        bg=bg)
            except Exception as exc:
                print("⚠️ Реплика не перекрасилась: %s" % exc)
        # картинки-эмодзи перерисовывать не нужно: фон прозрачный
