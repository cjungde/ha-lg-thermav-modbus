"""Label table of the ODU operation cycle (input 30002).

const.py imports nothing from Home Assistant, so this needs no install.
The manual: "0: Standby (AUS) / 1: Kühlung / 2: Heizung".
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


def test_follows_the_manuals_table_for_30002() -> None:
    assert const.ODU_OPERATION_CYCLE_LABELS == {
        0: "Standby/Off",
        1: "Cooling",
        2: "Heating",
    }


def test_values_outside_the_manual_stay_unlabelled() -> None:
    """A 3 (defrost in an old YAML comment) shows as the number, not a guess."""
    assert 3 not in const.ODU_OPERATION_CYCLE_LABELS


def test_labels_are_unique() -> None:
    labels = list(const.ODU_OPERATION_CYCLE_LABELS.values())
    assert len(labels) == len(set(labels))
