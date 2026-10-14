"""Encoding and write rules of the power limit (coil 6, holding 24).

power_limit.py imports nothing from Home Assistant, so none of this needs an
install.
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


power_limit = _load("power_limit")
const = _load("const")
experimental = _load("experimental")
limits = _load("limits")


def test_addresses_are_the_manuals() -> None:
    """Coil 00007 and holding 40025, 0-based."""
    assert power_limit.POWER_LIMIT_COIL == 6
    assert power_limit.POWER_LIMIT_REGISTER == 24


def test_encode_is_tenths_of_a_kw() -> None:
    assert power_limit.encode_kw(0.1) == 1
    assert power_limit.encode_kw(2.0) == 20
    assert power_limit.encode_kw(7.3) == 73
    assert power_limit.encode_kw(25.0) == 250


def test_encode_clamps_to_the_manuals_range() -> None:
    assert power_limit.encode_kw(0) == 1  # never writes 0 by accident
    assert power_limit.encode_kw(-3) == 1
    assert power_limit.encode_kw(25.1) == 250
    assert power_limit.encode_kw(6553.5) == 250


def test_encode_rounds_to_a_tenth() -> None:
    assert power_limit.encode_kw(2.04) == 20
    assert power_limit.encode_kw(2.06) == 21


def test_decode() -> None:
    assert power_limit.decode_kw(None) is None
    assert power_limit.decode_kw(0) is None  # below the range: no value
    assert power_limit.decode_kw(1) == 0.1
    assert power_limit.decode_kw(73) == 7.3
    # Unexpected values are shown, not hidden by clamping.
    assert power_limit.decode_kw(300) == 30.0


def test_keys_follow_the_naming_rules() -> None:
    assert power_limit.KEY_POWER_LIMIT == "power_limit"
    assert power_limit.KEY_MAX_ELECTRICAL_POWER == "max_electrical_power"
    assert power_limit.DATA_KEY_POWER_LIMIT == "coil_power_limit"
    assert power_limit.DATA_KEY_MAX_ELECTRICAL_POWER == "holding_max_electrical_power"


def test_not_writable_unless_the_option_adds_it() -> None:
    assert power_limit.POWER_LIMIT_COIL not in const.WRITABLE_COILS
    assert power_limit.POWER_LIMIT_REGISTER not in const.WRITABLE_HOLDING_REGISTERS
    assert {power_limit.POWER_LIMIT_COIL} == const.POWER_LIMIT_WRITABLE_COILS
    assert {
        power_limit.POWER_LIMIT_REGISTER
    } == const.POWER_LIMIT_WRITABLE_HOLDING_REGISTERS


def test_separate_from_the_other_options() -> None:
    """The power limit option never makes coil 5 or holding 23 writable."""
    assert not const.POWER_LIMIT_WRITABLE_COILS & (
        const.EMERGENCY_OPERATION_WRITABLE_COILS
    )
    assert not const.POWER_LIMIT_WRITABLE_HOLDING_REGISTERS & (
        const.MODULATION_LIMIT_WRITABLE_HOLDING_REGISTERS
    )


def test_not_an_experimental_register() -> None:
    for kind, start, count in experimental.EXPERIMENTAL_BLOCKS:
        if kind == "holding":
            assert not start <= power_limit.POWER_LIMIT_REGISTER < start + count
