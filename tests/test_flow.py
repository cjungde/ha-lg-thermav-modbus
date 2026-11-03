"""The flow rate: 0 instead of the sensor's 5.0 floor while nothing flows.

flow.py imports nothing from Home Assistant, so none of this needs an install.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "lg_therma_v_r290"
    / "flow.py"
)
_spec = importlib.util.spec_from_file_location("flow_under_test", PATH)
flow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flow)


def test_the_floor_with_the_pump_off_is_no_flow() -> None:
    """The measured case: 5.0 L/min, Water Flow and Water Pump both off."""
    assert flow.flow_rate(5.0, 0, 0) == 0.0


def test_a_real_flow_is_kept() -> None:
    assert flow.flow_rate(15.3, 1, 1) == 15.3
    assert flow.flow_rate(29.5, 1, 1) == 29.5


def test_the_floor_with_the_pump_running_is_kept() -> None:
    """Below 5 L/min the sensor cannot tell; with the pump on it is not 0."""
    assert flow.flow_rate(5.0, 1, 1) == 5.0
    assert flow.flow_rate(5.0, 0, 1) == 5.0
    assert flow.flow_rate(5.0, 1, 0) == 5.0


def test_a_reading_above_the_floor_is_kept_whatever_the_inputs_say() -> None:
    """Flow from another pump (an external one) is real flow."""
    assert flow.flow_rate(12.0, 0, 0) == 12.0


def test_missing_inputs_keep_the_register() -> None:
    assert flow.flow_rate(5.0, None, 0) == 5.0
    assert flow.flow_rate(5.0, 0, None) == 5.0
    assert flow.flow_rate(None, 0, 0) is None
