"""Repairing recorded temperatures, against the real recorder (SQLite)."""

from __future__ import annotations

from homeassistant.components.recorder.db_schema import (
    States,
    StatesMeta,
    Statistics,
    StatisticsMeta,
    StatisticsShortTerm,
)
from homeassistant.helpers.recorder import get_instance, session_scope
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from sqlalchemy import select

from .test_config_flow import DOMAIN
from .test_setup import _set_up

SUCTION = "sensor.lg_therma_v_r290_suction_temperature"
FLOW_2 = "sensor.lg_therma_v_r290_flow_temperature_circuit_2"
H = 3600.0


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """The recorder has to start before Home Assistant (see conftest.py)."""
    yield


def _hour(days_back: int) -> float:
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    return now.timestamp() - days_back * 86400


async def _run_in_db(hass, job):
    def run():
        with session_scope(hass=hass) as session:
            return job(session)

    return await get_instance(hass).async_add_executor_job(run)


def _metadata(session, entity_id: str) -> tuple[int, int]:
    metadata_id = session.execute(
        select(StatesMeta.metadata_id).where(StatesMeta.entity_id == entity_id)
    ).scalar()
    if metadata_id is None:
        meta = StatesMeta(entity_id=entity_id)
        session.add(meta)
        session.flush()
        metadata_id = meta.metadata_id
    statistics = StatisticsMeta(
        statistic_id=entity_id,
        source="recorder",
        unit_of_measurement="°C",
        unit_class="temperature",
        has_mean=True,
        has_sum=False,
        mean_type=1,
    )
    session.add(statistics)
    session.flush()
    return metadata_id, statistics.id


async def _record_history(hass) -> dict[str, float]:
    """What 2.2.1 recorded: a dip to -4.7 °C read as 6548.9 °C, and more."""
    mixed = _hour(2)  # states still there
    negative = _hour(3) - 2 * 86400  # all below zero, states purged
    lost = _hour(3) - 3 * 86400  # mixed, states purged

    def write(session):
        metadata_id, statistics_id = _metadata(session, SUCTION)
        # States from the mixed hour on (what purging left): 3.0 °C, a
        # 10-minute dip to -4.7 °C at :20, 3.0 °C again.
        for offset, value in ((0, "3.0"), (1200, "6548.9"), (1800, "3.0")):
            session.add(
                States(
                    metadata_id=metadata_id,
                    state=value,
                    last_updated_ts=mixed + offset,
                    last_changed_ts=mixed + offset,
                )
            )
        session.add_all(
            [
                Statistics(
                    metadata_id=statistics_id,
                    start_ts=mixed,
                    mean=(5 * 3.0 + 6548.9) / 6,
                    min=3.0,
                    max=6548.9,
                ),
                Statistics(
                    metadata_id=statistics_id,
                    start_ts=negative,
                    mean=6550.0,
                    min=6548.0,
                    max=6552.0,
                ),
                Statistics(
                    metadata_id=statistics_id,
                    start_ts=lost,
                    mean=1000.0,
                    min=2.0,
                    max=6550.0,
                ),
                Statistics(
                    metadata_id=statistics_id,
                    start_ts=mixed + H,
                    mean=3.0,
                    min=3.0,
                    max=3.0,
                ),
                StatisticsShortTerm(
                    metadata_id=statistics_id,
                    start_ts=mixed + 1200,
                    mean=6548.9,
                    min=6548.9,
                    max=6548.9,
                ),
            ]
        )
        # Flow Temperature Circuit 2 without a sensor: 6488.7 °C throughout.
        flow_id, flow_statistics = _metadata(session, FLOW_2)
        session.add(
            States(
                metadata_id=flow_id,
                state="6488.7",
                last_updated_ts=mixed,
                last_changed_ts=mixed,
            )
        )
        session.add(
            Statistics(
                metadata_id=flow_statistics,
                start_ts=mixed,
                mean=6488.7,
                min=6488.7,
                max=6488.7,
            )
        )

    await _run_in_db(hass, write)
    return {"mixed": mixed, "negative": negative, "lost": lost}


