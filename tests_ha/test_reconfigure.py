"""Reconfigure: new link settings for the device the entry already holds."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_config_flow import DOMAIN

TCP = {"host": "192.168.1.50", "port": 502, "slave_id": 1, "scan_interval": 10}


async def _loaded_tcp_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "tcp", **TCP},
        unique_id="192.168.1.50:502:1",
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def _reconfigure_to(hass, entry, connection_type: str):
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["step_id"] == "reconfigure"
    result = await flow.async_configure(
        result["flow_id"], {"connection_type": connection_type}
    )
    assert result["step_id"] == "tcp"
    result = await flow.async_configure(result["flow_id"], TCP)
    await hass.async_block_till_done()
    return result


async def test_tcp_to_tcp_rtu_on_the_same_host(hass, unit) -> None:
    """Used to fail with link_settings_conflict against the entry's own hold."""
    entry = await _loaded_tcp_entry(hass)
    result = await _reconfigure_to(hass, entry, "tcp_rtu")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["connection_type"] == "tcp_rtu"
    assert entry.state is ConfigEntryState.LOADED


async def test_new_settings_that_fail_leave_the_entry_as_it_was(hass, unit) -> None:
    entry = await _loaded_tcp_entry(hass)
    unit.silent = {("input", 0)}  # the new settings get no answer
    result = await _reconfigure_to(hass, entry, "tcp_rtu")
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data["connection_type"] == "tcp"
    unit.silent = set()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_unchanged_link_settings_do_not_unload_the_entry(hass, unit) -> None:
    entry = await _loaded_tcp_entry(hass)
    unloads = []
    entry.async_on_unload(lambda: unloads.append(True))
    result = await _reconfigure_to(hass, entry, "tcp")
    assert result["reason"] == "reconfigure_successful"
    # Only the reload after success unloads it, not the connection test.
    assert len(unloads) == 1


DETECTED = {
    "energy_registers": True,
    "compressor_modulation_limit": True,
    "power_limit": False,
}


async def _checked_tcp_entry(hass) -> MockConfigEntry:
    entry = await _loaded_tcp_entry(hass)
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            "energy_registers": True,
            "detected": DETECTED,
            "detected_at": "2026-10-01T10:00:00+00:00",
        },
    )
    await hass.async_block_till_done()
    return entry


async def _reconfigure_tcp(hass, entry, connection_type: str, settings: dict):
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await flow.async_configure(
        result["flow_id"], {"connection_type": connection_type}
    )
    result = await flow.async_configure(result["flow_id"], settings)
    await hass.async_block_till_done()
    return result


async def test_same_unit_keeps_the_check(hass, unit) -> None:
    """TCP -> TCP-RTU on the same host: another framing, the same unit."""
    entry = await _checked_tcp_entry(hass)
    result = await _reconfigure_tcp(hass, entry, "tcp_rtu", TCP)
    assert result["reason"] == "reconfigure_successful"
    assert entry.options["detected"] == DETECTED
    assert entry.unique_id == "192.168.1.50:502:1"


async def test_another_address_clears_the_check(hass, unit) -> None:
    entry = await _checked_tcp_entry(hass)
    result = await _reconfigure_tcp(hass, entry, "tcp", {**TCP, "host": "192.168.1.60"})
    assert result["reason"] == "reconfigure_successful_check_cleared"
    assert entry.data["host"] == "192.168.1.60"
    # As setup writes it: the form hands the slave id over as a float.
    assert entry.unique_id == "192.168.1.60:502:1.0"
    assert entry.options["detected"] is None
    assert entry.options["detected_at"] is None
    # The options themselves are unchanged.
    assert entry.options["energy_registers"] is True
    assert entry.state is ConfigEntryState.LOADED


async def test_another_slave_id_clears_the_check(hass, unit) -> None:
    entry = await _checked_tcp_entry(hass)
    result = await _reconfigure_tcp(hass, entry, "tcp", {**TCP, "slave_id": 33})
    assert result["reason"] == "reconfigure_successful_check_cleared"
    assert entry.unique_id == "192.168.1.50:502:33.0"
    assert entry.options["detected"] is None


async def test_an_address_another_entry_has_is_refused(hass, unit) -> None:
    entry = await _checked_tcp_entry(hass)
    other = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "tcp", **TCP, "host": "192.168.1.60"},
        unique_id="192.168.1.60:502:1",
        version=1,
        minor_version=4,
    )
    other.add_to_hass(hass)
    result = await _reconfigure_tcp(hass, entry, "tcp", {**TCP, "host": "192.168.1.60"})
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "192.168.1.50"
    assert entry.options["detected"] == DETECTED
