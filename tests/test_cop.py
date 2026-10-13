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


def test_system_cop_reads_inputs_48_and_34() -> None:
    by_address = {r.address: r for r in energy.ENERGY_REGISTERS}
    assert by_address[48].data_key == cop.THERMAL_POWER_KEY
    assert by_address[34].data_key == cop.ELECTRICAL_POWER_SYSTEM_KEY


def test_system_cop_has_its_own_id_and_is_removed_with_the_energy_sensors() -> None:
    assert cop.COP_SYSTEM_KEY != cop.COP_CURRENT_KEY
    assert cop.COP_SYSTEM_KEY.startswith(energy.ENERGY_UNIQUE_ID_PREFIX)
    assert cop.COP_SYSTEM_KEY not in {r.data_key for r in energy.ENERGY_REGISTERS}


def test_system_cop_is_lower_when_the_system_draws_more() -> None:
    """Same thermal power over a larger system draw gives a lower COP."""
    thermal = 9_000
    heat_pump, system = 2_000, 3_000  # e.g. a 1 kW backup heater running
    assert cop.current_cop(thermal, system) < cop.current_cop(thermal, heat_pump)


def test_thermal_power_from_flow_and_delta_t() -> None:
    # 20 l/min, 5 K: 20/60 × 5 × 4186 = 6976.7 W
    assert cop.thermal_power_w(20.0, 30.0, 35.0) == 6977
    assert cop.thermal_power_w(0.0, 30.0, 35.0) == 0


def test_thermal_power_never_negative() -> None:
    """Reversed ΔT (defrost, cooling) gives 0, as the sensors always did."""
    assert cop.thermal_power_w(20.0, 35.0, 30.0) == 0


def test_thermal_power_needs_all_inputs() -> None:
    assert cop.thermal_power_w(None, 30.0, 35.0) is None
    assert cop.thermal_power_w(20.0, None, 35.0) is None
    assert cop.thermal_power_w(20.0, 30.0, None) is None


def test_calculated_cop_combines_both() -> None:
    """flow × ΔT over the heat pump's power, same idle rule as COP Current."""
    thermal = cop.thermal_power_w(20.0, 30.0, 35.0)
    assert cop.current_cop(thermal, 1_744) == 4.0
    assert cop.current_cop(thermal, cop.MIN_ELECTRICAL_POWER_W - 1) is None


def test_calculated_cop_has_its_own_id_and_is_removed_with_the_energy_sensors() -> None:
    keys = {cop.COP_CURRENT_KEY, cop.COP_SYSTEM_KEY, cop.COP_CALCULATED_KEY}
    assert len(keys) == 3
    assert cop.COP_CALCULATED_KEY.startswith(energy.ENERGY_UNIQUE_ID_PREFIX)
