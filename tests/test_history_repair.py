"""Planning the repair of recorded temperatures (history_repair.py).

history_repair.py imports nothing from Home Assistant, so none of this needs
an install. The recorder side is tested in tests_ha/test_history_repair.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "lg_therma_v_r290"
    / "history_repair.py"
)
_spec = importlib.util.spec_from_file_location("history_repair_under_test", PATH)
hr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = hr  # dataclasses look their module up
_spec.loader.exec_module(hr)

H = 3600.0
T0 = 1_000_000 * H  # the start of an hour


def test_a_spike_is_the_real_value_plus_6553_6() -> None:
    assert hr.repaired(6548.9) == -4.7
    assert hr.repaired(6553.4) == -0.2
    assert hr.repaired(6540.0) == -13.6
    assert hr.repaired(21.5) == 21.5  # untouched


def test_an_input_without_a_sensor_becomes_unknown() -> None:
    assert hr.repaired(6488.7) is None
    assert hr.state_text(None) == "unknown"
    assert hr.state_text(-4.7) == "-4.7"


def test_the_recorders_time_weighted_mean() -> None:
    # 3.0 from before the hour for 30 min, then 5.0 for 30 min.
    points = [(T0 - 100, 3.0), (T0 + 1800, 5.0)]
    assert hr.period_statistics(points, T0, T0 + H) == (4.0, 3.0, 5.0)


def test_non_numbers_do_not_end_a_value() -> None:
    points = [(T0 - 100, 3.0), (T0 + 1800, None)]
    assert hr.period_statistics(points, T0, T0 + H) == (3.0, 3.0, 3.0)


def test_nothing_held_means_no_statistics() -> None:
    assert hr.period_statistics([(T0 + 10, None)], T0, T0 + H) is None


def _states(*values):
    """States every 10 minutes from the start of the hour, ids 1, 2, ..."""
    return [(i + 1, T0 + i * 600, v) for i, v in enumerate(values)]


def test_a_mixed_hour_is_recalculated_from_the_repaired_states() -> None:
    """The case from the suction temperature: a short dip below 0 °C."""
    states = _states("3.0", "6548.9", "3.0", "3.0", "3.0", "3.0")
    damaged = hr.StatRow(10, T0, 1093.9, 3.0, 6548.9)
    plan = hr.plan_entity(states, [damaged], [])
    assert plan.states == [(2, "-4.7")]
    ((row_id, mean, low, high),) = plan.hourly.recalculated
    assert row_id == 10
    assert mean == pytest.approx((5 * 3.0 - 4.7) / 6)
    assert (low, high) == (-4.7, 3.0)


def test_healthy_rows_are_left_alone() -> None:
    plan = hr.plan_entity(_states("3.0"), [hr.StatRow(10, T0, 3.0, 3.0, 3.0)], [])
    assert plan.empty


def test_an_hour_entirely_below_zero_is_shifted_without_states() -> None:
    """Every value moved by the same amount, so mean, min and max did too."""
    plan = hr.plan_entity([], [hr.StatRow(10, T0, 6550.0, 6548.0, 6552.0)], [])
    ((row_id, mean, low, high),) = plan.hourly.shifted
    assert row_id == 10
    assert mean == pytest.approx(-3.6)
    assert low == pytest.approx(-5.6)
    assert high == pytest.approx(-1.6)


def test_a_mixed_hour_without_states_cannot_be_recovered() -> None:
    row = hr.StatRow(10, T0, 1093.9, 3.0, 6548.9)
    plan = hr.plan_entity([], [row], [])
    assert plan.hourly.unrecoverable == [10]
    assert plan.hourly.deletes == []
    plan = hr.plan_entity([], [row], [], remove_unrecoverable=True)
    assert plan.hourly.deletes == [10]


def test_states_starting_inside_the_hour_are_not_enough() -> None:
    """Purged up to mid-hour: the start of the hour is unknown."""
    states = [(1, T0 + 1800, "3.0")]
    plan = hr.plan_entity(states, [hr.StatRow(10, T0, 1093.9, 3.0, 6548.9)], [])
    assert plan.hourly.unrecoverable == [10]


def test_no_sensor_hours_are_removed() -> None:
    """Flow Temperature Circuit 2 without a second circuit: no temperature."""
    rows = [hr.StatRow(10, T0, 6488.7, 6488.7, 6488.7)]
    with_states = hr.plan_entity(_states("6488.7", "6488.7"), rows, [])
    assert with_states.states == [(1, "unknown"), (2, "unknown")]
    assert with_states.hourly.removed_no_sensor == [10]
    without_states = hr.plan_entity([], rows, [])
    assert without_states.hourly.removed_no_sensor == [10]


def test_five_minute_periods_are_handled_like_hours() -> None:
    states = _states("3.0", "6548.9")
    rows = [
        hr.StatRow(20, T0, 3.0, 3.0, 3.0),
        hr.StatRow(21, T0 + 600, 6548.9, 6548.9, 6548.9),
    ]
    plan = hr.plan_entity(states, [], rows)
    assert plan.five_minute.recalculated == [(21, -4.7, -4.7, -4.7)]


def test_summary() -> None:
    states = _states("3.0", "6548.9")
    plan = hr.plan_entity(states, [hr.StatRow(10, T0, 1093.9, 3.0, 6548.9)], [])
    assert plan.summary() == {
        "states": 1,
        "hourly": {
            "recalculated": 1,
            "shifted": 0,
            "removed_no_sensor": 0,
            "unrecoverable": 0,
            "removed_unrecoverable": 0,
        },
        "five_minute": {
            "recalculated": 0,
            "shifted": 0,
            "removed_no_sensor": 0,
            "unrecoverable": 0,
            "removed_unrecoverable": 0,
        },
    }
