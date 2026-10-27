#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка синтаксиса Python после правки файла (хук Deep Copilot).

Запускается автоматически после write_file / str_replace_in_file / apply_patch.
Берёт ДВА источника:
  1) изменённые .py по `git status --porcelain`;
  2) любые .py, тронутые за последние RECENT_SEC секунд (ловятся и файлы,
     которые git игнорирует, например `_tmp_*.py`).
Печатает ТОЛЬКО проблемы: пусто = всё хорошо (хук молчит).
"""
import ast
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"models", "logs", "profiles", "__pycache__", ".deep-copilot",
             ".git", "node_modules", ".venv", "venv"}
RECENT_SEC = 120


def _skip(rel):
    parts = rel.replace("\\", "/").lower().split("/")
    return any(p in SKIP_DIRS for p in parts)


def changed_by_git():
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        ).stdout
    except OSError:
        return []
    files = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:              # переименование
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        if not path.endswith(".py") or _skip(path):
            continue
        files.append(path)
    return files


def recent_py():
    files, now = [], time.time()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            full = os.path.join(dirpath, name)
            try:
                if now - os.path.getmtime(full) > RECENT_SEC:
                    continue
            except OSError:
                continue
            files.append(os.path.relpath(full, ROOT).replace("\\", "/"))
    return files


def main():
    if hasattr(sys.stdout, "reconfigure"):
        # UTF-8 обязательно: расширение читает вывод как utf8,
        # иначе русский текст превращается в кракозябры.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    seen, problems = set(), []
    for rel in changed_by_git() + recent_py():
        if rel in seen:
            continue
        seen.add(rel)
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full):
            continue                      # файл удалён — это не ошибка
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
            ast.parse(src, filename=rel)
        except SyntaxError as exc:
            problems.append("%s:%s: %s" % (rel, exc.lineno, exc.msg))
        except Exception as exc:          # noqa: BLE001 — хук не должен падать
            problems.append("%s: %s" % (rel, exc))
    if problems:
        print("СИНТАКСИС СЛОМАН (правка не годится, исправь):")
        for p in problems:
            print("  " + p)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
