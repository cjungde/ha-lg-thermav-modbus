"""The oil-return flush pulse: when it comes, when it is running, when it is over.

Every so often the unit runs the compressor up to 60 Hz for about a minute. It
is returning oil from the refrigerant circuit to the compressor, and it is
normal -- but it ends a heating run, so it looks like short cycling to anyone
watching the compressor, and it is the one event an outside controller wants to
know about in advance.

THE TRIGGER, measured rather than assumed. On a HN1639HC NK0 over seven days,
29 pulses: the unit flushes after **60.5 minutes of uninterrupted running at or
below 25 Hz** (1500 rpm). All 29 fell in the 55-65 minute band, median 60.3, and
24 of 24 long low-load phases ended in a pulse with none skipped. Three details
cost time to find:

* The threshold is **inclusive**. The unit sits at exactly 1500 rpm for long
  stretches, and a `<` comparison never sees those minutes.
* **A compressor stop resets the clock**, it does not pause it. The time is
  continuous running time in the band, not time of day: measured intervals
  between pulses ranged from 61 minutes to 23 hours, median 124.
* The ramp up (1140, 1680, 2280, 2880, 3600 rpm, about 10 s per step) belongs
  to the pulse. Counting it as part of the run-up puts the trigger at 60.0.

A second account agrees on the threshold from a different direction: a forum
post gives "below 25 Hz for longer than 60 minutes", unsourced. 25 Hz is 1500
rpm, so the two readings are the same rule.

TELLING A FLUSH FROM A DEFROST. Both run the compressor up, and for two days in
October 2026 that cost us two misreadings. They separate cleanly on two
independent signals:

| | flush pulse | defrost |
|---|---|---|
| peak | **exactly 3600 rpm** (60.0 Hz) | 4020-4080 rpm (67-68 Hz) |
| length | 40-60 s | about 90 s |

The peak being exactly 3600 on every day a pulse occurs, never 3580 or 3620,
says 60 Hz is a setpoint of the routine rather than an incidental maximum. The
unit's own defrost flag settles it regardless, and is what this module uses;
the numbers above are the fallback when the flag is late, which it can be by
one poll.

Deliberately free of Home Assistant imports, like connection.py and
experimental.py, so the state machine can be tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

#: Event payload values. The integration fires one event type and distinguishes
#: by `type`, which is what device triggers are built on.
EVENT_IMMINENT = "flush_pulse_imminent"
EVENT_STARTED = "flush_pulse_started"
EVENT_FINISHED = "flush_pulse_finished"


@dataclass(frozen=True)
class FlushPulseConfig:
    """Thresholds, all measured. Changing one invalidates the figures above."""

    #: Upper bound of the low-load band, inclusive. 1500 rpm = 25 Hz.
    low_load_rpm: int = 1500
    #: Uninterrupted minutes in that band before the unit flushes.
    trigger_minutes: float = 60.5
    #: How early the imminent event fires. The ramp alone is about 50 s, which
    #: is too late for anything that has to talk to the machine first: a Modbus
    #: write plus the unit's reaction does not fit in it.
    lead_seconds: int = 180
    #: Above this the compressor is ramping, not modulating.
    pulse_rpm: int = 2900
    #: Above this it is not a flush. Only used when the defrost flag is late.
    defrost_rpm: int = 3700


@dataclass(frozen=True)
class PulseRecord:
    """What one completed pulse looked like."""

    started: datetime
    ended: datetime
    peak_rpm: int
    #: Running time in the low-load band before it, in minutes. `None` when the
    #: clock was not running long enough to be meaningful -- after a restart,
    #: for instance, where the unit's own timer kept running and ours did not.
    runtime_minutes: float | None

    @property
    def duration_seconds(self) -> float:
        """40-60 s for a flush. A defrost runs about 90 s and is not recorded here."""
        return (self.ended - self.started).total_seconds()


@dataclass
class FlushPulseTracker:
    """Follows the compressor and says where in the cycle the unit is.

    Fed once per poll. Returns the events that the poll caused, so the caller
    does not have to diff states to find them.

    After a Home Assistant restart the clock starts from zero, because nothing
    in the unit reports how long it has already been in the band. The device's
    own timer keeps running, so the first pulse after a restart can arrive
    earlier than predicted. That is reported as `runtime_minutes = None` rather
    than as a wrong number -- the same choice the YAML version made when it
    left its forecast columns empty.
    """

    config: FlushPulseConfig = field(default_factory=FlushPulseConfig)

    low_load_since: datetime | None = None
    #: Set when a pulse is running. Also the marker for "we are in a pulse".
    pulse_started: datetime | None = None
    pulse_peak_rpm: int = 0
    #: Running time in the band at the moment the pulse began.
    pulse_runtime_minutes: float | None = None
    last_pulse: PulseRecord | None = None
    #: Guards against re-announcing the same approach on every poll.
    _imminent_fired: bool = False
    #: True while a ramp is attributed to defrosting rather than flushing.
    _in_defrost: bool = False

    # -- what the entities read ------------------------------------------

    @property
    def runtime_minutes(self) -> float | None:
        """Uninterrupted running time in the low-load band."""
        return self._runtime_at(self._now) if self.low_load_since else None

    @property
    def pulse_active(self) -> bool:
        return self.pulse_started is not None

    @property
    def low_load(self) -> bool:
        return self.low_load_since is not None

    _now: datetime | None = None

    def _runtime_at(self, now: datetime | None) -> float | None:
        if self.low_load_since is None or now is None:
            return None
        return max(0.0, (now - self.low_load_since).total_seconds() / 60)

    def expected_at(self) -> datetime | None:
        """When the unit is expected to flush, or None if the clock is not running."""
        if self.low_load_since is None:
            return None
        return self.low_load_since + timedelta(minutes=self.config.trigger_minutes)

    def minutes_remaining(self) -> float | None:
        runtime = self.runtime_minutes
        if runtime is None:
            return None
        return max(0.0, self.config.trigger_minutes - runtime)

    # -- being fed -------------------------------------------------------

    def update(
        self,
        now: datetime,
        rpm: int | float | None,
        *,
        defrosting: bool = False,
        dhw_heating: bool = False,
    ) -> tuple[str, ...]:
        """Take one observation and return the events it caused.

        `rpm` of None means the value was not readable this poll. That is not a
        compressor stop: treating it as one would reset a clock that is in fact
        still running, so the observation is skipped entirely.
        """
        self._now = now
        if rpm is None:
            return ()

        rpm = int(rpm)
        events: list[str] = []

        if self.pulse_started is not None:
            self.pulse_peak_rpm = max(self.pulse_peak_rpm, rpm)
            if defrosting or self.pulse_peak_rpm > self.config.defrost_rpm:
                # Not a flush after all. The unit's flag can arrive a poll late,
                # so this can happen mid-ramp; drop the pulse without reporting
                # one, and let the clock restart from the end of the ramp.
                self._in_defrost = True
                self._abandon_pulse()
                return ()
            if rpm <= self.config.pulse_rpm:
                events.append(EVENT_FINISHED)
                self.last_pulse = PulseRecord(
                    started=self.pulse_started,
                    ended=now,
                    peak_rpm=self.pulse_peak_rpm,
                    runtime_minutes=self.pulse_runtime_minutes,
                )
                self._clear_pulse()
                # The clock restarts only once the compressor is back in the
                # band, which the next poll decides.
            return tuple(events)

        if rpm > self.config.pulse_rpm:
            if defrosting or self._in_defrost or rpm > self.config.defrost_rpm:
                self._in_defrost = True
                self.low_load_since = None
                self._imminent_fired = False
                return ()
            self.pulse_started = now
            self.pulse_peak_rpm = rpm
            self.pulse_runtime_minutes = self._runtime_at(now)
            self.low_load_since = None
            self._imminent_fired = False
            events.append(EVENT_STARTED)
            return tuple(events)

        self._in_defrost = False

        if rpm == 0:
            # A stop resets the clock rather than pausing it.
            self.low_load_since = None
            self._imminent_fired = False
            return ()

        if rpm > self.config.low_load_rpm:
            # Running, but out of the band: the unit's timer is not counting.
            self.low_load_since = None
            self._imminent_fired = False
            return ()

        # In the band. Note the inclusive comparison above: the unit sits at
        # exactly 1500 for long stretches.
        if dhw_heating:
            # A tank charge drives the flow above 50 C and the pulse is not
            # counted against the heating curve, but the compressor is still
            # running in the band and the unit's timer does not care. Keep
            # counting; only the classification of the pulse differs.
            pass

        if self.low_load_since is None:
            self.low_load_since = now
            self._imminent_fired = False
            return ()

        remaining = self.minutes_remaining()
        if (
            not self._imminent_fired
            and remaining is not None
            and remaining * 60 <= self.config.lead_seconds
        ):
            self._imminent_fired = True
            events.append(EVENT_IMMINENT)
        return tuple(events)

    # -- internals -------------------------------------------------------

    def _clear_pulse(self) -> None:
        self.pulse_started = None
        self.pulse_peak_rpm = 0
        self.pulse_runtime_minutes = None

    def _abandon_pulse(self) -> None:
        self._clear_pulse()
        self.low_load_since = None
        self._imminent_fired = False
