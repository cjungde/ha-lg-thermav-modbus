"""Diagnostics download for a config entry (device page → Download diagnostics).

What a bug report needs, without what identifies the installation: the
connection settings minus host and serial port, the options with the result
of the register check, the state of every optional read, and the last poll's
data as the coordinator holds it, i.e. every register value already scaled.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import CONF_SERIAL_PORT, DOMAIN

TO_REDACT = {"host", CONF_SERIAL_PORT}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    integration = await async_get_integration(hass, DOMAIN)
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    result: dict[str, Any] = {
        "integration_version": str(integration.version),
        "entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
    }
    if coordinator is None:
        result["coordinator"] = None
        return result
    result["coordinator"] = {
        "last_update_success": coordinator.last_update_success,
        "update_interval_s": coordinator.update_interval.total_seconds(),
        "reads": coordinator.diagnostics(),
        "data": dict(coordinator.data or {}),
    }
    return result
