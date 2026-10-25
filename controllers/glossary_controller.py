"""CONTROLLERS/GLOSSARY_CONTROLLER.PY — разбор реплик в паузах.

Правило ученика (25.10.2026): приоритет — ответ учителя и озвучка.
Перевод-подсказка может подождать: ученик перечитывает реплику, слушает её
и только потом наводит курсор на слово.

Поэтому:
  * модель зовётся из ФОНОВОГО потока и только когда приложение свободно
    (`is_idle()` → True: учитель не думает, озвучка не идёт);
  * в очереди не больше `max_pending` реплик: новые вытесняют старые;
  * наведение курсора сюда не попадает вообще — оно читает готовый словарь.

Модуль без Tk: его легко проверять тестом.
"""

from __future__ import annotations

import logging
import queue
import threading

_log = logging.getLogger(__name__)


class GlossaryController:
    """Очередь «разбери реплику, когда освободимся»."""

    def __init__(self, gloss, is_idle=None, max_pending: int = 3,
                 poll: float = 0.15):
        self.gloss = gloss
        self.is_idle = is_idle or (lambda: True)
        self.max_pending = max(1, int(max_pending))
        self.poll = max(0.01, float(poll))
        self.done = 0            # сколько реплик разобрано
        self.skipped = 0         # сколько вытеснено из очереди
        self._queue = queue.Queue()
        self._stopped = threading.Event()
        self._thread = None

    # ---------- постановка ----------
    def request(self, text: str) -> bool:
        """Поставить реплику в очередь. Пустую/уже разобранную не берём."""
        phrase = str(text or "").strip()
        if not phrase or self._stopped.is_set():
            return False
        try:
            if self.gloss is not None and self.gloss.known(phrase):
                return False
        except Exception:                        # noqa: BLE001
            pass
        if self._queue.qsize() >= self.max_pending:
            try:
                self._queue.get_nowait()         # вытесняем самую старую
                self.skipped += 1
            except queue.Empty:
                pass
        self._queue.put(phrase)
        self._ensure_thread()
        return True

    def _ensure_thread(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="glossary")
        self._thread.start()

    # ---------- работа ----------
    def _loop(self):
        while not self._stopped.is_set():
            # ВАЖНО: сначала пауза, потом забираем из очереди. Иначе фоновый
            # поток «съедал» реплики ещё во время ответа учителя, и очередь
            # никогда не переполнялась (поймал тест).
            if not self._wait_idle():
                return                        # остановили
            try:
                text = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                ok, _info = self.gloss.prime(text)
                if ok:
                    self.done += 1
            except Exception as exc:              # noqa: BLE001
                _log.warning("Глоссарий: разбор не удался (%s)", exc)

    def _wait_idle(self) -> bool:
        """Ждём паузу в приложении. False — если нас остановили."""
        while not self._stopped.is_set():
            try:
                if self.is_idle():
                    return True
            except Exception:                     # noqa: BLE001
                return True                       # сломанный признак не блокирует
            self._stopped.wait(self.poll)
        return False

    def stop(self, timeout: float = 2.0):
        """Остановить фон (выход из приложения)."""
        self._stopped.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
