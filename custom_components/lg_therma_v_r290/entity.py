"""Base class shared by every entity of the integration.

One place for what all entities have in common: they belong to one device,
take their name from the entity description or class, and build their
unique id as ``<config entry id>_<key>``, where the key is the entity's name
as Home Assistant slugifies it into an entity id (see docs/naming.md).
"""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import LGThermaVCoordinator

# The device name; Home Assistant makes the entity ids from it
# (the device name as an id, then the key), and the YAML takeover targets
# those ids.
DEVICE_NAME = "LG Therma V R290"


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """The one device every entity of a config entry belongs to."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=DEVICE_NAME,
        manufacturer="LG",
        model="Therma V R290",
    )


def unique_id(entry: ConfigEntry, key: str) -> str:
    """Unique id of the entity with this key in this config entry."""
    return f"{entry.entry_id}_{key}"


class LGEntity(CoordinatorEntity[LGThermaVCoordinator]):
    """An entity of the LG Therma V R290 device, keyed per docs/naming.md."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        key: str,
        translation_key: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id(entry, key)
        self._attr_device_info = device_info(entry)
        self.entity_key = key
        # The name comes from the translations (entity.<platform>.<key>.name
        # in strings.json), so it shows in the user's language. Entity ids
        # stay English: see english_entity_ids.
        self._attr_translation_key = translation_key or key

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


def english_entity_ids(domain: str, entities: Iterable[LGEntity]) -> list[LGEntity]:
    """Suggest the English entity id for each entity, in every language.

    Home Assistant makes new entity ids from the name in the system language,
    so a German system would get sensor.<device>_aussentemperatur. The README,
    the guides, the example dashboard and the YAML takeover use the English
    ids, and an automation should work on every installation, so the
    integration suggests <domain>.<device name as id>_<key> itself. Only new
    entities are affected: an entity already in the registry keeps its id,
    whatever the language is changed to later, and a taken id gets Home
    Assistant's usual _2 suffix.
    """
    result = list(entities)
    prefix = slugify(DEVICE_NAME)
    for entity in result:
        entity.entity_id = f"{domain}.{prefix}_{entity.entity_key}"
    return result
