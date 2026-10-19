"""The 20-second request timeout the coordinator asks the shared link for.

Taken over, with its tests, from cjungde's integration. The floor exists
because a slow answer from the heat pump must not be read as a dropped link: on
a shared connection a request can wait behind someone else's conversation. It
is one line in ``coordinator.py``, and without these tests nothing would catch
its removal, or a dependency slip back to ``modbus-connection`` 4.10.0, which
has no such method and would only fail with an ``AttributeError`` at setup.

No Home Assistant install is needed. ``coordinator.py`` imports Home Assistant,
so the call itself is read out of the syntax tree rather than executed; the
behaviour it relies on is pinned against the library's own mock unit. The
bound on the setup dialog's probes is read the same way from
``config_flow.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from modbus_connection import ModbusUnit
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest

COMPONENT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "lg_therma_v_r290"
)
COORDINATOR = COMPONENT / "coordinator.py"
CONFIG_FLOW = COMPONENT / "config_flow.py"

#: Mirrors ``coordinator._REQUEST_TIMEOUT``. Duplicated on purpose: the point of
#: these tests is to notice when that value changes, which a shared import would
#: defeat.
EXPECTED_TIMEOUT = 20.0

#: Any unit id does; the floor is per unit and resolved per link.
_UNIT_ID = 1


@pytest.fixture(name="unit")
def unit_fixture() -> MockModbusUnit:
    """A mock unit, built directly rather than through the library's plugin."""
    return MockModbusConnection().for_unit(_UNIT_ID)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _constant(tree: ast.Module, name: str) -> float:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not assigned")


def test_the_library_offers_a_timeout_floor() -> None:
    """Guards the dependency floor in the manifest and the test requirements.

    ``require_timeout`` arrived in modbus-connection 4.12.3. On 4.10.0, which
    the Home Assistant 2026.9 line pins, the unit protocol does not carry it,
    and the integration cannot set up.
    """
    assert hasattr(ModbusUnit, "require_timeout")


def test_the_coordinator_asks_for_the_floor() -> None:
    """The call has to be there, once, and it has to pass the named constant."""
    calls = [
        node
        for node in ast.walk(_tree(COORDINATOR))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "require_timeout"
    ]
    assert len(calls) == 1, "expected exactly one timeout-floor request"

    (call,) = calls
    assert [a.id for a in call.args if isinstance(a, ast.Name)] == ["_REQUEST_TIMEOUT"]


def test_the_floor_is_the_documented_twenty_seconds() -> None:
    assert _constant(_tree(COORDINATOR), "_REQUEST_TIMEOUT") == EXPECTED_TIMEOUT


def test_the_dialogs_wait_less_than_the_floor() -> None:
    """The setup and options probes are bounded below the link timeout, or a
    dialog on a shared link would inherit the 20 s per check."""
    assert _constant(_tree(CONFIG_FLOW), "_PROBE_TIMEOUT") < EXPECTED_TIMEOUT


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
