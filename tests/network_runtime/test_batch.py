from __future__ import annotations

import asyncio

from weconduct.network_runtime.batch import execute_batch


def test_batch_executor_preserves_input_order_and_honors_serial_limit() -> None:
    async def run() -> None:
        active = 0
        max_active = 0

        async def execute(item: int) -> dict[str, int]:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.001 * (4 - item))
            active -= 1
            return {"item": item}

        results = await execute_batch([1, 2, 3], execute, max_concurrency=1)

        assert results == [{"item": 1}, {"item": 2}, {"item": 3}]
        assert max_active == 1

    asyncio.run(run())


def test_batch_executor_returns_structured_failure_for_one_item() -> None:
    async def run() -> None:
        async def execute(item: int) -> int:
            if item == 2:
                raise RuntimeError("secret implementation detail")
            return item * 2

        results = await execute_batch([1, 2, 3], execute, max_concurrency=2)

        assert results[0] == 2
        assert results[1]["status"] == "failed"
        assert results[1]["error_code"] == "network.batch_item_failed"
        assert "secret implementation detail" not in results[1]["message"]
        assert results[2] == 6

    asyncio.run(run())
