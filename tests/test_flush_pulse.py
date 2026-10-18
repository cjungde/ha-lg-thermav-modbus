"""The flush-pulse state machine, against the behaviour measured on the unit.

Every threshold in `flush_pulse.py` came out of 29 logged pulses over seven
days, and three of them were only found by getting them wrong first: the
inclusive comparison at 1500 rpm, a stop resetting the clock instead of pausing
it, and the ramp belonging to the pulse rather than to the run-up. Those three
are what these tests are mostly about.

No Home Assistant install is needed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


fp = _load("flush_pulse")

T0 = datetime(2026, 10, 18, 8, 0, 0, tzinfo=UTC)
#: The unit is polled every 10 s on this installation.
POLL = timedelta(seconds=10)


def _tracker(**kwargs):
    return fp.FlushPulseTracker(config=fp.FlushPulseConfig(**kwargs))


def _run(tracker, samples, start=T0, step=POLL):
    """Feed (rpm, kwargs) samples one poll apart; return (time, events) pairs."""
    seen = []
    now = start
    for sample in samples:
        rpm, extra = sample if isinstance(sample, tuple) else (sample, {})
        events = tracker.update(now, rpm, **extra)
        if events:
            seen.append((now, events))
        now += step
    return seen


def _hold(rpm, minutes, step=POLL):
    return [rpm] * int(minutes * 60 / step.total_seconds())


# --- the three details that cost time -----------------------------------


def test_exactly_1500_rpm_counts() -> None:
    """The unit sits at exactly 1500 for long stretches.

    With a `<` comparison those minutes never count and the pulse arrives as a
    surprise. This is the single most expensive mistake available here.
    """
    t = _tracker()
    _run(t, _hold(1500, 30))
    assert t.runtime_minutes is not None
    assert round(t.runtime_minutes) == 30


def test_a_stop_resets_the_clock_rather_than_pausing_it() -> None:
    """Measured intervals between pulses ran from 61 minutes to 23 hours.

    What counts is continuous running time in the band, so a stop must discard
    what was accumulated -- not resume from it.
    """
    t = _tracker()
    _run(t, _hold(1400, 40))
    assert round(t.runtime_minutes) == 40

    _run(t, [0], start=T0 + timedelta(minutes=40))
    assert t.runtime_minutes is None
    assert t.low_load_since is None

    _run(t, _hold(1400, 5), start=T0 + timedelta(minutes=41))
    assert round(t.runtime_minutes) == 5


def test_leaving_the_band_also_resets_the_clock() -> None:
    """Above 25 Hz the unit's own timer is not counting either."""
    t = _tracker()
    _run(t, _hold(1500, 20) + [1800] + _hold(1500, 3))
    assert round(t.runtime_minutes) == 3


def test_the_ramp_is_not_counted_as_run_up() -> None:
    """1140, 1680, 2280, 2880, 3600 -- the ramp belongs to the pulse.

    Attributing it to the low-load phase is what put the trigger at 60.0
    instead of 60.5 in the first analysis.
    """
    t = _tracker()
    events = _run(t, _hold(1500, 60) + [1140, 1680, 2280, 2880, 3600])
    kinds = [e for _, evs in events for e in evs]
    assert fp.EVENT_STARTED in kinds
    # 1680 already leaves the band, so the clock stopped before the pulse was
    # recognised; the runtime recorded with the pulse is the one at that point.
    assert t.pulse_active


# --- the trigger --------------------------------------------------------


def test_the_pulse_is_announced_before_it_arrives() -> None:
    """A warning that lands during the ramp is useless.

    The ramp is about 50 s, and anything that has to write to the machine first
    does not fit in that. Default lead is three minutes.
    """
    t = _tracker()
    events = _run(t, _hold(1500, 59))
    kinds = [e for _, evs in events for e in evs]
    assert kinds == [fp.EVENT_IMMINENT]

    ((fired_at, _),) = events
    assert round((fired_at - T0).total_seconds() / 60, 1) == 57.5


def test_the_announcement_is_made_once_not_every_poll() -> None:
    t = _tracker()
    events = _run(t, _hold(1500, 60))
    assert [e for _, evs in events for e in evs].count(fp.EVENT_IMMINENT) == 1


