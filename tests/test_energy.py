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


def test_data_keys_use_the_unique_id_prefix() -> None:
    """The prefix is what removes the sensors again when the option is off."""
    for register in energy.ENERGY_REGISTERS:
        assert register.data_key.startswith(energy.ENERGY_UNIQUE_ID_PREFIX)


def test_demand_vs_supply_has_no_unit() -> None:
    """It reads 0-12, so it must not be presented as a percentage."""
    by_key = {r.key: r for r in energy.ENERGY_REGISTERS}
    assert by_key["demand_vs_supply"].kind == energy.KIND_VALUE


def test_numbers_follow_the_manuals_notation() -> None:
    by_key = {r.key: r for r in energy.ENERGY_REGISTERS}
    assert by_key["power_total_system"].modbus_number == 30035
    assert by_key["thermal_energy_heating"].modbus_number == 30051


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
    assert values["energy_reg_power_heat_pump"] == 2300
    assert values["energy_reg_energy_total"] == 123_456_789
    assert values["energy_reg_thermal_energy_heating"] == 42
    assert values["energy_reg_power_total_system"] == 0
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


def test_backoff_tries_until_the_threshold_then_pauses() -> None:
    backoff = energy.RetryBackoff(failures_before_pause=3, pause_polls=4)
    assert backoff.should_try()
    assert not backoff.record(False)
    assert backoff.should_try()
    assert not backoff.record(False)
    assert backoff.should_try()
    assert backoff.record(False)  # third miss starts the pause
    # Four skipped polls, then one more attempt.
    assert [backoff.should_try() for _ in range(4)] == [False] * 4
    assert backoff.should_try()


def test_a_success_resets_the_count() -> None:
    backoff = energy.RetryBackoff(failures_before_pause=3, pause_polls=4)
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


def test_heating_cop_divides_thermal_by_electrical() -> None:
    assert energy.heating_cop(12_000, 3_000) == 4.0
    assert energy.heating_cop(10_000, 3_000) == 3.33


def test_heating_cop_is_none_without_electrical_energy() -> None:
    """Not 0: a 0 would read as a terrible COP and skew statistics."""
    assert energy.heating_cop(5_000, 0) is None
    assert energy.heating_cop(None, 3_000) is None
    assert energy.heating_cop(5_000, None) is None


def test_heating_cop_reads_inputs_50_and_40() -> None:
    """The keys it divides are the data keys of input 50 and input 40."""
    by_address = {r.address: r for r in energy.ENERGY_REGISTERS}
    assert by_address[50].data_key == energy.THERMAL_ENERGY_HEATING_KEY
    assert by_address[40].data_key == energy.ELECTRICAL_ENERGY_HEATING_KEY


def test_heating_cop_is_removed_with_the_energy_sensors() -> None:
    assert energy.HEATING_COP_KEY.startswith(energy.ENERGY_UNIQUE_ID_PREFIX)
    assert energy.HEATING_COP_KEY not in {r.data_key for r in energy.ENERGY_REGISTERS}
