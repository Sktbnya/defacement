# async_tasks/worker_thread.py
import asyncio
import logging
from typing import List
from PyQt5.QtCore import QObject, pyqtSignal
from async_tasks.worker import process_all_sites

class Worker(QObject):
    update_signal = pyqtSignal(list)  # Список результатов, каждый словарь должен содержать ключ "url"
    finished_signal = pyqtSignal()

    def __init__(self, urls: List[str], interval: int):
        """
        Инициализация Worker.
        :param urls: Список URL для мониторинга.
        :param interval: Интервал мониторинга в секундах.
        """
        super().__init__()
        self.urls = urls
        self.interval = interval
        self._running = True

    def stop(self):
        """Останавливает мониторинг."""
        self._running = False

    def run(self):
        """Запускает цикл мониторинга в новом event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._monitoring_loop(loop))
        loop.close()
        self.finished_signal.emit()

    async def _monitoring_loop(self, loop: asyncio.AbstractEventLoop):
        while self._running:
            try:
                results = await process_all_sites(self.urls, self.interval)
                # Если process_all_sites не добавляет ключ "url", добавим его здесь:
                processed_results = []
                for url, res in zip(self.urls, results):
                    res["url"] = url
                    processed_results.append(res)
                self.update_signal.emit(processed_results)
            except Exception as e:
                logging.error(f"Ошибка в фоновой задаче: {e}")
            await asyncio.sleep(self.interval)
