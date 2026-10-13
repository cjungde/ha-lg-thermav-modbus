"""Experimental blocks the unit does not answer are not asked again."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_config_flow import DOMAIN, RTU


async def _set_up(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options={"experimental_registers": True},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _poll(hass, entry, times: int) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    for _ in range(times):
        await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_refused_block_is_asked_once(hass, unit) -> None:
    unit.refused = {("holding", 10)}
    entry = await _set_up(hass)
    await _poll(hass, entry, 5)
    assert unit.requests.count(("holding", 10)) == 1
    # The other blocks are still read every poll.
    assert unit.requests.count(("holding", 62)) == 6
    state = hass.states.get("sensor.lg_thermav_r290_experimental_holding_40011")
    assert state.state == "unavailable"
    state = hass.states.get("sensor.lg_thermav_r290_experimental_holding_40063")
    assert state.state == "0"


async def test_silent_block_is_given_up_after_three_misses(hass, unit) -> None:
    unit.silent = {("input", 63)}
    entry = await _set_up(hass)
    await _poll(hass, entry, 6)
    assert unit.requests.count(("input", 63)) == 3
    state = hass.states.get("sensor.lg_thermav_r290_experimental_input_30064")
    assert state.state == "unavailable"


async def test_a_reload_asks_again(hass, unit) -> None:
    unit.refused = {("input", 14)}
    entry = await _set_up(hass)
    await _poll(hass, entry, 2)
    assert unit.requests.count(("input", 14)) == 1
    unit.refused = set()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert unit.requests.count(("input", 14)) == 2
    state = hass.states.get("sensor.lg_thermav_r290_experimental_input_30015")
    assert state.state == "0"
