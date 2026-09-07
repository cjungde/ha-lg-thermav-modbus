"""Select platform for LG ThermaV R290 — operation mode and control method."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONTROL_METHOD_FROM_VALUE,
    CONTROL_METHOD_OPTIONS,
    CONTROL_METHOD_TO_VALUE,
    DOMAIN,
    OPERATION_MODE_FROM_VALUE,
    OPERATION_MODE_OPTIONS,
    OPERATION_MODE_TO_VALUE,
)
from .coordinator import LGThermaVCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class LGSelectDescription(SelectEntityDescription):
    data_key: str = ""
    register_address: int = 0
    to_value: dict[str, int] | None = None
    from_value: dict[int, str] | None = None


_SELECTS: tuple[LGSelectDescription, ...] = (
    LGSelectDescription(
        key="operation_mode",
        data_key="operation_mode",
        register_address=0,
        name="Operation Mode",
        options=OPERATION_MODE_OPTIONS,
        to_value=OPERATION_MODE_TO_VALUE,
        from_value=OPERATION_MODE_FROM_VALUE,
        icon="mdi:heat-pump",
    ),
    LGSelectDescription(
        key="control_method",
        data_key="control_method",
        register_address=1,
        name="Control Method",
        options=CONTROL_METHOD_OPTIONS,
        to_value=CONTROL_METHOD_TO_VALUE,
        from_value=CONTROL_METHOD_FROM_VALUE,
        icon="mdi:tune",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(LGSelect(coordinator, entry, desc) for desc in _SELECTS)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="LG ThermaV R290",
        manufacturer="LG",
        model="ThermaV R290",
    )


class LGSelect(CoordinatorEntity[LGThermaVCoordinator], SelectEntity):
    """A select entity backed by a writable Modbus holding register."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGSelectDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._data_key = description.data_key
        self._register_address = description.register_address
        self._to_value = description.to_value
        self._from_value = description.from_value
        self._attr_options = description.options
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._data_key)
        if raw is None:
            return None
        return self._from_value.get(raw)

    async def async_select_option(self, option: str) -> None:
        value = self._to_value.get(option)
        if value is None:
            _LOGGER.warning("Unknown option '%s' for %s", option, self.entity_id)
            return
        await self.coordinator.async_write_register(self._register_address, value)
        await self.coordinator.async_request_refresh()
