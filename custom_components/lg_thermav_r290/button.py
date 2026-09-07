"""Button platform for LG ThermaV R290 — momentary trigger coils.

Some coils are not state switches but one-shot triggers. The manual describes
them as "0: hold status / 1: start operation": writing 1 starts the operation
and the unit clears the coil again by itself. Reading such a coil back is
therefore never a confirmation — the operation's status lives in a separate
discrete input, exposed as its own binary sensor.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LGThermaVCoordinator


@dataclass(frozen=True, kw_only=True)
class LGButtonDescription(ButtonEntityDescription):
    coil_address: int = 0


_BUTTONS: tuple[LGButtonDescription, ...] = (
    LGButtonDescription(
        key="dhw_desinfection_start",
        coil_address=3,
        name="Start Disinfection",
        icon="mdi:shield-bug",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(LGButton(coordinator, entry, desc) for desc in _BUTTONS)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="LG ThermaV R290",
        manufacturer="LG",
        model="ThermaV R290",
    )


class LGButton(CoordinatorEntity[LGThermaVCoordinator], ButtonEntity):
    """A button that pulses a momentary Modbus trigger coil."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGButtonDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._coil_address = description.coil_address
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        await self.coordinator.async_write_coil(self._coil_address, True)
        await self.coordinator.async_request_refresh()
