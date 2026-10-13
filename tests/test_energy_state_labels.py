"""Display text of the energy state sensors (holding 9 and input 11).

const.py imports nothing from Home Assistant, so no install is needed.
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


const = _load("const")


def test_every_state_shows_its_value_and_name() -> None:
    assert const.ENERGY_STATE_DISPLAY[0] == "0 – Not Used"
    assert const.ENERGY_STATE_DISPLAY[2] == "2 – Normal Operation"
    assert const.ENERGY_STATE_DISPLAY[8] == "8 – Super Energy Saving Mode"


def test_covers_exactly_the_labelled_values() -> None:
    assert set(const.ENERGY_STATE_DISPLAY) == set(range(9))
    assert set(const.ENERGY_STATE_DISPLAY) == set(const.ENERGY_STATE_LABELS)


def test_display_texts_are_unique() -> None:
    texts = list(const.ENERGY_STATE_DISPLAY.values())
    assert len(texts) == len(set(texts))