def test_a_reset_rearms_the_announcement() -> None:
    t = _tracker()
    _run(t, _hold(1500, 59) + [0])
    events = _run(t, _hold(1500, 59), start=T0 + timedelta(minutes=70))
    assert [e for _, evs in events for e in evs] == [fp.EVENT_IMMINENT]


def test_expected_time_is_the_measured_sixty_and_a_half_minutes() -> None:
    t = _tracker()
    _run(t, _hold(1500, 10))
    assert t.expected_at() == T0 + timedelta(minutes=60.5)
    # The last of 60 ten-second samples lands at 9:50, not 10:00, so the
    # remainder is one poll short of 50.5.
    assert round(t.minutes_remaining(), 1) == 50.7


# --- a whole pulse ------------------------------------------------------


def test_a_complete_pulse_is_recorded() -> None:
    t = _tracker()
    samples = _hold(1500, 60) + _hold(3600, 1) + [1500]
    events = _run(t, samples)
    kinds = [e for _, evs in events for e in evs]
    assert kinds == [fp.EVENT_IMMINENT, fp.EVENT_STARTED, fp.EVENT_FINISHED]

    record = t.last_pulse
    assert record is not None
    assert record.peak_rpm == 3600
    assert 40 <= record.duration_seconds <= 70
    assert not t.pulse_active


def test_the_runtime_before_the_pulse_is_kept_with_it() -> None:
    """The one number that says whether the mechanism still holds."""
    t = _tracker()
    _run(t, _hold(1500, 60) + _hold(3600, 1) + [1500])
    assert t.last_pulse.runtime_minutes is not None
    assert 55 <= t.last_pulse.runtime_minutes <= 65


# --- flush against defrost ----------------------------------------------


def test_a_defrost_is_not_reported_as_a_pulse() -> None:
    """Both run the compressor up; for two days in October that cost us two
    misreadings. The unit's own flag settles it."""
    t = _tracker()
    samples = (
        _hold(1500, 60)
        + [(4020, {"defrosting": True})] * 9
        + [(1500, {"defrosting": False})]
    )
    events = _run(t, samples)
    kinds = [e for _, evs in events for e in evs]
    assert fp.EVENT_STARTED not in kinds
    assert fp.EVENT_FINISHED not in kinds
    assert t.last_pulse is None


def test_a_late_defrost_flag_still_does_not_produce_a_pulse() -> None:
    """The flag can arrive a poll after the ramp. 4020 rpm alone is enough:
    a flush peaks at exactly 3600, a defrost at 4020-4080."""
    t = _tracker()
    samples = _hold(1500, 60) + [3600, 4020, (4080, {"defrosting": True}), 1500]
    _run(t, samples)
    assert t.last_pulse is None
    assert not t.pulse_active


def test_the_clock_restarts_after_a_defrost() -> None:
    t = _tracker()
    _run(t, _hold(1500, 60) + [(4020, {"defrosting": True})])
    _run(t, _hold(1500, 4), start=T0 + timedelta(minutes=62))
    assert round(t.runtime_minutes) == 4


# --- readings that are not observations ---------------------------------


def test_an_unreadable_poll_is_skipped_not_taken_as_a_stop() -> None:
    """A dropped Modbus read is not a compressor stop.

    Treating it as one resets a clock that is in fact still running, and the
    next pulse then arrives unannounced.
    """
    t = _tracker()
    _run(t, _hold(1500, 20) + [None, None] + _hold(1500, 1))
    assert round(t.runtime_minutes) == 21


def test_a_tank_charge_keeps_the_clock_running() -> None:
    """The unit's timer does not care what the heat is used for.

    Only the pulse's comparison against the heating curve becomes meaningless
    during a charge, which is a matter for whoever reads the record.
    """
    t = _tracker()
    _run(t, [(1500, {"dhw_heating": True})] * 120)
    assert round(t.runtime_minutes) == 20


def test_nothing_is_claimed_before_the_first_observation() -> None:
    t = _tracker()
    assert t.runtime_minutes is None
    assert t.expected_at() is None
    assert t.minutes_remaining() is None
    assert not t.pulse_active
    assert not t.low_load


# --- configurability ----------------------------------------------------


def test_the_lead_time_is_configurable() -> None:
    t = _tracker(lead_seconds=600)
    events = _run(t, _hold(1500, 55))
    ((fired_at, _),) = events
    assert round((fired_at - T0).total_seconds() / 60, 1) == 50.5
