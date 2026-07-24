from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar


T = TypeVar("T")
R = TypeVar("R")


async def execute_batch(
    items: Sequence[T],
    executor: Callable[[T], Awaitable[R]],
    *,
    max_concurrency: int,
) -> list[R | dict[str, object]]:
    if not isinstance(max_concurrency, int) or isinstance(max_concurrency, bool) or max_concurrency < 1:
        raise ValueError("max_concurrency must be a positive integer")
    semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_one(index: int, item: T) -> tuple[int, R | dict[str, object]]:
        async with semaphore:
            try:
                return index, await executor(item)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                return index, {
                    "status": "failed",
                    "error_code": "network.batch_item_failed",
                    "message": type(exc).__name__,
                }

    completed = await asyncio.gather(
        *(execute_one(index, item) for index, item in enumerate(items))
    )
    completed.sort(key=lambda item: item[0])
    return [result for _, result in completed]
