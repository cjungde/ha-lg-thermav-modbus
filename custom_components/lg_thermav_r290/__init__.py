"""LG ThermaV R290 Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import LGThermaVCoordinator
from .migration import UNIQUE_ID_MINOR_VERSION, renamed_unique_id

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "switch", "button", "number", "select"]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Rename the unique ids of entries set up before 1.3.0 (see migration.py).

    The registry entries are changed in place, so entity ids, history,
    statistics and automations stay as they are. An id that is already taken
    is left alone and logged rather than failing the setup.
    """
    if entry.version > 1:
        # Set up by a newer version of the integration; nothing to do here.
        return False
    if entry.minor_version >= UNIQUE_ID_MINOR_VERSION:
        return True

    registry = er.async_get(hass)

    @callback
    def _rename(entity: er.RegistryEntry) -> dict[str, str] | None:
        new_id = renamed_unique_id(entity.domain, entity.unique_id, entry.entry_id)
        if new_id is None:
            return None
        if registry.async_get_entity_id(entity.domain, DOMAIN, new_id) is not None:
            _LOGGER.warning(
                "Not renaming the unique id of %s to %s: already in use",
                entity.entity_id,
                new_id,
            )
            return None
        return {"new_unique_id": new_id}

    await er.async_migrate_entries(hass, entry.entry_id, _rename)
    hass.config_entries.async_update_entry(entry, minor_version=UNIQUE_ID_MINOR_VERSION)
    _LOGGER.info("Unique ids of %s migrated to the 1.3.0 naming", entry.title)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = LGThermaVCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # The shared connection closes itself when its last unit holder unloads,
        # so there is no client of our own left to close here.
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
