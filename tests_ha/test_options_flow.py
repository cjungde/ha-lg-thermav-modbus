"""Configure: the menu with the status table, the options, the check."""

from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_config_flow import DOMAIN, RTU, defaults, form_input, options_are_sections


def _entry(hass, options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options=options,
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    return entry


async def test_menu_before_any_check(hass, unit) -> None:
    entry = _entry(hass, {"power_limit": True})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {"options", "detect"}
    status = result["description_placeholders"]
    assert status["power_limit_on"] == "✓"
    assert status["energy_registers_on"] == "–"
    assert status["energy_registers"] == "–"  # never checked
    assert status["checked"] == "–"
    assert unit.requests == []  # opening the menu asks the unit nothing


async def test_options_without_a_check_keep_the_values(hass, unit) -> None:
    entry = _entry(hass, {"energy_registers": True, "scan_interval": 30})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "options"}
    )
    assert result["step_id"] == "options"
    assert options_are_sections(result)
    values = defaults(result)
    assert values["energy_registers"] is True
    assert values["scan_interval"] == 30
    assert values["power_limit"] is False
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], form_input(result, values)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["scan_interval"] == 30


async def test_check_ticks_what_answers_and_switches_nothing_off(hass, unit) -> None:
    entry = _entry(hass, {"power_limit": True, "experimental_registers": True})
    unit.silent = {("coil", 6)}  # this unit lacks the power limit
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "detect"}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_configure(result["flow_id"])
    assert result["step_id"] == "options"

    values = defaults(result)
    assert values["energy_registers"] is True
    assert values["compressor_modulation_limit"] is True
    # On before, so still on, although the unit did not answer.
    assert values["power_limit"] is True
    assert values["experimental_registers"] is True
    status = result["description_placeholders"]
    assert status["energy_registers"] == "✓ ➕"  # answers, still off
    assert status["power_limit"] == "✗"
    assert status["checked"] != "–"

    await hass.config_entries.options.async_configure(
        result["flow_id"], form_input(result, values)
    )
    assert entry.options["detected"]["energy_registers"] is True
    assert entry.options["detected"]["power_limit"] is False

    # The stored result shows without asking the unit again.
    asked = len(unit.requests)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    status = result["description_placeholders"]
    assert status["energy_registers"] == "✓"
    assert status["energy_registers_on"] == "✓"
    assert len(unit.requests) == asked
