"""Temperatures are signed: -0.2 °C arrives as 65534, not 6553.4 °C.

decode.py imports nothing from Home Assistant; coordinator.py does, so its
keys are read from the syntax tree rather than executed.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

COMPONENT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "lg_therma_v_r290"
)
_spec = importlib.util.spec_from_file_location(
    "decode_under_test", COMPONENT / "decode.py"
)
decode = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(decode)


@pytest.mark.parametrize(
    ("raw", "celsius"),
    [
        (0, 0.0),
        (215, 21.5),
        (650, 65.0),
        (65534, -0.2),  # read unsigned this was 6553.4 °C
        (65436, -10.0),
        (65286, -25.0),
        (32767, 3276.7),  # the largest positive word stays positive
    ],
)
def test_temperature_is_signed(raw: int, celsius: float) -> None:
    assert decode.temperature(raw) == celsius


def test_signed16_keeps_the_shift_registers() -> None:
    assert decode.signed16(5) == 5
    assert decode.signed16(65531) == -5


def _poll_keys() -> dict[str, ast.expr]:
    """The keys of the dict the coordinator's poll returns, with their values."""
    tree = ast.parse((COMPONENT / "coordinator.py").read_text(encoding="utf-8"))
    keys: dict[str, ast.expr] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys[key.value] = value
    return keys


def test_every_temperature_goes_through_the_signed_decoder() -> None:
    temperatures = {k: v for k, v in _poll_keys().items() if "temperature" in k}
    unsigned = [
        key
        for key, value in temperatures.items()
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "temperature"
        )
    ]
    assert unsigned == []
    assert len(temperatures) == 19


def test_flow_and_pressure_stay_unsigned() -> None:
    """They cannot be negative; a signed read would only turn noise negative."""
    keys = _poll_keys()
    for key in ("input_flow_rate", "input_water_pressure"):
        assert "temperature(" not in ast.unparse(keys[key])


def test_an_input_without_a_sensor_has_no_temperature() -> None:
    """64887 is -64.9 °C as a signed word: what an unconnected input sends."""
    assert decode.temperature(decode.NO_SENSOR) is None
    assert decode.temperature(64887) is None


def test_temperatures_next_to_the_placeholder_are_kept() -> None:
    assert decode.temperature(64886) == -65.0
    assert decode.temperature(64888) == -64.8
