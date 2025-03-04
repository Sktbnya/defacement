# async_tasks/scheduler.py
import asyncio
import logging
from typing import Callable, Awaitable

async def schedule_task(task: Callable[[], Awaitable[None]], interval: int) -> None:
    while True:
        try:
            await task()
        except Exception as e:
            logging.error(f"Ошибка выполнения задачи: {e}")
        await asyncio.sleep(interval)
