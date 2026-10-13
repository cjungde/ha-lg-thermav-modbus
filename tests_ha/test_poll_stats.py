"""Poll Duration and Bus Load: diagnostic, disabled by default, filled per poll."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_config_flow import DOMAIN, RTU

DURATION = "sensor.lg_thermav_r290_poll_duration"
LOAD = "sensor.lg_thermav_r290_bus_load"


async def test_poll_sensors(hass, unit) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    for entity_id in (DURATION, LOAD):
        entity = registry.async_get(entity_id)
        assert entity is not None
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert entity.entity_category == "diagnostic"
        assert hass.states.get(entity_id) is None
        registry.async_update_entity(entity_id, disabled_by=None)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    duration = hass.states.get(DURATION)
    assert duration.attributes["unit_of_measurement"] == "ms"
    assert int(duration.state) >= 0
    # Five block reads plus the identity registers on the first poll.
    assert duration.attributes["requests"] == 6
    load = hass.states.get(LOAD)
    assert load.attributes["unit_of_measurement"] == "%"
    assert 0 <= float(load.state) < 100

    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    # The identity is read once per start, not per poll.
    assert hass.states.get(DURATION).attributes["requests"] == 5
