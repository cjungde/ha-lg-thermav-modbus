"""The diagnostics download: useful for a bug report, without the host."""

from __future__ import annotations

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lg_therma_v_r290.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .test_config_flow import DOMAIN

TCP = {
    "connection_type": "tcp",
    "host": "192.168.1.50",
    "port": 502,
    "slave_id": 1,
    "scan_interval": 10,
}


async def test_diagnostics(hass, unit) -> None:
    unit.refused = {("holding", 10)}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=TCP,
        options={"experimental_registers": True, "energy_registers": True},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)
    json.dumps(result)  # the download is JSON

    assert result["integration_version"]
    assert result["entry"]["data"]["host"] == "**REDACTED**"
    assert result["entry"]["data"]["port"] == 502
    assert result["entry"]["options"]["energy_registers"] is True
    coordinator = result["coordinator"]
    assert coordinator["last_update_success"] is True
    assert coordinator["update_interval_s"] == 10
    assert coordinator["data"]["input_outdoor_temperature"] == 0.0
    reads = coordinator["reads"]
    assert reads["identity_registers"] == {"39998": 0, "39999": 0}
    assert reads["energy_registers"] == {
        "enabled": True,
        "status": "answering",
        "ever_answered": True,
        "misses_in_a_row": 0,
        "paused_polls_left": 0,
    }
    assert reads["experimental_registers"]["blocks_given_up"] == ["holding 10"]
    assert 23 not in reads["writable_holding_registers"]


async def test_diagnostics_of_an_entry_that_is_not_loaded(hass, unit) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=TCP, version=1, minor_version=4)
    entry.add_to_hass(hass)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["coordinator"] is None
    assert result["entry"]["data"]["host"] == "**REDACTED**"
