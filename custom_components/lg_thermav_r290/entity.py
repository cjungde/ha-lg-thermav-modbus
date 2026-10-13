"""Base class shared by every entity of the integration.

One place for what all entities have in common: they belong to one device,
take their name from the entity description or class, and build their
unique id as ``<config entry id>_<key>``, where the key is the entity's name
as Home Assistant slugifies it into an entity id (see docs/naming.md).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LGThermaVCoordinator


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """The one device every entity of a config entry belongs to."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="LG ThermaV R290",
        manufacturer="LG",
        model="ThermaV R290",
    )


def unique_id(entry: ConfigEntry, key: str) -> str:
    """Unique id of the entity with this key in this config entry."""
    return f"{entry.entry_id}_{key}"


class LGEntity(CoordinatorEntity[LGThermaVCoordinator]):
    """An entity of the LG ThermaV R290 device, keyed per docs/naming.md."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: LGThermaVCoordinator, entry: ConfigEntry, key: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id(entry, key)
        self._attr_device_info = device_info(entry)

    def _data(self, data_key: str):
        """A value from the coordinator data, None before the first update."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(data_key)


def remove_entities(hass, entry: ConfigEntry, domain: str, keys) -> None:
    """Drop optional entities when their option is switched off.

    Left in the registry they would sit there unavailable for good.
    """
    registry = er.async_get(hass)
    for key in keys:
        entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id(entry, key))
        if entity_id is not None:
            registry.async_remove(entity_id)
