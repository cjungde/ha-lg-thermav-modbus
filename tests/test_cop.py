"""COP and thermal power calculations (cop.py).

cop.py and energy.py import nothing from Home Assistant, so no install is
needed.
"""

from __future__ import annotations

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


cop = _load("cop")
energy = _load("energy")


def test_instantaneous_cop_divides_thermal_by_electrical_power() -> None:
    assert cop.instantaneous_cop(8_000, 2_000) == 4.0
    assert cop.instantaneous_cop(5_000, 1_500) == 3.33


def test_no_value_while_idling() -> None:
    """Below the threshold there is no meaningful COP: None, not 0."""
    assert cop.instantaneous_cop(0, 0) is None
    assert cop.instantaneous_cop(300, 40) is None
    assert cop.instantaneous_cop(0, cop.MIN_ELECTRICAL_POWER_W - 1) is None


def test_reported_from_the_threshold_on() -> None:
    assert cop.instantaneous_cop(0, cop.MIN_ELECTRICAL_POWER_W) == 0.0
    assert cop.instantaneous_cop(350, cop.MIN_ELECTRICAL_POWER_W) == 3.5


def test_no_value_without_both_values() -> None:
    assert cop.instantaneous_cop(None, 2_000) is None
    assert cop.instantaneous_cop(8_000, None) is None


def test_system_cop_is_lower_when_the_system_draws_more() -> None:
    """Same thermal power over a larger system draw gives a lower COP."""
    thermal = 9_000
    heat_pump, system = 2_000, 3_000  # e.g. a 1 kW backup heater running
    assert cop.instantaneous_cop(thermal, system) < cop.instantaneous_cop(
        thermal, heat_pump
    )


def test_cumulative_cop_divides_thermal_by_electrical_energy() -> None:
    assert cop.cumulative_cop(12_000, 3_000) == 4.0
    assert cop.cumulative_cop(10_000, 3_000) == 3.33


def test_cumulative_cop_is_none_without_electrical_energy() -> None:
    """Not 0: a 0 would read as a terrible COP and skew statistics."""
    assert cop.cumulative_cop(5_000, 0) is None
    assert cop.cumulative_cop(None, 3_000) is None
    assert cop.cumulative_cop(5_000, None) is None


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
    """flow × ΔT over the heat pump's power, same idle rule as COP (Reported)."""
    thermal = cop.thermal_power_w(20.0, 30.0, 35.0)
    assert cop.instantaneous_cop(thermal, 1_744) == 4.0
    assert cop.instantaneous_cop(thermal, cop.MIN_ELECTRICAL_POWER_W - 1) is None


def test_cop_keys_are_the_name_slugs() -> None:
    """docs/naming.md: key = name as an entity id slug."""
    assert cop.KEY_COP_REPORTED == "cop_reported"
    assert cop.KEY_COP_SYSTEM_REPORTED == "cop_system_reported"
    assert cop.KEY_COP_CALCULATED == "cop_calculated"
    assert cop.KEY_COP_HEATING_CUMULATIVE == "cop_heating_cumulative"
    assert len(set(cop.COP_KEYS)) == 4


def test_cop_keys_do_not_collide_with_the_energy_sensors() -> None:
    assert not set(cop.COP_KEYS) & {r.key for r in energy.ENERGY_REGISTERS}
