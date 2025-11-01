from app.middleware.logger.logging import file_logger

import asyncio
import functools
import time
from typing import Callable


def log_execution_time(func: Callable) -> Callable:
    """
    Decorator that logs the execution time of a function.
    Works with both async and sync functions.
    """
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            execution_time = time.time() - start_time
            file_logger.info(
                f"{func.__module__}.{func.__name__} executed in {execution_time:.2f} seconds",
                extra={
                    "function": f"{func.__module__}.{func.__name__}",
                    "execution_time": execution_time,
                }
            )

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            execution_time = time.time() - start_time
            file_logger.info(
                f"{func.__module__}.{func.__name__} executed in {execution_time:.2f} seconds",
                extra={
                    "function": f"{func.__module__}.{func.__name__}",
                    "execution_time": execution_time,
                }
            )

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper