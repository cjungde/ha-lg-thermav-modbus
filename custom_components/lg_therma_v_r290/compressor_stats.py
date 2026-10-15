"""Compressor starts, run time and average speed, from data already polled.

Counted from the Compressor discrete input (10004) and Compressor Speed
(input 30025) on every poll; nothing extra is read from the unit. With the
Compressor statistics option, three sensors show them:

- Compressor Starts: off-to-on changes, a total counter (starts per day or
  per hour come from Home Assistant's statistics). Many short runs mean the
  unit is cycling, which costs efficiency and wear.
- Compressor Run Time: hours the compressor ran, a total counter.
- Compressor Average Speed: rpm while running, today (reset at local
  midnight), so it can be compared day by day. Standstill is left out, or the
  value would measure how often it runs, not how hard.

Every poll counts the state seen at the previous poll over the time since
(left Riemann sum), like the energy integration in external_meter.py. The
interval that crosses midnight counts to the new day (at most one poll
interval). A gap
longer than MAX_GAP_S is not counted, and a start is only counted between two
polls that are both known, so a restart never adds one.

Deliberately free of Home Assistant imports so it can be tested without a
Home Assistant install, like energy.py.
"""

from __future__ import annotations

from typing import Any

# Entity keys (docs/naming.md).
KEY_COMPRESSOR_STARTS = "compressor_starts"
KEY_COMPRESSOR_RUN_TIME = "compressor_run_time"
KEY_COMPRESSOR_AVERAGE_SPEED = "compressor_average_speed"
KEYS = (KEY_COMPRESSOR_STARTS, KEY_COMPRESSOR_RUN_TIME, KEY_COMPRESSOR_AVERAGE_SPEED)

MAX_GAP_S = 300.0


class CompressorStats:
    """The running counts, fed one poll at a time."""

    def __init__(self) -> None:
        self.starts = 0
        self.run_s = 0.0
        # Today, for the average speed: the day, seconds running, rpm × s.
        self.day: str | None = None
        self.day_run_s = 0.0
        self.day_rpm_s = 0.0
        # The run in progress, or the last one: its duration in seconds.
        self.last_run_s: float | None = None
        self._on: bool | None = None
        self._rpm: float | None = None
        self._time_s: float | None = None
        self._run_started_s: float | None = None

    def add(self, on: bool | None, rpm: float | None, time_s: float, day: str) -> None:
        """Record one poll: compressor on/off (None: unknown), speed, time, day."""
        if day != self.day:
            self.day = day
            self.day_run_s = 0.0
            self.day_rpm_s = 0.0
        elapsed = (
            time_s - self._time_s
            if self._time_s is not None and self._on is not None
            else None
        )
        if elapsed is not None and 0 < elapsed <= MAX_GAP_S:
            if self._on:
                self.run_s += elapsed
                self.day_run_s += elapsed
                if self._rpm is not None:
                    self.day_rpm_s += self._rpm * elapsed
            if on and not self._on:
                self.starts += 1
                self._run_started_s = time_s
        # The run in progress grows with every poll; a stop fixes its length.
        if self._run_started_s is not None and (on or self._on):
            self.last_run_s = time_s - self._run_started_s
        if not on:
            self._run_started_s = None
        self._on = on
        self._rpm = rpm if on else None
        self._time_s = time_s

    @property
    def run_hours(self) -> float:
        return self.run_s / 3600

    @property
    def average_rpm_today(self) -> int | None:
        """Average speed while running today, or None before the first run."""
        if self.day_run_s <= 0:
            return None
        return int(round(self.day_rpm_s / self.day_run_s))

    def restore(self, data: dict[str, Any]) -> None:
        """Continue from what a previous run stored (see state())."""
        self.starts = int(data.get("starts") or 0)
        self.run_s = float(data.get("run_s") or 0.0)
        if data.get("day") is not None and self.day in (None, data["day"]):
            self.day = data["day"]
            self.day_run_s += float(data.get("day_run_s") or 0.0)
            self.day_rpm_s += float(data.get("day_rpm_s") or 0.0)
        self.last_run_s = data.get("last_run_s")

    def state(self) -> dict[str, Any]:
        return {
            "starts": self.starts,
            "run_s": self.run_s,
            "day": self.day,
            "day_run_s": self.day_run_s,
            "day_rpm_s": self.day_rpm_s,
            "last_run_s": self.last_run_s,
        }
