"""The 20-second request timeout the coordinator asks the shared link for.

The floor exists because a slow answer from the heat pump must not be read as a
dropped link -- it shares the RS485 gateway with an energy meter, so a request
can wait behind someone else's conversation. It is one line in
``coordinator.py``, and until now nothing caught its removal: the suite passed
against ``modbus-connection`` 4.10.0, which has no such method at all, so a
dependency slip would only have surfaced as an ``AttributeError`` at setup on
the live installation.

No Home Assistant install is needed. ``coordinator.py`` imports Home Assistant,
so the call itself is read out of the syntax tree rather than executed; the
behaviour it relies on is pinned against the library's own mock unit.
"""

from __future__ import annotations

import ast
from pathlib import Path

from modbus_connection import ModbusUnit
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest

COORDINATOR = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "lg_thermav_r290"
    / "coordinator.py"
)

CONFIG_FLOW = COORDINATOR.parent / "config_flow.py"

#: Mirrors ``coordinator._REQUEST_TIMEOUT``. Duplicated on purpose: the point of
#: these tests is to notice when that value changes, which a shared import would
#: defeat.
EXPECTED_TIMEOUT = 20.0

#: Any unit id does; the floor is per unit and resolved per link.
_UNIT_ID = 33


@pytest.fixture(name="unit")
def unit_fixture() -> MockModbusUnit:
    """A mock unit. Built here rather than through the library's pytest plugin,
    which this suite does not load -- there is no conftest to register it."""
    return MockModbusConnection().for_unit(_UNIT_ID)


@pytest.fixture(name="tree")
def tree_fixture() -> ast.Module:
    return ast.parse(COORDINATOR.read_text(encoding="utf-8"))


def _constant(tree: ast.Module, name: str) -> float:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not assigned in {COORDINATOR.name}")


def test_the_library_offers_a_timeout_floor() -> None:
    """Guards the dependency floor in the manifest.

    ``require_timeout`` arrived in modbus-connection 4.12.3. On 4.10.0 — which
    the Home Assistant 2026.9 line pins — the unit protocol does not carry it,
    and the integration cannot set up.
    """
    assert hasattr(ModbusUnit, "require_timeout")


def test_the_coordinator_asks_for_the_floor(tree: ast.Module) -> None:
    """The call has to be there, and it has to pass the named constant."""
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "require_timeout"
    ]
    assert len(calls) == 1, "expected exactly one timeout-floor request"

    (call,) = calls
    assert [a.id for a in call.args if isinstance(a, ast.Name)] == ["_REQUEST_TIMEOUT"]


def test_the_floor_is_the_documented_twenty_seconds(tree: ast.Module) -> None:
    assert _constant(tree, "_REQUEST_TIMEOUT") == EXPECTED_TIMEOUT


def test_the_connection_test_stays_below_the_floor() -> None:
    """The config form's own bound has to be shorter than the link's timeout.

    Taken over from isarrider's adoption of this change, which had the test and
    this repository did not. Without the relation the bound is decoration: the
    borrowed unit may land on a connection whose timeout the coordinator has
    already raised, and a form bounded at or above that value would sit there
    for the full wait anyway.
    """
    probe = _constant(
        ast.parse(CONFIG_FLOW.read_text(encoding="utf-8")), "_PROBE_TIMEOUT"
    )
    assert 0 < probe < EXPECTED_TIMEOUT


def test_the_floor_is_recorded_by_the_unit(unit: MockModbusUnit) -> None:
    """Pins the semantics the comment in ``coordinator.py`` relies on.

    The value is a floor the link resolves as a maximum over its units, not an
    assignment, and it can be withdrawn. Should the library ever turn it into a
    plain assignment, this is where it shows.
    """
    assert unit.required_timeout is None

    unit.require_timeout(EXPECTED_TIMEOUT)
    assert unit.required_timeout == EXPECTED_TIMEOUT

    unit.require_timeout(None)
    assert unit.required_timeout is None


def test_a_negative_floor_is_refused(unit: MockModbusUnit) -> None:
    with pytest.raises(ValueError):
        unit.require_timeout(-1)
