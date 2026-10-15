"""COP against an electricity meter of the user's own choosing.

The electrical figures the unit reports run high against a separate meter
(README, energy registers), so COPs built on them come out too low. With the
External electricity meter option, the user picks Home Assistant sensors of
their own meter, and the integration computes:

- COP (External Meter): thermal power from flow rate × ΔT over the meter's
  power, the COP of the moment
- Thermal Energy (Calculated): that thermal power added up over time, a kWh
  counter independent of the unit's counters
- COP Cumulative (External Meter): thermal energy over the meter's energy,
  both counted from the moment the option was set up: the seasonal
  performance factor (JAZ) over that period

Deliberately free of Home Assistant imports so the arithmetic can be tested
without a Home Assistant install, like cop.py.
"""

from __future__ import annotations

from typing import Any

# Entity keys (docs/naming.md).
KEY_COP_EXTERNAL_METER = "cop_external_meter"
KEY_THERMAL_ENERGY_CALCULATED = "thermal_energy_calculated"
KEY_COP_CUMULATIVE_EXTERNAL_METER = "cop_cumulative_external_meter"
POWER_KEYS = (KEY_COP_EXTERNAL_METER,)
ENERGY_KEYS = (KEY_THERMAL_ENERGY_CALCULATED, KEY_COP_CUMULATIVE_EXTERNAL_METER)

# Longer than this between two samples (Home Assistant was down, the unit
# did not answer) and the interval is not counted: nothing is known about
# the power in between, and a guess would be worse than a gap.
MAX_GAP_S = 300.0


class EnergyIntegrator:
    """Adds up a power over time into kWh, sample by sample.

    Each sample counts the previous power over the time since it (left
    Riemann sum): with a poll every 10 s, the error is that of the poll
    interval, not of the integration. A gap longer than MAX_GAP_S is skipped.
    """

    def __init__(self, kwh: float = 0.0) -> None:
        self.kwh = kwh
        self._last_power_w: float | None = None
        self._last_time_s: float | None = None

    def add(self, power_w: float | None, time_s: float) -> float:
        """Record a sample (None: unknown power); returns the total in kWh."""
        if (
            self._last_power_w is not None
            and self._last_time_s is not None
            and 0 < time_s - self._last_time_s <= MAX_GAP_S
        ):
            self.kwh += self._last_power_w * (time_s - self._last_time_s) / 3_600_000
        self._last_power_w = power_w
        self._last_time_s = time_s
        return self.kwh


class CounterDelta:
    """How much a total counter has grown since the first reading.

    Only increases count. A counter that goes down was reset (a new meter, a
    counter rolled over): its new value is counted as growth from zero, the
    way Home Assistant treats a total_increasing sensor.
    """

    def __init__(self, kwh: float = 0.0, last: float | None = None) -> None:
        self.kwh = kwh
        self.last = last

    def add(self, value: float | None) -> float:
        """Record a counter reading (None: unknown); returns the growth."""
        if value is None:
            return self.kwh
        if self.last is not None:
            self.kwh += value - self.last if value >= self.last else value
        self.last = value
        return self.kwh


def ratio(thermal: float | None, electrical: float | None) -> float | None:
    """thermal / electrical, rounded, or None while either is missing or 0."""
    if thermal is None or electrical is None or electrical <= 0:
        return None
    return round(thermal / electrical, 2)


def state(integrator: EnergyIntegrator, delta: CounterDelta | None) -> dict[str, Any]:
    """What a restart needs to continue counting."""
    result: dict[str, Any] = {"thermal_kwh": integrator.kwh}
    if delta is not None:
        result["electrical_kwh"] = delta.kwh
        result["electrical_last"] = delta.last
    return result
