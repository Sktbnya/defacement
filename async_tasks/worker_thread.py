# async_tasks/worker_thread.py
import asyncio
import logging
from typing import List
from PyQt5.QtCore import QObject, pyqtSignal
from async_tasks.worker import process_all_sites

class Worker(QObject):
    update_signal = pyqtSignal(list)  # Список результатов с ключом "url"
    finished_signal = pyqtSignal()

    def __init__(self, urls: List[str], interval: int):
        super().__init__()
        self.urls = urls
        self.interval = interval
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._monitoring_loop(loop))
        loop.close()
        self.finished_signal.emit()

    async def _monitoring_loop(self, loop: asyncio.AbstractEventLoop):
        while self._running:
            try:
                results = await process_all_sites(self.urls, self.interval)
                processed_results = []
                for url, res in zip(self.urls, results):
                    res["url"] = url
                    processed_results.append(res)
                self.update_signal.emit(processed_results)
            except Exception as e:
                logging.error(f"Ошибка в фоновой задаче: {e}")
            await asyncio.sleep(self.interval)
