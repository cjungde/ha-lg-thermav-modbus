"""Repairing temperature history recorded before temperatures were read signed.

Until 2.2.2 (#90) every temperature below 0 °C was read as an unsigned word
and recorded as 6553.6 °C higher than it was: -4.7 °C became 6548.9 °C. Until
2.2.3 (#92) an input without a sensor was recorded as 6488.7 °C. Both live in
Home Assistant's recorder, in two forms:

* **States**, every value with its time (kept ``purge_keep_days``, 10 days by
  default). Each one is repaired exactly: 6548.9 -> -4.7; 6488.7 -> unknown.
* **Statistics**, per hour (kept for good) and per 5 minutes (10 days): mean,
  min and max of the period. A period with a spike cannot be repaired from
  its three numbers alone -- the mean of a mixed hour does not tell how many
  values were spikes. So it is **recalculated from the repaired states**,
  the way the recorder calculates it, while those states still exist. A period
  whose values were *all* below zero is repaired exactly without them (every
  value was shifted by the same amount, so mean, min and max are too). What
  remains -- a mixed period whose states are gone -- cannot be recovered; it
  is reported, and removed only when asked.

Only values above 3276.7 °C are touched: no temperature of the unit comes near
it (the hot gas peaks around 100 °C), and the largest word read signed is
3276.7, so anything above can only come from the unsigned read.

Deliberately free of Home Assistant imports: the planning is tested without a
Home Assistant install; services.py loads the rows and applies the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: What the unsigned read added to a negative temperature (65536 tenths).
OFFSET = 6553.6
#: Above this a recorded temperature can only come from the unsigned read.
LIMIT = 3276.7
#: A temperature input without a sensor, read unsigned (decode.NO_SENSOR).
NO_SENSOR = 6488.7

#: Statistics tables and the length of their periods, in seconds.
HOUR = 3600.0
FIVE_MINUTES = 300.0


def _number(state: str | None) -> float | None:
    try:
        return float(state)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def repaired(value: float) -> float | None:
    """The value as it was meant: None for an input without a sensor."""
    if round(value, 1) == NO_SENSOR:
        return None
    if value > LIMIT:
        return round(value - OFFSET, 1)
    return value


def state_text(value: float | None) -> str:
    """How the repaired value is stored as a state."""
    return "unknown" if value is None else str(round(value, 1))


@dataclass(frozen=True)
class StatRow:
    """One row of a statistics table: id, start and the three numbers."""

    id: int
    start_ts: float
    mean: float | None
    min: float | None
    max: float | None


@dataclass
class TablePlan:
    """What happens to one statistics table of one entity."""

    recalculated: list[tuple[int, float, float, float]] = field(default_factory=list)
    shifted: list[tuple[int, float | None, float | None, float | None]] = field(
        default_factory=list
    )
    removed_no_sensor: list[int] = field(default_factory=list)
    unrecoverable: list[int] = field(default_factory=list)
    removed_unrecoverable: list[int] = field(default_factory=list)

    @property
    def updates(self) -> list[tuple[int, float | None, float | None, float | None]]:
        return [*self.recalculated, *self.shifted]

    @property
    def deletes(self) -> list[int]:
        return [*self.removed_no_sensor, *self.removed_unrecoverable]

    def summary(self) -> dict[str, int]:
        return {
            "recalculated": len(self.recalculated),
            "shifted": len(self.shifted),
            "removed_no_sensor": len(self.removed_no_sensor),
            "unrecoverable": len(self.unrecoverable),
            "removed_unrecoverable": len(self.removed_unrecoverable),
        }


@dataclass
class EntityPlan:
    """Everything that changes for one entity."""

    states: list[tuple[int, str]] = field(default_factory=list)
    hourly: TablePlan = field(default_factory=TablePlan)
    five_minute: TablePlan = field(default_factory=TablePlan)

    @property
    def empty(self) -> bool:
        return not (
            self.states
            or self.hourly.updates
            or self.hourly.deletes
            or self.hourly.unrecoverable
            or self.five_minute.updates
            or self.five_minute.deletes
            or self.five_minute.unrecoverable
        )

    def summary(self) -> dict[str, object]:
        return {
            "states": len(self.states),
            "hourly": self.hourly.summary(),
            "five_minute": self.five_minute.summary(),
        }


def period_statistics(
    points: list[tuple[float, float | None]], start: float, end: float
) -> tuple[float, float, float] | None:
    """Time-weighted mean, min and max over [start, end), like the recorder.

    ``points`` are (time, value) sorted by time, value None where the state was
    not a number. As in the recorder, only numbers count: the last number
    before ``start`` holds from ``start`` on, each number holds until the next
    one, and a non-number in between does not end it. None when no number
    holds at any time in the period.
    """
    numbers = [(t, v) for t, v in points if v is not None]
    held: list[tuple[float, float]] = []
    before = [p for p in numbers if p[0] <= start]
    if before:
        held.append((start, before[-1][1]))
    held.extend(p for p in numbers if start < p[0] < end)
    if not held:
        return None
    total = 0.0
    weighted = 0.0
    for index, (time, value) in enumerate(held):
        until = held[index + 1][0] if index + 1 < len(held) else end
        weighted += value * (until - time)
        total += until - time
    values = [v for _, v in held]
    mean = weighted / total if total > 0 else values[-1]
    return mean, min(values), max(values)


def plan_table(
    points: list[tuple[float, float | None]],
    earliest_state: float | None,
    rows: list[StatRow],
    period: float,
    *,
    remove_unrecoverable: bool,
) -> TablePlan:
    """Decide for each damaged row of one statistics table."""
    plan = TablePlan()
    for row in rows:
        if row.max is None or row.max <= LIMIT:
            continue
        if earliest_state is not None and earliest_state <= row.start_ts:
            result = period_statistics(points, row.start_ts, row.start_ts + period)
            if result is None:
                plan.removed_no_sensor.append(row.id)
            else:
                plan.recalculated.append((row.id, *result))
            continue
        if row.min is not None and row.min > LIMIT:
            if round(row.min, 1) == NO_SENSOR and round(row.max, 1) == NO_SENSOR:
                plan.removed_no_sensor.append(row.id)
            else:
                plan.shifted.append(
                    (
                        row.id,
                        None if row.mean is None else row.mean - OFFSET,
                        row.min - OFFSET,
                        row.max - OFFSET,
                    )
                )
            continue
        plan.unrecoverable.append(row.id)
        if remove_unrecoverable:
            plan.removed_unrecoverable.append(row.id)
    return plan


def plan_entity(
    states: list[tuple[int, float, str | None]],
    hourly: list[StatRow],
    five_minute: list[StatRow],
    *,
    remove_unrecoverable: bool = False,
) -> EntityPlan:
    """The whole repair of one entity.

    ``states`` are (state id, time, state) sorted by time: all states the
    recorder still has for the entity, so the statistics can be recalculated
    from them, damaged or not.
    """
    plan = EntityPlan()
    points: list[tuple[float, float | None]] = []
    for state_id, time, text in states:
        value = _number(text)
        if value is not None and value > LIMIT:
            value = repaired(value)
            plan.states.append((state_id, state_text(value)))
        points.append((time, value))
    earliest = states[0][1] if states else None
    plan.hourly = plan_table(
        points, earliest, hourly, HOUR, remove_unrecoverable=remove_unrecoverable
    )
    plan.five_minute = plan_table(
        points,
        earliest,
        five_minute,
        FIVE_MINUTES,
        remove_unrecoverable=remove_unrecoverable,
    )
    return plan
