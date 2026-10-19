"""Layout, decoding and retry behaviour of the energy block (input 34-51).

energy.py imports nothing from Home Assistant, so none of this needs an install.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

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


energy = _load("energy")
const = _load("const")


def test_block_covers_exactly_the_registers_in_use() -> None:
    """Every register is two words inside the block, none overlap."""
    start = energy.ENERGY_BLOCK_START
    end = start + energy.ENERGY_BLOCK_COUNT
    words: list[int] = []
    for register in energy.ENERGY_REGISTERS:
        assert start <= register.address
        assert register.address + 2 <= end
        words += [register.address, register.address + 1]
    assert len(words) == len(set(words))
    # No gap in the block: one unanswered address would drop the whole request.
    assert set(words) == set(range(start, end))


def test_block_stays_clear_of_the_unconfirmed_registers() -> None:
    """52-55 do not answer on a 12 kW unit; one silent address drops the block."""
    end = energy.ENERGY_BLOCK_START + energy.ENERGY_BLOCK_COUNT
    assert end <= 52


def test_keys_and_names_are_unique() -> None:
    registers = energy.ENERGY_REGISTERS
    assert len({r.key for r in registers}) == len(registers)
    assert len({r.data_key for r in registers}) == len(registers)
    assert len({r.name for r in registers}) == len(registers)


def test_keys_follow_the_naming_rules() -> None:
    """docs/naming.md: key = name slug, data key = input_<key>."""
    for register in energy.ENERGY_REGISTERS:
        slug = "".join(c if c.isalnum() else "_" for c in register.name.lower())
        assert register.key == "_".join(part for part in slug.split("_") if part)
        assert register.data_key == f"input_{register.key}"


def test_data_key_constants_point_at_the_right_registers() -> None:
    by_address = {r.address: r.data_key for r in energy.ENERGY_REGISTERS}
    assert by_address[34] == energy.DATA_KEY_ELECTRICAL_POWER_TOTAL_SYSTEM
    assert by_address[36] == energy.DATA_KEY_ELECTRICAL_POWER_HEAT_PUMP
    assert by_address[40] == energy.DATA_KEY_ELECTRICAL_ENERGY_SPACE_HEATING
    assert by_address[48] == energy.DATA_KEY_THERMAL_POWER_REPORTED
    assert by_address[50] == energy.DATA_KEY_THERMAL_ENERGY_SPACE_HEATING


def test_demand_vs_supply_has_no_unit() -> None:
    """It reads 0-12, so it must not be presented as a percentage."""
    by_key = {r.key: r for r in energy.ENERGY_REGISTERS}
    assert by_key["demand_vs_supply"].kind == energy.KIND_VALUE


def test_numbers_follow_the_manuals_notation() -> None:
    by_key = {r.key: r for r in energy.ENERGY_REGISTERS}
    assert by_key["electrical_power_total_system"].modbus_number == 30035
    assert by_key["thermal_energy_space_heating"].modbus_number == 30051


def test_decode_joins_high_word_first() -> None:
    assert energy.decode_uint32(0, 1234) == 1234
    assert energy.decode_uint32(1, 0) == 65536
    assert energy.decode_uint32(0x0001, 0x86A0) == 100_000
    assert energy.decode_uint32(0xFFFF, 0xFFFF) == 0xFFFFFFFF


def test_decode_block_picks_each_value_from_its_own_pair() -> None:
    registers = [0] * energy.ENERGY_BLOCK_COUNT
    # power_heat_pump at 36-37 -> offset 2, 3
    registers[2], registers[3] = 0, 2300
    # energy_total at 38-39 -> offset 4, 5 : 123_456_789 Wh
    registers[4], registers[5] = 123_456_789 >> 16, 123_456_789 & 0xFFFF
    # thermal_energy_heating at 50-51 -> offset 16, 17
    registers[16], registers[17] = 0, 42
    values = energy.decode_block(registers)
    assert values["input_electrical_power_heat_pump"] == 2300
    assert values["input_electrical_energy_total"] == 123_456_789
    assert values["input_thermal_energy_space_heating"] == 42
    assert values["input_electrical_power_total_system"] == 0
    assert len(values) == len(energy.ENERGY_REGISTERS)


def test_decode_block_rejects_a_short_read() -> None:
    with pytest.raises(ValueError):
        energy.decode_block([0] * (energy.ENERGY_BLOCK_COUNT - 1))


def test_nothing_in_the_block_is_writable() -> None:
    block = set(
        range(
            energy.ENERGY_BLOCK_START,
            energy.ENERGY_BLOCK_START + energy.ENERGY_BLOCK_COUNT,
        )
    )
    assert not block & const.WRITABLE_HOLDING_REGISTERS


def test_backoff_gives_up_on_a_block_that_never_answered() -> None:
    """Three misses without a single answer since start: the unit most likely
    does not serve the block, so it is not asked again until a reload."""
    backoff = energy.RetryBackoff(failures_before_pause=3, pause_polls=4)
    assert backoff.status() == energy.STATUS_NOT_READ
    assert backoff.should_try()
    assert backoff.record(False) is None
    assert backoff.status() == energy.STATUS_MISSING
    assert backoff.should_try()
    assert backoff.record(False) is None
    assert backoff.should_try()
    assert backoff.record(False) == energy.EVENT_GAVE_UP
    assert backoff.status() == energy.STATUS_GIVEN_UP
    assert not any(backoff.should_try() for _ in range(100))
    assert backoff.state()["ever_answered"] is False


def test_backoff_pauses_a_block_that_answered_before() -> None:
    """Misses after an answer are most likely a hiccup: rest, then try again."""
    backoff = energy.RetryBackoff(failures_before_pause=3, pause_polls=4)
    assert backoff.should_try()
    assert backoff.record(True) is None
    assert backoff.status() == energy.STATUS_ANSWERING
    for _ in range(2):
        assert backoff.should_try()
        assert backoff.record(False) is None
    assert backoff.should_try()
    assert backoff.record(False) == energy.EVENT_PAUSED
    assert backoff.status() == energy.STATUS_PAUSED
    # Four skipped polls, then one more attempt.
    assert [backoff.should_try() for _ in range(4)] == [False] * 4
    assert backoff.should_try()
    assert backoff.record(True) is None
    assert backoff.status() == energy.STATUS_ANSWERING


def test_a_success_resets_the_count() -> None:
    backoff = energy.RetryBackoff(failures_before_pause=3, pause_polls=4)
    backoff.should_try()
    backoff.record(True)
    for _ in range(2):
        backoff.should_try()
        backoff.record(False)
    backoff.should_try()
    backoff.record(True)
    # Two more misses are not enough to pause again.
    for _ in range(2):
        assert backoff.should_try()
        assert not backoff.record(False)
    assert backoff.should_try()


def test_a_healthy_unit_is_never_paused() -> None:
    backoff = energy.RetryBackoff()
    for _ in range(100):
        assert backoff.should_try()
        assert not backoff.record(True)
