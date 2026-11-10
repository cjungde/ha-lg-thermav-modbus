"""Poll Duration, Bus Load and the Modbus error sensors, by the poll statistics option."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_config_flow import DOMAIN, RTU

DURATION = "sensor.lg_therma_v_r290_poll_duration"
LOAD = "sensor.lg_therma_v_r290_bus_load"
ERRORS = "sensor.lg_therma_v_r290_modbus_errors"
LAST_ERROR = "sensor.lg_therma_v_r290_last_modbus_error"
OUTDOOR = "sensor.lg_therma_v_r290_outdoor_temperature"


async def _set_up(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options={"poll_statistics": True},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_poll_sensors_with_the_option(hass, unit) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options={"poll_statistics": True},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    for entity_id in (DURATION, LOAD, ERRORS, LAST_ERROR):
        entity = registry.async_get(entity_id)
        assert entity is not None
        assert entity.disabled_by is None  # enabled, as the option asked
        assert entity.entity_category == "diagnostic"

    duration = hass.states.get(DURATION)
    assert duration.attributes["unit_of_measurement"] == "ms"
    assert int(duration.state) >= 0
    # Five block reads plus the identity registers on the first poll.
    assert duration.attributes["requests"] == 6
    load = hass.states.get(LOAD)
    assert load.attributes["unit_of_measurement"] == "%"
    assert 0 <= float(load.state) < 100

    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    # The identity is read once per start, not per poll.
    assert hass.states.get(DURATION).attributes["requests"] == 5

    # Switching the option off removes all four.
    hass.config_entries.async_update_entry(entry, options={"poll_statistics": False})
    await hass.async_block_till_done()
    for entity_id in (DURATION, LOAD, ERRORS, LAST_ERROR):
        assert registry.async_get(entity_id) is None


async def test_error_sensors_count_failed_requests(hass, unit) -> None:
    # A unit without the identity registers refuses them on the first poll:
    # an answer, not a bus error.
    unit.refused = {("input", 9997)}
    entry = await _set_up(hass)

    errors = hass.states.get(ERRORS)
    assert errors.state == "0"
    assert errors.attributes["refusals"] == 1
    assert errors.attributes["state_class"] == "total_increasing"
    # No error yet: "none" (shown as None), not unknown, and since when.
    last = hass.states.get(LAST_ERROR)
    assert last.state == "none"
    assert last.attributes["time"] is None
    assert last.attributes["since"] == errors.attributes["since"]

    # The coil block stops answering: the poll fails, the heat pump's
    # entities go unavailable, the error sensors stay and say why.
    unit.silent = {("coil", 0)}
    coordinator = entry.runtime_data
    for expected in (1, 2):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(OUTDOOR).state == "unavailable"
        # Counted on the second failure too, when the coordinator itself does
        # not notify its entities again.
        assert hass.states.get(ERRORS).state == str(expected)

    last = hass.states.get(LAST_ERROR)
    assert last.state == "ModbusTimeoutError: coil 0: no answer"
    assert last.attributes["request"] == "read_coils(0, 6)"
    assert last.attributes["time"] is not None
    assert last.attributes["since"] == errors.attributes["since"]

    # Answering again: the data is back, the count and the last error stay.
    unit.silent = set()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(OUTDOOR).state == "0.0"
    assert hass.states.get(ERRORS).state == "2"
    assert hass.states.get(LAST_ERROR).state == last.state


async def test_status_table_shows_the_option(hass, unit) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options={"poll_statistics": True},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    status = result["description_placeholders"]
    assert status["poll_statistics_on"] == "✓"
    assert status["poll_statistics"] == "–"  # nothing to check on the unit