async def _read(hass, entity_id: str):
    def read(session):
        metadata_id = session.execute(
            select(StatesMeta.metadata_id).where(StatesMeta.entity_id == entity_id)
        ).scalar()
        states = [
            row.state
            for row in session.execute(
                select(States.state)
                .where(States.metadata_id == metadata_id)
                .order_by(States.last_updated_ts)
            )
        ]
        statistics_id = session.execute(
            select(StatisticsMeta.id).where(StatisticsMeta.statistic_id == entity_id)
        ).scalar()
        hourly = {
            row.start_ts: (row.mean, row.min, row.max)
            for row in session.execute(
                select(Statistics).where(Statistics.metadata_id == statistics_id)
            ).scalars()
        }
        five_minute = {
            row.start_ts: (row.mean, row.min, row.max)
            for row in session.execute(
                select(StatisticsShortTerm).where(
                    StatisticsShortTerm.metadata_id == statistics_id
                )
            ).scalars()
        }
        return states, hourly, five_minute

    return await _run_in_db(hass, read)


async def _repair(hass, **data):
    return await hass.services.async_call(
        DOMAIN,
        "repair_temperature_history",
        data,
        blocking=True,
        return_response=True,
    )


async def test_a_dry_run_changes_nothing(hass, unit) -> None:
    await _set_up(hass)
    await async_wait_recording_done(hass)
    await _record_history(hass)
    before = await _read(hass, SUCTION)

    response = await _repair(hass)
    assert response["dry_run"] is True
    assert response["entities"][SUCTION] == {
        "states": 1,
        "hourly": {
            "recalculated": 1,
            "shifted": 1,
            "removed_no_sensor": 0,
            "unrecoverable": 1,
            "removed_unrecoverable": 0,
        },
        "five_minute": {
            "recalculated": 1,
            "shifted": 0,
            "removed_no_sensor": 0,
            "unrecoverable": 0,
            "removed_unrecoverable": 0,
        },
    }
    assert await _read(hass, SUCTION) == before


async def test_the_repair(hass, unit) -> None:
    await _set_up(hass)
    await async_wait_recording_done(hass)
    times = await _record_history(hass)

    response = await _repair(hass, dry_run=False)
    assert response["dry_run"] is False
    await async_wait_recording_done(hass)

    states, hourly, five_minute = await _read(hass, SUCTION)
    # The spike is the real value again.
    assert states[:3] == ["3.0", "-4.7", "3.0"]
    # The mixed hour, recalculated from the repaired states: 3.0 for 20 min,
    # -4.7 for 10 min, 3.0 for 30 min.
    mean, low, high = hourly[times["mixed"]]
    assert mean == pytest.approx((50 * 3.0 + 10 * -4.7) / 60)
    assert (low, high) == (-4.7, 3.0)
    # The hour entirely below zero, shifted without its states.
    assert hourly[times["negative"]] == pytest.approx((-3.6, -5.6, -1.6))
    # The mixed hour whose states are gone stays as it was.
    assert hourly[times["lost"]] == (1000.0, 2.0, 6550.0)
    # A healthy hour is untouched.
    assert hourly[times["mixed"] + H] == (3.0, 3.0, 3.0)
    # The 5-minute period of the dip.
    assert five_minute[times["mixed"] + 1200] == pytest.approx((-4.7, -4.7, -4.7))

    # No sensor on circuit 2: unknown, and its statistics are removed.
    states, hourly, _ = await _read(hass, FLOW_2)
    assert states[0] == "unknown"
    assert times["mixed"] not in hourly


async def test_unrecoverable_hours_can_be_removed(hass, unit) -> None:
    await _set_up(hass)
    await async_wait_recording_done(hass)
    times = await _record_history(hass)

    response = await _repair(hass, dry_run=False, remove_unrecoverable=True)
    assert response["entities"][SUCTION]["hourly"]["removed_unrecoverable"] == 1
    await async_wait_recording_done(hass)
    _, hourly, _ = await _read(hass, SUCTION)
    assert times["lost"] not in hourly
    assert times["mixed"] in hourly


async def test_a_second_run_finds_nothing(hass, unit) -> None:
    await _set_up(hass)
    await async_wait_recording_done(hass)
    await _record_history(hass)
    await _repair(hass, dry_run=False, remove_unrecoverable=True)
    await async_wait_recording_done(hass)
    response = await _repair(hass)
    assert response["entities"] == {}
