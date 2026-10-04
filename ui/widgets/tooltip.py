# -*- coding: utf-8 -*-
"""ui.widgets.tooltip — всплывающие подсказки для кнопок.

Кнопки-иконки (🎯 ✏️ 🗑️) неочевидны без подписи, поэтому при наведении
мыши показываем текст о назначении. Tk сам подсказок не умеет — окно
делаем сами: небольшой Toplevel без рамки, который появляется рядом с
виджетом через небольшую задержку и исчезает, когда курсор ушёл.

Подписки на <Enter>/<Leave> вешаем на сам виджет, его canvas и всех детей
(у CTk-кнопок события приходят на ВНУТРЕННИЙ canvas, а не на обёртку),
поэтому ToolTip можно передавать как «держатель», так и саму кнопку.
"""

import tkinter as tk

import theme


class ToolTip:
    def __init__(self, widget, text, palette=None, delay=450, offset=(10, 18)):
        self.widget = widget
        self.text = str(text or "")
        self.palette = palette or theme.DARK
        self.delay = delay
        self.offset = offset
        self._after_id = None
        self._tip = None
        for target in self._targets(widget):
            try:
                target.bind("<Enter>", self._on_enter, add="+")
                target.bind("<Leave>", self._on_leave, add="+")
                target.bind("<ButtonPress>", self._on_leave, add="+")
            except Exception:
                pass

    # -----------------------------------------------------
    @classmethod
    def _targets(cls, widget):
        """Виджет + его canvas + все вложенные виджеты."""
        out = []
        stack = [widget]
        while stack:
            node = stack.pop()
            if node is None:
                continue
            out.append(node)
            canvas = getattr(node, "_canvas", None)
            if canvas is not None and canvas not in out:
                out.append(canvas)
            try:
                stack.extend(node.winfo_children())
            except Exception:
                pass
        return out

    def _on_enter(self, _event=None):
        self._cancel()
        try:
            self._after_id = self.widget.after(self.delay, self._show)
        except Exception:
            self._after_id = None

    def _on_leave(self, _event=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    # -----------------------------------------------------
    def _show(self):
        self._after_id = None
        if self._tip is not None or not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
        except Exception:
            return
        p = self.palette
        try:
            tip = tk.Toplevel(self.widget)
        except Exception:
            return
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except Exception:
            pass
        tip.configure(bg=p["border"])
        tk.Label(tip, text=self.text, bg=p["btn"], fg=p["text"],
                 font=theme.FONT_SMALL, padx=9, pady=5,
                 justify="left", borderwidth=0).pack(padx=1, pady=1)
        tip.update_idletasks()
        x = self.widget.winfo_rootx() + self.offset[0]
        y = self.widget.winfo_rooty() + self.offset[1]
        # не даём подсказке уехать за правый край экрана
        screen_w = tip.winfo_screenwidth()
        if x + tip.winfo_reqwidth() > screen_w - 8:
            x = max(8, screen_w - tip.winfo_reqwidth() - 8)
        tip.wm_geometry("+%d+%d" % (x, y))
        self._tip = tip

    def _hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
