"""COP against the user's own meter: integration, counter growth, ratio.

external_meter.py imports nothing from Home Assistant, so none of this needs
an install.
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


em = _load("external_meter")


def test_integrator_counts_the_previous_power_over_the_interval() -> None:
    integrator = em.EnergyIntegrator()
    assert integrator.add(6000, 0) == 0  # the first sample has no interval
    assert integrator.add(3000, 60) == pytest.approx(0.1)  # 6 kW for 1 min
    assert integrator.add(0, 120) == pytest.approx(0.15)  # 3 kW for 1 min


def test_integrator_skips_gaps_and_unknown_power() -> None:
    integrator = em.EnergyIntegrator(kwh=1.0)
    integrator.add(6000, 0)
    integrator.add(6000, 0 + em.MAX_GAP_S + 1)  # Home Assistant was down
    assert integrator.kwh == 1.0
    integrator.add(None, em.MAX_GAP_S + 61)  # 6 kW for 1 min, then unknown
    assert integrator.kwh == pytest.approx(1.1)
    integrator.add(6000, em.MAX_GAP_S + 121)  # unknown power: not counted
    assert integrator.kwh == pytest.approx(1.1)


def test_integrator_ignores_time_going_backwards() -> None:
    integrator = em.EnergyIntegrator()
    integrator.add(6000, 100)
    integrator.add(6000, 50)
    assert integrator.kwh == 0


def test_counter_delta_counts_growth_and_resets() -> None:
    delta = em.CounterDelta()
    assert delta.add(1000.0) == 0  # the first reading is the start
    assert delta.add(1002.5) == pytest.approx(2.5)
    assert delta.add(None) == pytest.approx(2.5)  # unavailable meter
    assert delta.add(1.0) == pytest.approx(3.5)  # reset: new value is growth
    assert delta.add(2.0) == pytest.approx(4.5)


def test_ratio() -> None:
    assert em.ratio(7.0, 2.0) == 3.5
    assert em.ratio(7.0, 0) is None
    assert em.ratio(None, 2.0) is None
    assert em.ratio(7.0, None) is None


def test_state_for_a_restart() -> None:
    integrator = em.EnergyIntegrator(kwh=3.0)
    delta = em.CounterDelta(kwh=1.0, last=500.0)
    assert em.state(integrator, delta) == {
        "thermal_kwh": 3.0,
        "electrical_kwh": 1.0,
        "electrical_last": 500.0,
    }
