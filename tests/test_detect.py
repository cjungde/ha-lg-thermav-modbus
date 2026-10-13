"""Which optional register groups are checked, suggested and shown (detect.py).

detect.py imports nothing from Home Assistant, so none of this needs an
install.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

from modbus_connection.exceptions import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusTimeoutError,
)

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


detect = _load("detect")
const = _load("const")

ENERGY = const.CONF_ENERGY_REGISTERS
MODULATION = const.CONF_MODULATION_LIMIT
POWER = const.CONF_POWER_LIMIT


class Unit:
    """Answers everywhere except on the addresses given as silent."""

    def __init__(self, silent=(), error=ModbusTimeoutError) -> None:
        self.silent = set(silent)
        self.error = error
        self.requests: list[tuple[str, int, int]] = []

    def _read(self, kind: str, address: int, count: int):
        self.requests.append((kind, address, count))
        if (kind, address) in self.silent:
            raise self.error("no answer")
        return [0] * count

    async def read_input_registers(self, address, count):
        return self._read("input", address, count)

    async def read_holding_registers(self, address, count):
        return self._read("holding", address, count)

    async def read_coils(self, address, count):
        return self._read("coil", address, count)


def _run(unit) -> dict[str, bool]:
    return asyncio.run(detect.detect(unit))


def test_a_unit_that_answers_everywhere() -> None:
    unit = Unit()
    assert _run(unit) == {ENERGY: True, MODULATION: True, POWER: True}
    assert unit.requests == [
        ("input", 34, 18),
        ("holding", 23, 1),
        ("coil", 6, 1),
        ("holding", 24, 1),
    ]


def test_a_unit_like_the_scanned_9_kw() -> None:
    """Silent on all three groups; the power limit register is not asked
    once the coil has not answered, which saves one timeout."""
    unit = Unit(silent={("input", 34), ("holding", 23), ("coil", 6)})
    assert _run(unit) == {ENERGY: False, MODULATION: False, POWER: False}
    assert ("holding", 24, 1) not in unit.requests


def test_power_limit_needs_both_addresses() -> None:
    assert _run(Unit(silent={("holding", 24)}))[POWER] is False


def test_any_modbus_error_counts_as_no_answer() -> None:
    for error in (ModbusTimeoutError, IllegalDataAddressError, ModbusConnectionError):
        assert _run(Unit(silent={("holding", 23)}, error=error))[MODULATION] is False


def test_only_safe_groups_are_suggested() -> None:
    everything = {ENERGY: True, MODULATION: True, POWER: True}
    result = detect.suggested(everything, {})
    assert result == {ENERGY: True, MODULATION: True}
    assert POWER not in result


def test_never_ticks_emergency_or_experimental() -> None:
    assert const.CONF_EMERGENCY_OPERATION not in detect.SUGGESTED_WHEN_ANSWERING
    assert const.CONF_EXPERIMENTAL not in detect.SUGGESTED_WHEN_ANSWERING
    assert POWER not in detect.SUGGESTED_WHEN_ANSWERING


def test_suggestions_never_switch_anything_off() -> None:
    current = {ENERGY: True, POWER: True, "scan_interval": 10}
    nothing = {ENERGY: False, MODULATION: False, POWER: False}
    assert detect.suggested(nothing, current) == current
    assert detect.suggested(None, current) == current


def test_placeholders() -> None:
    assert detect.placeholders({ENERGY: True, MODULATION: False, POWER: True}) == {
        ENERGY: "✓",
        MODULATION: "✗",
        POWER: "✓",
    }
    unknown = {ENERGY: "–", MODULATION: "–", POWER: "–"}
    assert detect.placeholders(None) == unknown
    assert detect.placeholders({}) == unknown


def test_status_shows_what_could_be_switched_on() -> None:
    detected = {ENERGY: True, MODULATION: True, POWER: False}
    options = {ENERGY: True, const.CONF_EXPERIMENTAL: True}
    status = detect.status_placeholders(detected, options)
    assert status[f"{ENERGY}_on"] == "✓"
    assert status[ENERGY] == "✓"  # on and answers: nothing to add
    assert status[f"{MODULATION}_on"] == "–"
    assert status[MODULATION] == "✓ ➕"  # answers, but off
    assert status[POWER] == "✗"
    assert status[f"{const.CONF_EXPERIMENTAL}_on"] == "✓"
    assert status[const.CONF_EXPERIMENTAL] == "–"  # never checked
    assert status[const.CONF_EMERGENCY_OPERATION] == "–"
    assert set(status) == {k for g in detect.GROUPS for k in (g, f"{g}_on")}


def test_status_before_any_check() -> None:
    status = detect.status_placeholders(None, {})
    assert all(value == "–" for value in status.values())


def test_every_placeholder_is_in_the_texts() -> None:
    """Each description uses exactly the placeholders the flow fills in."""
    import json
    import re

    status = set(detect.status_placeholders(None, {})) | {"checked"}
    setup = set(detect.placeholders(None))
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        texts = json.loads((COMPONENT / name).read_text())
        steps = texts["options"]["step"]
        for step in ("init", "options"):
            found = set(re.findall(r"\{(\w+)\}", steps[step]["description"]))
            assert found == status, (name, step)
        features = texts["config"]["step"]["features"]["description"]
        assert set(re.findall(r"\{(\w+)\}", features)) == setup, name
