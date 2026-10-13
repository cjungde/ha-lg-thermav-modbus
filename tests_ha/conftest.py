"""Run the integration inside a real Home Assistant, against a fake unit.

These tests need Home Assistant (pytest-homeassistant-custom-component) and
run in their own CI job; tests/ stays free of it. Locally:

    pip install -r requirements_test_ha.txt
    pytest tests_ha -o asyncio_mode=auto

The test package pins the current Home Assistant release, so these tests
also catch changes in Home Assistant that break the integration. Its own
modbus component is replaced by a stub that hands out the fake unit: no bus
and no serial library are needed to test the flows, the setup and the
migration.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
import sys
import types

from homeassistant.exceptions import HomeAssistantError
from modbus_connection.exceptions import ModbusTimeoutError
import pytest

ROOT = Path(__file__).resolve().parent.parent


class FakeUnit:
    """Answers every read with zeros, except on the addresses set silent.

    A silent address raises a timeout, as a unit that does not serve it
    would after the request timeout. Writes are recorded.
    """

    def __init__(self, silent=()) -> None:
        self.silent = set(silent)
        self.requests: list[tuple[str, int]] = []
        self.writes: list[tuple[str, int, object]] = []

    async def _read(self, kind: str, address: int, count: int):
        self.requests.append((kind, address))
        await asyncio.sleep(0)
        if (kind, address) in self.silent:
            raise ModbusTimeoutError(f"{kind} {address}: no answer")
        return [0] * count

    async def read_input_registers(self, address, count):
        return await self._read("input", address, count)

    async def read_holding_registers(self, address, count):
        return await self._read("holding", address, count)

    async def read_coils(self, address, count):
        return [bool(v) for v in await self._read("coil", address, count)]

    async def read_discrete_inputs(self, address, count):
        return [bool(v) for v in await self._read("discrete", address, count)]

    async def write_coil(self, address, value):
        self.writes.append(("coil", address, value))

    async def write_register(self, address, value):
        self.writes.append(("holding", address, value))


class Bus:
    """The stub's state: the unit it hands out, and who holds which link.

    Like the shared connection, a device can be held by several entries only
    with the same link settings; borrowing it with other settings while it is
    held is refused.
    """

    unit: FakeUnit = FakeUnit()
    held: dict[str, object] = {}


def _endpoint(params) -> str:
    """The device a set of link settings talks to: socket or serial port."""
    device = getattr(params, "device", None)
    if device is None:
        return f"{params.host}:{params.port}"
    return device.removeprefix("socket://")


def _get_unit(hass, entry, params, slave):
    Bus.held[entry.entry_id] = params

    def release() -> None:
        Bus.held.pop(entry.entry_id, None)

    entry.async_on_unload(release)
    return Bus.unit


@contextlib.asynccontextmanager
async def _temporary_unit(hass, params, slave):
    for held in Bus.held.values():
        if _endpoint(held) == _endpoint(params) and held != params:
            raise HomeAssistantError("held with different link settings")
    yield Bus.unit


async def _setup(hass, config):
    return True


_modbus = types.ModuleType("homeassistant.components.modbus")
_modbus.async_get_unit = _get_unit
_modbus.async_get_temporary_unit = _temporary_unit
_modbus.async_setup = _setup
sys.modules["homeassistant.components.modbus"] = _modbus

# The test package ships a custom_components package of its own and imports
# it first; add this repository's to it so Home Assistant finds ours.
import custom_components  # noqa: E402

if str(ROOT / "custom_components") not in custom_components.__path__:
    custom_components.__path__.append(str(ROOT / "custom_components"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def unit():
    """A fresh fake unit for the test; set .silent to leave addresses out."""
    Bus.unit = FakeUnit()
    Bus.held.clear()
    return Bus.unit
