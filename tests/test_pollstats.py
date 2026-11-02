"""Poll statistics: counting reads, duration, bus load and errors (pollstats.py).

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
    Path(__file__).resolve().parent.parent / "custom_components" / "lg_therma_v_r290"
)


def _load(module_name: str):
    package = "lg_therma_v_r290_under_test"
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
    assert pollstats.KEY_MODBUS_ERRORS == "modbus_errors"
    assert pollstats.KEY_LAST_MODBUS_ERROR == "last_modbus_error"
    for key in (
        pollstats.DATA_KEY_POLL_DURATION,
        pollstats.DATA_KEY_BUS_LOAD,
        pollstats.DATA_KEY_POLL_REQUESTS,
    ):
        assert key.startswith("poll_")


class Timeout(Exception):
    pass


class Refused(Exception):
    pass


class FailingUnit(Unit):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def read_coils(self, address, count):
        raise self.error

    async def write_register(self, address, value):
        raise self.error


def _clock():
    times = iter(range(100, 200))
    return lambda: next(times)


def test_failed_requests_are_logged_and_raised() -> None:
    log = pollstats.ErrorLog(refused=(Refused,), clock=_clock())
    calls = []
    log.add_listener(lambda: calls.append(log.errors))
    unit = pollstats.CountingUnit(FailingUnit(Timeout("no answer")), log)

    async def run():
        for call in (unit.read_coils(0, 6), unit.write_register(4, 350)):
            try:
                await call
            except Timeout:
                pass
            else:
                raise AssertionError("the error must reach the caller")
        assert await unit.read_holding_registers(0, 1) == [2]

    asyncio.run(run())
    assert log.since == 100
    assert log.errors == 2
    assert log.refusals == 0
    assert unit.reads == 2  # failed reads still count as requests
    assert log.last == {
        "error": "Timeout",
        "message": "no answer",
        "request": "write_register(4, 350)",
        "time": 102,
    }
    assert log.last_text() == "Timeout: no answer"
    assert calls == [1, 2]  # told after every failure, not after a success


def test_refusals_are_counted_apart() -> None:
    log = pollstats.ErrorLog(refused=(Refused,), clock=_clock())
    calls = []
    log.add_listener(lambda: calls.append(True))
    log.record("read_input_registers(9997, 2)", Refused("illegal address"))
    assert (log.errors, log.refusals) == (0, 1)
    assert log.last is None  # the unit answered: not the last error
    assert log.last_text() is None
    assert calls == [True]


def test_last_text_fits_a_state_and_never_is_empty() -> None:
    log = pollstats.ErrorLog(clock=_clock())
    log.record("read_coils(0, 6)", Timeout())
    assert log.last_text() == "Timeout: Timeout"
    log.record("read_coils(0, 6)", Timeout("x" * 400))
    assert len(log.last_text()) == pollstats.MAX_STATE_LENGTH


def test_listener_can_be_removed() -> None:
    log = pollstats.ErrorLog(clock=_clock())
    calls = []
    remove = log.add_listener(lambda: calls.append(True))
    remove()
    remove()  # twice is harmless
    log.record("read_coils(0, 6)", Timeout())
    assert calls == []


def test_without_a_log_errors_pass_through() -> None:
    unit = pollstats.CountingUnit(FailingUnit(Timeout("no answer")))

    async def run():
        try:
            await unit.read_coils(0, 6)
        except Timeout:
            return
        raise AssertionError("the error must reach the caller")

    asyncio.run(run())
    assert unit.reads == 1
