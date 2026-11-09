"""The action that repairs temperature history (see history_repair.py).

``lg_therma_v_r290.repair_temperature_history`` goes through the temperature
sensors of every LG Therma V R290 entry, plans the repair of their states and
statistics, and -- unless it is a dry run, the default -- applies it. The
work runs as a task in the recorder's own thread, like Home Assistant's own
statistics corrections, so it never competes with the recorder writing, and
all changes are committed in one transaction. The response lists, per
entity, what was (or would be) changed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from sqlalchemy import delete, select, update
import voluptuous as vol

from . import history_repair
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.components.recorder import Recorder

_LOGGER = logging.getLogger(__name__)

SERVICE_REPAIR_TEMPERATURE_HISTORY = "repair_temperature_history"
ATTR_DRY_RUN = "dry_run"
ATTR_REMOVE_UNRECOVERABLE = "remove_unrecoverable"

SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DRY_RUN, default=True): bool,
        vol.Optional(ATTR_REMOVE_UNRECOVERABLE, default=False): bool,
    }
)


def temperature_sensors(hass: HomeAssistant) -> list[str]:
    """The temperature sensors of every entry of this integration."""
    registry = er.async_get(hass)
    return sorted(
        entry.entity_id
        for entry in registry.entities.values()
        if entry.platform == DOMAIN
        and entry.domain == "sensor"
        and entry.original_device_class == SensorDeviceClass.TEMPERATURE
    )


def _repair(
    instance: Recorder,
    entity_ids: list[str],
    *,
    dry_run: bool,
    remove_unrecoverable: bool,
) -> dict[str, Any]:
    """Load, plan and (unless a dry run) apply; runs in the recorder thread."""
    from homeassistant.components.recorder.db_schema import (  # noqa: PLC0415
        States,
        StatesMeta,
        Statistics,
        StatisticsMeta,
        StatisticsShortTerm,
    )
    from homeassistant.helpers.recorder import session_scope  # noqa: PLC0415

    report: dict[str, Any] = {}
    with session_scope(session=instance.get_session()) as session:
        for entity_id in entity_ids:
            metadata_id = session.execute(
                select(StatesMeta.metadata_id).where(StatesMeta.entity_id == entity_id)
            ).scalar()
            states: list[tuple[int, float, str | None]] = []
            if metadata_id is not None:
                states = [
                    (row.state_id, row.last_updated_ts, row.state)
                    for row in session.execute(
                        select(States.state_id, States.last_updated_ts, States.state)
                        .where(States.metadata_id == metadata_id)
                        .order_by(States.last_updated_ts)
                    )
                ]
            statistics_id = session.execute(
                select(StatisticsMeta.id).where(
                    StatisticsMeta.statistic_id == entity_id
                )
            ).scalar()

            def damaged(table, statistics_id=statistics_id):
                if statistics_id is None:
                    return []
                return [
                    history_repair.StatRow(r.id, r.start_ts, r.mean, r.min, r.max)
                    for r in session.execute(
                        select(
                            table.id, table.start_ts, table.mean, table.min, table.max
                        )
                        .where(
                            table.metadata_id == statistics_id,
                            table.max > history_repair.LIMIT,
                        )
                        .order_by(table.start_ts)
                    )
                ]

            plan = history_repair.plan_entity(
                states,
                damaged(Statistics),
                damaged(StatisticsShortTerm),
                remove_unrecoverable=remove_unrecoverable,
            )
            if plan.empty:
                continue
            report[entity_id] = plan.summary()
            if dry_run:
                continue
            for state_id, text in plan.states:
                session.execute(
                    update(States).where(States.state_id == state_id).values(state=text)
                )
            for table, table_plan in (
                (Statistics, plan.hourly),
                (StatisticsShortTerm, plan.five_minute),
            ):
                for row_id, mean, low, high in table_plan.updates:
                    session.execute(
                        update(table)
                        .where(table.id == row_id)
                        .values(mean=mean, min=low, max=high)
                    )
                if table_plan.deletes:
                    session.execute(
                        delete(table).where(table.id.in_(table_plan.deletes))
                    )
        if dry_run:
            session.rollback()
    return report


@dataclass(slots=True)
class _RepairTask:
    """A recorder task: runs _repair in the recorder thread, reports back."""

    hass: HomeAssistant
    future: asyncio.Future[dict[str, Any]]
    entity_ids: list[str]
    dry_run: bool
    remove_unrecoverable: bool
    commit_before: bool = field(default=True)

    def run(self, instance: Recorder) -> None:
        try:
            result = _repair(
                instance,
                self.entity_ids,
                dry_run=self.dry_run,
                remove_unrecoverable=self.remove_unrecoverable,
            )
        except Exception as err:  # noqa: BLE001 -- reported to the caller
            self.hass.loop.call_soon_threadsafe(self.future.set_exception, err)
        else:
            self.hass.loop.call_soon_threadsafe(self.future.set_result, result)


async def _async_repair(call: ServiceCall) -> ServiceResponse:
    hass = call.hass
    try:
        from homeassistant.helpers.recorder import get_instance  # noqa: PLC0415

        instance = get_instance(hass)
    except KeyError as err:
        raise HomeAssistantError("The recorder is not running") from err
    entity_ids = temperature_sensors(hass)
    dry_run = call.data[ATTR_DRY_RUN]
    future: asyncio.Future[dict[str, Any]] = hass.loop.create_future()
    instance.queue_task(
        _RepairTask(
            hass,
            future,
            entity_ids,
            dry_run,
            call.data[ATTR_REMOVE_UNRECOVERABLE],
        )
    )
    entities = await future
    if not dry_run and entities:
        _LOGGER.warning(
            "Repaired the temperature history of %d entities: %s",
            len(entities),
            entities,
        )
    return {
        "dry_run": dry_run,
        "checked": len(entity_ids),
        "entities": entities,
    }


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions (once, not per entry)."""
    if hass.services.has_service(DOMAIN, SERVICE_REPAIR_TEMPERATURE_HISTORY):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_REPAIR_TEMPERATURE_HISTORY,
        _async_repair,
        schema=SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
