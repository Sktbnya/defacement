# monitor/utils.py
import asyncio
import logging
from typing import Any, Callable, TypeVar, Coroutine

T = TypeVar('T')

def retry_async(retries: int = 3, delay: float = 1.0, backoff: float = 2.0) -> Callable:
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        async def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logging.error(f"Ошибка в {func.__name__}: {e}. Попытка {attempt+1}/{retries}")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            raise Exception(f"Функция {func.__name__} не выполнилась после {retries} попыток.")
        return wrapper
    return decorator

CONFIG = {
    "min_interval": 1,
    "default_interval": 30,
    "timeout": 30,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)..."
}
