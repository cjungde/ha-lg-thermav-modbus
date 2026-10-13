"""Encoding and write rules of the compressor modulation limit (holding 23).

limits.py imports nothing from Home Assistant, so none of this needs an install.
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


limits = _load("limits")
const = _load("const")
experimental = _load("experimental")


def test_register_is_holding_23() -> None:
    assert limits.MODULATION_LIMIT_REGISTER == 23


def test_encode_clamps_to_the_slider_range() -> None:
    assert limits.encode(40) == 40
    assert limits.encode(75) == 75
    assert limits.encode(100) == 100
    assert limits.encode(39) == 40
    assert limits.encode(0) == 40  # never writes "not used" by accident
    assert limits.encode(-5) == 40
    assert limits.encode(101) == 100
    assert limits.encode(65535) == 100


def test_encode_rounds_to_whole_percent() -> None:
    assert limits.encode(62.4) == 62
    assert limits.encode(62.6) == 63


def test_decode_keeps_not_used_apart() -> None:
    assert limits.decode(0) == {
        limits.DATA_KEY_LIMIT: None,
        limits.DATA_KEY_RAW: 0,
    }


def test_decode_reports_a_limit_as_read() -> None:
    assert limits.decode(70) == {
        limits.DATA_KEY_LIMIT: 70,
        limits.DATA_KEY_RAW: 70,
    }
    # Unexpected values are shown, not hidden by clamping.
    assert limits.decode(120)[limits.DATA_KEY_LIMIT] == 120


def test_not_writable_unless_the_option_adds_it() -> None:
    """23 is not in the fixed whitelist; only the option makes it writable."""
    assert limits.MODULATION_LIMIT_REGISTER not in const.WRITABLE_HOLDING_REGISTERS
    assert {
        limits.MODULATION_LIMIT_REGISTER
    } == const.OPTIONAL_WRITABLE_HOLDING_REGISTERS


def test_not_an_experimental_register() -> None:
    """The experimental holding block stops at 22; 23 is never in it."""
    for kind, start, count in experimental.EXPERIMENTAL_BLOCKS:
        if kind == "holding":
            assert not start <= limits.MODULATION_LIMIT_REGISTER < start + count
