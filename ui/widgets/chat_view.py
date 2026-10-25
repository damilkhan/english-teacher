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
# Воздух над первой репликой и под последней: облачко не должно липнуть к
# краю поля чата (замечание ученика 23.10.2026).
TOP_PAD = 10
BOTTOM_PAD = 8
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
                 on_replay=None, on_hover_word=None):
        super().__init__(parent, fg_color=palette["chat_bg"],
                         corner_radius=corner_radius or theme.R["card"],
                         border_width=0,
                         height=140)   # запрос «минимум», растёт за счёт expand
        self.palette = palette
        self.on_replay = on_replay    # callback(text) — озвучить реплику повторно
        # callback(текст_реплики, позиция) → {"en","ru",…} | None.
        # Подсказки есть и в репликах УЧЕНИКА (решение 25.10.2026): на письме
        # «сказал сам — значит знает» не работает, он тоже хочет проверить.
        self.on_hover_word = on_hover_word
        self._gloss_tip = None    # окно-подсказка (Toplevel без рамки)
        self._gloss_key = None    # что показано — чтобы не мерцало
        self._gloss_body = None   # облачко, где сейчас подсвечено слово

        self._messages = {}           # mark → _Message
        self._order = []              # метки в порядке появления
        self._seq = 0
        self._wrap_px = 0             # ширина, под которую разложены реплики
        self._replay_icon = None      # держим ссылку на PhotoImage (иначе пропадёт)
        self._fonts = {}              # (family, size) → tkfont.Font
        self._relayout_job = None
        self._syncing = False         # защита от рекурсии в <Configure>

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
        # Воздух сверху и снизу — отдельные пустые полоски. Держим их всегда
        # (clear() их не трогает), иначе первая реплика липнет к краю, а
        # последняя — к полосе прокрутки.
        self._top_spacer = ctk.CTkFrame(self.list_frame, fg_color=palette["chat_bg"],
                                        corner_radius=0, height=TOP_PAD)
        self._top_spacer.pack(side="top", fill="x")
        self._top_spacer.pack_propagate(False)
        self._bottom_spacer = ctk.CTkFrame(self.list_frame, fg_color=palette["chat_bg"],
                                           corner_radius=0, height=BOTTOM_PAD)
        self._bottom_spacer.pack(side="bottom", fill="x")
        self._bottom_spacer.pack_propagate(False)

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
        self._gloss_hide()
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
        # справа — преподаватель, слева — ученик
        on_right = not msg.is_user

        msg.row = ctk.CTkFrame(self.list_frame, fg_color=p["chat_bg"],
                               corner_radius=0)
        # before=_bottom_spacer: воздух снизу всегда остаётся под репликами
        msg.row.pack(fill="x", padx=SIDE_PAD, pady=(ROW_PADY, ROW_PADY),
                     before=self._bottom_spacer)
        # реплики преподавателя слева, ученика справа


        # «хвостик»: треугольник в цвет облачка. Рисуем его ПЕРВЫМ/ПОСЛЕДНИМ
        # по стороне, чтобы он примыкал к нижнему углу облачка.
        msg.tail = tk.Canvas(msg.row, width=TAIL_W, height=TAIL_H, bd=0,
                             highlightthickness=0, bg=p["chat_bg"])
        self._draw_tail(msg.tail, on_right, bg)

        msg.bubble = ctk.CTkFrame(msg.row, fg_color=bg, corner_radius=BUBBLE_RADIUS,
                                  border_width=0)
        # СТОРОНЫ (решение ученика 23.10.2026): реплика УЧЕНИКА — слева,
        # преподавателя — справа.
        # ВАЖНО: pack отдаёт место ПЕРВОМУ упакованному, поэтому «хвостик»
        # пакуется РАНЬШЕ облачка с той же стороны — тогда он оказывается с
        # НАРУЖНОЙ стороны (у левого облачка слева, у правого справа).
        side = "right" if on_right else "left"
        # padx в Tk — (слева, справа): у правого облачка воздух слева от
        # хвостика, у левого — справа от него
        gap = (6, 0) if on_right else (0, 6)
        msg.tail.pack(side=side, anchor="s", padx=gap)
        msg.bubble.pack(side=side, anchor="s")

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
        # Высота окна текста подгоняется по факту размещения: <Configure>
        # приходит, когда Tk уже знает настоящие высоты строк (у строк с
        # эмодзи они больше). Так обрезка снизу лечится сама и без таймеров.
        msg.body.bind("<Configure>",
                      lambda _e, b=msg.body: self._fit_body_height(b), add="+")
        # подсказки-переводы — во ВСЕХ облачках, у ученика тоже
        if self.on_hover_word is not None:
            self._bind_hover(msg.body)
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
        # Карта «смещение в ЧИСТОМ тексте → счётчик символов Tk». Нужна для
        # подсветки слова: картинка-эмодзи в индексах Tk занимает 1 символ, а
        # в get() не появляется вовсе (замерено 25.10.2026: «1.0 + 4c» → 1.4,
        # а get() короче на число эмодзи). Без карты выделение уезжает.
        offset_map = [(0, 0)]
        text_off = 0
        tk_off = 0
        for index, line in enumerate(lines):
            if index:
                body.insert("end", "\n")
                text_off += 1
                tk_off += 1
                offset_map.append((text_off, tk_off))
            for kind, chunk, _w in line:
                if kind is True:
                    photo = self._emoji.photo(chunk, master=body)
                    if photo is None:
                        body.insert("end", chunk)
                        text_off += len(chunk)
                    else:
                        body.image_create("end", image=photo,
                                          align=emoji_render.ALIGN,
                                          padx=EMOJI_PAD)
                    tk_off += 1
                    offset_map.append((text_off, tk_off))
                else:
                    body.insert("end", chunk)
                    text_off += len(chunk)
                    tk_off += len(chunk)
                    offset_map.append((text_off, tk_off))
        try:
            body._gloss_map = offset_map
        except Exception:
            pass
        body.configure(width=width, height=max(1, len(lines)))
        body.configure(state="disabled")
        try:
            body._fit_extra = 0        # новый текст — новый отсчёт подгонки
        except Exception:
            pass
        self._schedule_fit(body)

    # ---------------- подсказки-переводы по наведению (25.10.2026) --------------
    def _bind_hover(self, body):
        """Наведение на слово в облачке (любом — теперь и у ученика)."""
        body.bind("<Motion>", lambda e, b=body: self._gloss_motion(b, e), add="+")
        body.bind("<Leave>", lambda _e: self._gloss_hide(), add="+")
        body.bind("<ButtonPress>", lambda _e: self._gloss_hide(), add="+")

    def _gloss_motion(self, body, event):
        """Показать перевод слова под курсором. Модель здесь НЕ вызывается:

        всё уже лежит в словаре-кэше (см. glossary.py), поэтому ответ
        мгновенный.
        """
        try:
            index = body.index("@%d,%d" % (event.x, event.y))
            text = body.get("1.0", "end-1c")
            offset = len(body.get("1.0", index))
        except Exception:
            return
        try:
            hit = self.on_hover_word(text, offset)
        except Exception:
            hit = None
        if not hit:
            self._gloss_hide()
            return
        key = (hit.get("start"), hit.get("end"), hit.get("ru"))
        if key == self._gloss_key and self._gloss_tip is not None:
            return                       # та же фраза — окно не пересоздаём
        self._gloss_key = key
        self._gloss_show(hit, event.x_root, event.y_root, body=body)

    def _gloss_show(self, hit, x_root, y_root, body=None):
        """Окно-подсказка рядом с курсором: ТОЛЬКО русский перевод.

        Английское слово в окне больше не дублируется (решение 25.10.2026):
        вместо него слово подсвечивается прямо в облачке.
        """
        self._gloss_hide()
        p = self.palette
        try:
            tip = tk.Toplevel(self)
        except Exception:
            return
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except Exception:
            pass
        tip.configure(bg=p["border"])
        box = tk.Frame(tip, bg=p["btn"], bd=0)
        box.pack(padx=1, pady=1)
        tk.Label(box, text=str(hit.get("ru") or ""), bg=p["btn"], fg=p["text"],
                 font=theme.FONT_SMALL, padx=9, pady=5,
                 justify="left", anchor="w", bd=0).pack(fill="x")
        tip.update_idletasks()
        x = x_root + 12
        y = y_root + 18
        screen_w = tip.winfo_screenwidth()
        screen_h = tip.winfo_screenheight()
        if x + tip.winfo_reqwidth() > screen_w - 8:
            x = max(8, screen_w - tip.winfo_reqwidth() - 8)
        if y + tip.winfo_reqheight() > screen_h - 8:
            y = max(8, y_root - tip.winfo_reqheight() - 10)
        tip.wm_geometry("+%d+%d" % (x, y))
        self._gloss_tip = tip
        if body is not None:
            self._gloss_mark(body, hit)

    def _gloss_hide(self):
        self._gloss_key = None
        self._gloss_unmark()
        if self._gloss_tip is not None:
            try:
                self._gloss_tip.destroy()
            except Exception:
                pass
            self._gloss_tip = None

    def _text_index(self, body, offset):
        """Смещение в чистом тексте → индекс tk.Text (эмодзи считаются)."""
        offset = max(0, int(offset or 0))
        table = getattr(body, "_gloss_map", None) or [(0, 0)]
        text_off, tk_off = table[0]
        for t_off, k_off in table:
            if t_off <= offset:
                text_off, tk_off = t_off, k_off
            else:
                break
        try:
            return body.index("1.0 + %dc" % (tk_off + max(0, offset - text_off)))
        except Exception:
            return "1.0 + %dc" % offset

    def _gloss_mark(self, body, hit):
        """Подсветить переводимое слово/фразу в тексте облачка."""
        self._gloss_unmark()
        try:
            start = self._text_index(body, hit.get("start") or 0)
            end = self._text_index(body, hit.get("end") or start)
            body.tag_config("gloss", foreground=self.palette.get("warn", "#FBBF24"))
            body.tag_add("gloss", start, end)
        except Exception:
            return
        self._gloss_body = body

    def _gloss_unmark(self):
        """Снять подсветку (уход курсора, смена слова, прокрутка)."""
        body = getattr(self, "_gloss_body", None)
        self._gloss_body = None
        if body is None:
            return
        try:
            body.tag_remove("gloss", "1.0", "end")
        except Exception:
            pass
    def _schedule_fit(self, body):
        """Попросить подгонку высоты в следующем простое (виджет ещё не размещён)."""
        try:
            self.after_idle(lambda: self._fit_body_height(body))
        except Exception:
            pass

    def _fit_body_height(self, body, max_extra=4):
        """Подогнать высоту окна текста ПО ПИКСЕЛЯМ, а не по числу строк.

        ГРАБЛЯ (снимок ученика 23.10.2026): у строки с эмодзи высота больше
        обычной (`dlineinfo` даёт 21 px вместо 19 — картинка-эмодзи поднимает
        строку над базовой линией). `height` у tk.Text задаётся в СТРОКАХ и
        такого не учитывает: замер — тексту нужно 61 px, а окно 59 px, и
        нижние пиксели последней строки срезаны (в пиксельном шрифте это
        видно как «обрезанная вторая строка»).

        Вызывается из <Configure> самого окна текста: к этому моменту высоты
        строк настоящие. Если нужно больше — добавляем строки, Tk снова
        пришлёт <Configure>, и цикл сойдётся (защита `max_extra` — от
        бесконечной «раскачки»).
        """
        if getattr(body, "_fitting", False):
            return
        try:
            if body is None or not body.winfo_exists():
                return
            height = body.winfo_height()
            if height <= 1:
                return                 # ещё не размещён — <Configure> придёт сам
            # Меряем по ГЕОМЕТРИИ последней строки (dlineinfo), а не по
            # count(ypixels): до размещения Tk занижает высоты строк с эмодзи
            # (замер: 133 px против 147 px после размещения).
            # Сколько пикселей занимает текст (без учёта обрезки) и есть ли
            # 2 px запаса: у пиксельного шрифта нижние точки букв могут выходить
            # за «коробку» строки.
            need = body.count("1.0", "end", "ypixels")[0]
            line = int(round(float(body.winfo_reqheight())
                             / max(1.0, float(body.cget("height"))))) or 19
            if need + 2 <= height:
                body._fit_extra = 0
                # лишняя строка? убираем, но только если текст всё равно
                # помещается с запасом (иначе начнётся «раскачка»)
                if need + 2 + line <= height and float(body.cget("height")) > 1:
                    body._fitting = True
                    try:
                        body.configure(height=int(float(body.cget("height"))) - 1)
                    finally:
                        body._fitting = False
                return
            # строку отрезало (или её не видно вовсе) — добавляем строки
            extra = int(getattr(body, "_fit_extra", 0)) + 1
            if extra > max_extra:
                return
            body._fitting = True
            try:
                body._fit_extra = extra
                body.configure(height=int(float(body.cget("height"))) + 1)
            finally:
                body._fitting = False
        except Exception:
            pass

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
        """Содержимое изменилось — обновить область прокрутки.

        ГРАБЛЯ (найдена 23.10.2026 по снимку ученика): если область прокрутки
        КОРОЧЕ окна, вызов `yview_moveto(1.0)` даёт ОТРИЦАТЕЛЬНОЕ смещение —
        содержимое уезжает вниз, а сверху появляется пустота. Лечится тем, что
        окно холста делаем не ниже самого холста: тогда регион всегда >= окна.
        """
        self._sync_scrollregion()

    def _sync_scrollregion(self):
        """Обновить область прокрутки и, если содержимое короче окна, прижать вверх.

        ГРАБЛЯ: внутри вызывается update_idletasks(), а сам метод вызывается из
        обработчика <Configure> того же фрейма — без флага это бесконечная
        рекурсия (окно «зависает» на добавлении реплики).
        """
        if self._syncing:
            return
        self._syncing = True
        try:
            self.update_idletasks()
            height = self.list_frame.winfo_reqheight()
            canvas_h = max(1, self.canvas.winfo_height())
            # окно холста не ниже самого холста — иначе возможен «минус»
            self.canvas.itemconfigure(self._window, height=max(height, canvas_h))
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            first, _last = self.canvas.yview()
            if height <= canvas_h and first != 0.0:
                self.canvas.yview_moveto(0.0)      # содержимое помещается — сверху
        except Exception:
            pass
        finally:
            self._syncing = False

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
        self._gloss_hide()          # подсказка-перевод «уезжает» вместе с текстом
        if event is None:
            return None
        widget = getattr(event, "widget", None)
        if widget is None or not self._is_inside(widget):
            return None
        try:
            # Если всё содержимое помещается в окно — прокручивать нечего.
            # Без этой проверки колесо вверх уводило чат в «минус» (замер:
            # canvasy(0) = -652 px), и сверху появлялась пустота — ровно то,
            # что увидел ученик 23.10.2026.
            box = self.canvas.bbox("all")
            if box is None or box[3] <= self.canvas.winfo_height():
                return "break"
            delta = int(-1 * (event.delta / 120)) if event.delta else 0
            if delta == 0:
                delta = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(delta, "units")
            # Ось Y холста: canvasy(0) — координата содержимого у верхнего края.
            # НОРМА — ноль (начало) или положительное число (прокрутили вниз).
            # Отрицательное значение означает, что содержимое уехало ВНИЗ и
            # сверху пустота — только этот случай и лечим.
            if self.canvas.canvasy(0) < 0:
                self.canvas.yview_moveto(0.0)
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
        """Прокрутить чат вниз (новая реплика должна быть видна).

        Если содержимое КОРОЧЕ окна — прокручивать нечего, и `yview_moveto(1.0)`
        только сдвинуло бы реплики вниз (пустота сверху). Поэтому в этом случае
        прижимаем вид к началу.
        """
        try:
            self._sync_scrollregion()
            content_h = self.list_frame.winfo_reqheight()
            if content_h > max(1, self.canvas.winfo_height()):
                self.canvas.yview_moveto(1.0)
            else:
                self.canvas.yview_moveto(0.0)
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

    def _draw_tail(self, canvas, on_right, colour):
        """Нарисовать «хвостик» облачка (треугольник в его цвете).

        on_right — облачко стоит справа (реплика преподавателя): вертикальная
        сторона треугольника прижата к облачку, остриё смотрит вправо.
        """
        try:
            canvas.delete("all")
            if on_right:
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
        """Размер картинок-эмодзи под шрифт чата (в пикселях, не «на глаз»).

        ВАЖНО: не больше ASCENT шрифта. Картинка вставляется с align="baseline",
        и если она выше подъёма букв, строка становится выше обычной (замер:
        эмодзи 17 px при ascent 16 давали строку 21 px вместо 19). Тогда
        высота окна текста (она в СТРОКАХ) оказывается меньше содержимого, и
        низ последней строки обрезается — ровно баг со снимка 23.10.2026.
        При эмодзи <= ascent строка держится ровно linespace, и обрезки нет.
        """
        try:
            font = tkfont.Font(root=self, font=theme.FONT_BODY)
            points = abs(font.actual("size"))
            scaling = float(self.tk.call("tk", "scaling"))
            size = emoji_render.size_from_font(points, scaling)
            # ВАЖНО: подъём букв спрашиваем через metrics(), а НЕ actual():
            # у tkfont.Font.actual нет ключа "ascent" — вызов бросает
            # TclError, и код молча падал в DEFAULT_PX = 18 px. А 18 при
            # ascent 16 поднимало строку → низ последней строки обрезался
            # (ровно баг со снимка 23.10.2026).
            # -1: замер показал, что картинка РОВНО в ascent всё равно делает
            # строку на 1 px выше (16+3 = 19 при linespace 21 → 20), а лишний
            # пиксель на каждой строке с эмодзи и обрезает низ окна текста.
            ascent = int(font.metrics("ascent") or 0)
            if ascent > 1:
                size = min(size, ascent - 1)
            return max(emoji_render.MIN_PX, size)
        except Exception:
            return emoji_render.DEFAULT_PX

    def apply_theme(self, palette):
        """Перекрасить чат под новую палитру (тёмная ↔ светлая)."""
        self.palette = palette
        self.configure(fg_color=palette["chat_bg"])
        self.canvas.configure(bg=palette["chat_bg"])
        self.list_frame.configure(fg_color=palette["chat_bg"])
        for spacer in (self._top_spacer, self._bottom_spacer):
            try:
                spacer.configure(fg_color=palette["chat_bg"])
            except Exception:
                pass
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
                self._draw_tail(msg.tail, not msg.is_user, bg)
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
