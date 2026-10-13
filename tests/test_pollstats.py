"""Poll statistics: counting reads, duration and bus load (pollstats.py).

pollstats.py imports nothing from Home Assistant, so none of this needs an
install.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

COMPONENT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "lg_thermav_r290"
)


def _load(module_name: str):
    package = "lg_thermav_r290_under_test"
    if package not in sys.modules:
        stub = types.ModuleType(package)
        stub.__path__ = [str(COMPONENT)]
        sys.modules[package] = stub

    qualified = f"{package}.{module_name}"
    if qualified not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            qualified, COMPONENT / f"{module_name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
    return sys.modules[qualified]


pollstats = _load("pollstats")


class Unit:
    def __init__(self) -> None:
        self.writes = []

    async def read_input_registers(self, address, count):
        return [1] * count

    async def read_holding_registers(self, address, count):
        return [2] * count

    async def read_coils(self, address, count):
        return [True] * count

    async def read_discrete_inputs(self, address, count):
        return [False] * count

    async def write_coil(self, address, value):
        self.writes.append((address, value))


def test_counts_reads_and_passes_values_through() -> None:
    inner = Unit()
    unit = pollstats.CountingUnit(inner)

    async def run():
        assert await unit.read_input_registers(0, 3) == [1, 1, 1]
        assert await unit.read_holding_registers(0, 2) == [2, 2]
        assert await unit.read_coils(0, 1) == [True]
        assert await unit.read_discrete_inputs(0, 1) == [False]
        await unit.write_coil(0, True)

    asyncio.run(run())
    assert unit.reads == 4  # writes are not counted
    assert inner.writes == [(0, True)]


def test_stats() -> None:
    assert pollstats.stats(0.8, 10, 6) == {
        "poll_duration_ms": 800,
        "poll_bus_load": 8.0,
        "poll_requests": 6,
    }
    assert pollstats.stats(0.0123, 10, 5)["poll_duration_ms"] == 12
    assert pollstats.stats(0.0123, 10, 5)["poll_bus_load"] == 0.1
    assert pollstats.stats(1.0, 0, 5)["poll_bus_load"] is None


def test_keys_follow_the_naming_rules() -> None:
    assert pollstats.KEY_POLL_DURATION == "poll_duration"
    assert pollstats.KEY_BUS_LOAD == "bus_load"
    for key in (
        pollstats.DATA_KEY_POLL_DURATION,
        pollstats.DATA_KEY_BUS_LOAD,
        pollstats.DATA_KEY_POLL_REQUESTS,
    ):
        assert key.startswith("poll_")
