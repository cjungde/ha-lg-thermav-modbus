"""Optional registers the unit never answers: given up, shown in four places.

The Repairs notice with its fix, the "Since start" column under Configure, the
"Optional Registers" sensor and the diagnostics download.
"""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.lg_therma_v_r290.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.lg_therma_v_r290.repairs import async_create_fix_flow

from .test_config_flow import DOMAIN
from .test_setup import _set_up

SENSOR = "sensor.lg_therma_v_r290_optional_registers"
ENERGY_SENSOR = "sensor.lg_therma_v_r290_electrical_power_heat_pump"


async def _polls(hass, entry, count: int) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    for _ in range(count):
        await coordinator.async_refresh()
    await hass.async_block_till_done()


def _issue(hass, entry):
    return ir.async_get(hass).async_get_issue(
        DOMAIN, f"{entry.entry_id}_energy_registers_never_answered"
    )


async def test_a_block_that_never_answers_is_given_up(hass, unit) -> None:
    unit.silent = {("input", 34)}
    entry = await _set_up(hass, {"energy_registers": True})
    await _polls(hass, entry, 2)  # the setup's first poll makes three

    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.is_fixable
    assert issue.translation_key == "energy_registers_never_answered"
    assert hass.states.get(SENSOR).state == "given_up"
    attributes = hass.states.get(SENSOR).attributes
    assert attributes["energy_registers"] == "given_up"
    assert attributes["energy_registers_last_check"] == "not_checked"

    # Not asked again, however many polls follow.
    asked = unit.requests.count(("input", 34))
    await _polls(hass, entry, 30)
    assert unit.requests.count(("input", 34)) == asked == 3

    # The status table under Configure.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["description_placeholders"]["energy_registers_now"] == "⛔"
    assert result["description_placeholders"]["power_limit_now"] == "–"

    # The diagnostics download.
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    reads = diagnostics["coordinator"]["reads"]["energy_registers"]
    assert reads["status"] == "given_up"
    assert reads["ever_answered"] is False


async def test_a_block_that_answered_before_only_pauses(hass, unit) -> None:
    entry = await _set_up(hass, {"energy_registers": True})
    unit.silent = {("input", 34)}
    await _polls(hass, entry, 3)

    assert _issue(hass, entry) is None
    assert hass.states.get(SENSOR).state == "paused"
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["description_placeholders"]["energy_registers_now"] == "⏸"


async def test_the_fix_switches_the_option_off(hass, unit) -> None:
    unit.silent = {("input", 34)}
    entry = await _set_up(hass, {"energy_registers": True})
    await _polls(hass, entry, 2)
    issue = _issue(hass, entry)
    assert hass.states.get(ENERGY_SENSOR) is not None

    flow = await async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"] == {"entry": entry.title}
    result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    assert entry.options["energy_registers"] is False
    # Reloaded without the option: its entities and the notice are gone.
    registry = er.async_get(hass)
    assert registry.async_get(ENERGY_SENSOR) is None
    assert _issue(hass, entry) is None
    assert hass.states.get(SENSOR).state == "not_used"


async def test_a_reload_starts_over(hass, unit) -> None:
    unit.silent = {("input", 34)}
    entry = await _set_up(hass, {"energy_registers": True})
    await _polls(hass, entry, 2)
    assert _issue(hass, entry) is not None

    # The unit answers after all (say, after a firmware update).
    unit.silent = set()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, entry) is None
    assert hass.states.get(SENSOR).state == "ok"


async def test_without_optional_registers_the_sensor_says_not_used(hass, unit) -> None:
    await _set_up(hass)
    assert hass.states.get(SENSOR).state == "not_used"
