"""Current COP from the unit's power registers (input 48 / input 36).

cop.py and energy.py import nothing from Home Assistant, so no install is
needed.
"""

from __future__ import annotations

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


cop = _load("cop")
energy = _load("energy")


def test_divides_thermal_by_electrical_power() -> None:
    assert cop.current_cop(8_000, 2_000) == 4.0
    assert cop.current_cop(5_000, 1_500) == 3.33


def test_no_value_while_idling() -> None:
    """Below the threshold there is no meaningful COP: None, not 0."""
    assert cop.current_cop(0, 0) is None
    assert cop.current_cop(300, 40) is None
    assert cop.current_cop(0, cop.MIN_ELECTRICAL_POWER_W - 1) is None


def test_reported_from_the_threshold_on() -> None:
    assert cop.current_cop(0, cop.MIN_ELECTRICAL_POWER_W) == 0.0
    assert cop.current_cop(350, cop.MIN_ELECTRICAL_POWER_W) == 3.5


def test_no_value_without_both_registers() -> None:
    assert cop.current_cop(None, 2_000) is None
    assert cop.current_cop(8_000, None) is None


def test_reads_inputs_48_and_36() -> None:
    """The keys it divides are the data keys of input 48 and input 36."""
    by_address = {r.address: r for r in energy.ENERGY_REGISTERS}
    assert by_address[48].data_key == cop.THERMAL_POWER_KEY
    assert by_address[36].data_key == cop.ELECTRICAL_POWER_KEY


def test_removed_with_the_energy_sensors() -> None:
    assert cop.COP_CURRENT_KEY.startswith(energy.ENERGY_UNIQUE_ID_PREFIX)
    assert cop.COP_CURRENT_KEY not in {r.data_key for r in energy.ENERGY_REGISTERS}
