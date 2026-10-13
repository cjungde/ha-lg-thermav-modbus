"""Compressor starts, run time and average speed (compressor_stats.py).

compressor_stats.py imports nothing from Home Assistant, so none of this needs
an install.
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


cs = _load("compressor_stats")
DAY = "2026-10-13"


def _run(stats, samples, day=DAY):
    for on, rpm, time_s in samples:
        stats.add(on, rpm, time_s, day)


def test_starts_run_time_and_average_speed() -> None:
    stats = cs.CompressorStats()
    _run(
        stats,
        [
            (False, 0, 0),
            (True, 1800, 10),  # start 1
            (True, 2400, 70),  # 60 s at 1800
            (False, 0, 130),  # 60 s at 2400, stop
            (False, 0, 190),
            (True, 3000, 250),  # start 2
            (False, 0, 280),  # 30 s at 3000
        ],
    )
    assert stats.starts == 2
    assert stats.run_s == 150
    # (60 × 1800 + 60 × 2400 + 30 × 3000) / 150 = 2280
    assert stats.average_rpm_today == 2280
    assert stats.last_run_s == 30


def test_a_restart_or_first_poll_is_no_start() -> None:
    stats = cs.CompressorStats()
    _run(stats, [(True, 2000, 0), (True, 2000, 10)])
    assert stats.starts == 0
    assert stats.run_s == 10


def test_unknown_and_gaps_are_not_counted() -> None:
    stats = cs.CompressorStats()
    _run(
        stats,
        [
            (False, 0, 0),
            (None, None, 10),  # unit did not answer
            (True, 2000, 20),  # off -> unknown -> on: not a counted start
            (True, 2000, 20 + cs.MAX_GAP_S + 1),  # Home Assistant was down
        ],
    )
    assert stats.starts == 0
    assert stats.run_s == 0


def test_average_speed_resets_at_midnight() -> None:
    stats = cs.CompressorStats()
    _run(stats, [(True, 2000, 0), (True, 2000, 60)], day="2026-10-12")
    assert stats.average_rpm_today == 2000
    # The first poll of the new day closes the interval across midnight,
    # which counts to the new day: 60 s at the 2000 rpm seen before.
    stats.add(True, 3000, 120, "2026-10-13")
    assert stats.average_rpm_today == 2000
    assert stats.run_s == 120  # run time keeps counting
    stats.add(True, 3000, 180, "2026-10-13")
    assert stats.average_rpm_today == 2500  # (60 × 2000 + 60 × 3000) / 120


def test_restore_continues_and_keeps_only_todays_average() -> None:
    old = cs.CompressorStats()
    _run(old, [(False, 0, 0), (True, 2000, 10), (False, 0, 70)])
    saved = old.state()

    same_day = cs.CompressorStats()
    same_day.add(False, 0, 0, DAY)
    same_day.restore(saved)
    assert same_day.starts == 1
    assert same_day.run_s == 60
    assert same_day.average_rpm_today == 2000

    next_day = cs.CompressorStats()
    next_day.add(False, 0, 0, "2026-10-14")
    next_day.restore(saved)
    assert next_day.starts == 1
    assert next_day.average_rpm_today is None  # yesterday's average is gone
