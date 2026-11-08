"""Temperatures are signed words: below zero must stay below zero.

Read unsigned, -0.2 °C (raw 65534) became 6553.4 °C. In winter that drew square
waves on the evaporator, suction and outdoor sensors whenever they crossed zero.
"""

from __future__ import annotations

import re

import pytest

from .test_logic import COMPONENT, _load

decode = _load("decode")


@pytest.mark.parametrize(
    ("raw", "celsius"),
    [
        (0, 0.0),
        (41, 4.1),
        (553, 55.3),
        (32767, 3276.7),
        (65535, -0.1),
        (65534, -0.2),
        (65486, -5.0),
        (65286, -25.0),
        (32768, -3276.8),
    ],
)
def test_temperature_is_signed(raw: int, celsius: float) -> None:
    assert decode.temperature(raw) == celsius


def test_signed16_keeps_the_shift_registers() -> None:
    assert decode.signed16(5) == 5
    assert decode.signed16(65531) == -5


def test_every_temperature_key_goes_through_the_signed_decoder() -> None:
    """No temperature in the poll may be scaled by hand again."""
    source = (COMPONENT / "coordinator.py").read_text()
    by_hand = re.findall(r'"(\w*temp\w*)": round\(', source)
    assert by_hand == []
    decoded = re.findall(r'"(\w+)": temperature\(', source)
    assert {
        "outside_temp",
        "temp_before_vaporiser",
        "temp_after_vaporiser",
        "temp_suction",
        "temp_liquid_gas",
        "inlet_temp",
        "outlet_temp",
        "dhw_water_temp",
    } <= set(decoded)
    assert len(decoded) == 19
