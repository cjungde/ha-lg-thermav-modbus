"""The status of the optional reads since start (register_status.py).

register_status.py imports nothing from Home Assistant, so none of this needs
an install.
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


status = _load("register_status")
detect = _load("detect")

ENERGY = "energy_registers"
MODULATION = "compressor_modulation_limit"
POWER = "power_limit"
EXPERIMENTAL = "experimental_registers"


def _snapshot(**groups) -> dict:
    snapshot = {ENERGY: None, MODULATION: None, POWER: None, EXPERIMENTAL: False}
    snapshot[status.EXPERIMENTAL_GIVEN_UP] = []
    snapshot.update(groups)
    return snapshot


def test_nothing_on_is_not_used() -> None:
    assert status.overall_state(_snapshot()) == "not_used"


def test_the_worst_group_that_is_on_decides() -> None:
    assert status.overall_state(_snapshot(energy_registers="answering")) == "ok"
    assert (
        status.overall_state(
            _snapshot(energy_registers="answering", power_limit="paused")
        )
        == "paused"
    )
    assert (
        status.overall_state(
            _snapshot(energy_registers="given_up", power_limit="paused")
        )
        == "given_up"
    )


def test_a_single_miss_is_not_a_state_of_its_own() -> None:
    """So an automation on the sensor does not fire on every bus hiccup."""
    assert status.overall_state(_snapshot(energy_registers="missing")) == "ok"


def test_experimental_blocks_given_up_do_not_count() -> None:
    """Expected on many units; the column and the attributes show them."""
    snapshot = _snapshot(experimental_registers=True)
    snapshot[status.EXPERIMENTAL_GIVEN_UP] = ["holding 10"]
    assert status.overall_state(snapshot) == "not_used"


def test_since_start_marks() -> None:
    snapshot = _snapshot(
        energy_registers="given_up",
        compressor_modulation_limit="paused",
        power_limit="missing",
        experimental_registers=True,
    )
    snapshot[status.EXPERIMENTAL_GIVEN_UP] = ["holding 10", "input 15"]
    marks = status.since_start_placeholders(snapshot, detect.GROUPS)
    assert marks == {
        "energy_registers_now": "⛔",
        "compressor_modulation_limit_now": "⏸",
        "power_limit_now": "⚠",
        "emergency_operation_button_now": "–",
        "experimental_registers_now": "⛔ 2",
        "compressor_statistics_now": "–",
        "poll_statistics_now": "–",
    }


def test_since_start_when_not_loaded_or_not_read() -> None:
    assert set(status.since_start_placeholders(None, detect.GROUPS).values()) == {"–"}
    snapshot = _snapshot(energy_registers="not_read", experimental_registers=True)
    marks = status.since_start_placeholders(snapshot, detect.GROUPS)
    assert marks["energy_registers_now"] == "–"
    assert marks["experimental_registers_now"] == "✓"


def test_attributes() -> None:
    snapshot = _snapshot(energy_registers="given_up", experimental_registers=True)
    snapshot[status.EXPERIMENTAL_GIVEN_UP] = ["holding 10"]
    options = {
        "detected": {ENERGY: False, MODULATION: True},
        "detected_at": "2026-10-19T13:00:00+00:00",
    }
    assert status.attributes(snapshot, options) == {
        "energy_registers": "given_up",
        "energy_registers_last_check": "no_answer",
        "compressor_modulation_limit": "off",
        "compressor_modulation_limit_last_check": "answers",
        "power_limit": "off",
        "power_limit_last_check": "not_checked",
        "experimental_registers": "on",
        "experimental_blocks_given_up": ["holding 10"],
        "last_check": "2026-10-19T13:00:00+00:00",
    }


def test_every_state_and_notice_is_translated() -> None:
    import json

    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        texts = json.loads((COMPONENT / name).read_text())
        states = texts["entity"]["sensor"]["optional_registers"]["state"]
        assert set(states) == set(status.STATES), name
        issues = texts["issues"]
        assert set(issues) == {f"{g}_never_answered" for g in status.BACKOFF_GROUPS}
        for issue in issues.values():
            confirm = issue["fix_flow"]["step"]["confirm"]
            assert "{entry}" in confirm["description"], name
