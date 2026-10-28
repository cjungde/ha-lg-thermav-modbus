"""The logic layer: what it does to the data, and that every function is a switch.

The point of the flow gate is a number nobody should have to believe: with the
pump stopped the SIKA VVX20 reports exactly 5.0 l/min, and the thermal power
sensors turned that into watts. These tests pin the gate to the pump bit, the
switch to its option, and the default to off.

No Home Assistant install is needed; ``logic.py`` imports nothing from it.
"""

from __future__ import annotations

import importlib.util
import json
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


logic = _load("logic")


def _poll(*, pump, flow):
    return {"di_water_pump": pump, "flow_rate": flow, "outlet_temp": 31.0}


def test_gate_zeroes_flow_when_pump_is_off():
    data = logic.LogicLayer(["flow_gate"]).process(_poll(pump=0, flow=5.0))
    assert data["flow_rate"] == 0.0
    assert data["flow_rate_raw"] == 5.0


def test_gate_keeps_flow_when_pump_runs():
    data = logic.LogicLayer(["flow_gate"]).process(_poll(pump=1, flow=29.5))
    assert data["flow_rate"] == 29.5
    assert data["flow_rate_raw"] == 29.5


def test_gate_drops_ramp_samples_while_pump_bit_is_still_off():
    """Between 5 and about 12 l/min the bit lags the flow by one poll."""
    data = logic.LogicLayer(["flow_gate"]).process(_poll(pump=0, flow=10.4))
    assert data["flow_rate"] == 0.0
    assert data["flow_rate_raw"] == 10.4


@pytest.mark.parametrize(
    "data",
    [
        {"flow_rate": 5.0},
        {"di_water_pump": 0},
        {},
    ],
)
def test_gate_does_not_guess_without_both_values(data):
    before = dict(data)
    logic.LogicLayer(["flow_gate"]).process(data)
    assert data == before


def test_gate_leaves_other_values_alone():
    data = logic.LogicLayer(["flow_gate"]).process(_poll(pump=0, flow=5.0))
    assert data["outlet_temp"] == 31.0
    assert data["di_water_pump"] == 0


def test_layer_with_nothing_enabled_returns_the_data_untouched():
    data = _poll(pump=0, flow=5.0)
    result = logic.LogicLayer([]).process(data)
    assert result is data
    assert data == _poll(pump=0, flow=5.0)
    assert "flow_rate_raw" not in data


def test_unknown_function_is_refused_rather_than_ignored():
    with pytest.raises(ValueError, match="no_such_function"):
        logic.LogicLayer(["no_such_function"])


def test_every_function_is_off_on_a_fresh_installation():
    """A function that changes a reported value must be asked for."""
    assert logic.LogicLayer.from_options({}).active == []


def test_option_switches_the_gate_on_and_off():
    key = logic.option_key("flow_gate")
    assert key == "logic_flow_gate"
    assert logic.LogicLayer.from_options({key: True}).active == ["flow_gate"]
    assert logic.LogicLayer.from_options({key: False}).active == []


def test_options_of_other_features_do_not_enable_anything():
    options = {"scan_interval": 10, "experimental_registers": True}
    assert logic.LogicLayer.from_options(options).active == []


def test_every_function_has_a_label_and_a_description_in_both_languages():
    """The options form is built from the registry; a missing string shows a raw key."""
    for language in ("en", "de"):
        strings = json.loads((COMPONENT / "translations" / f"{language}.json").read_text())
        step = strings["options"]["step"]["init"]
        for key in logic.FUNCTIONS:
            option = logic.option_key(key)
            assert step["data"].get(option), (language, option, "label")
            assert step["data_description"].get(option), (language, option, "description")
