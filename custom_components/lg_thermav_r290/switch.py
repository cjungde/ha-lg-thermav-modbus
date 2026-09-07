"""Switch platform for LG ThermaV R290 — state coil registers.

Only coils that hold a state belong here. The momentary trigger coils
("0: hold status / 1: start operation") are buttons instead — see button.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LGThermaVCoordinator


@dataclass(frozen=True, kw_only=True)
class LGSwitchDescription(SwitchEntityDescription):
    data_key: str = ""
    coil_address: int = 0


_SWITCHES: tuple[LGSwitchDescription, ...] = (
    LGSwitchDescription(
        key="hauptschalter",
        data_key="coil_hauptschalter",
        coil_address=0,
        name="Heat Pump",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:heat-pump",
    ),
    LGSwitchDescription(
        key="dhw",
        data_key="coil_dhw",
        coil_address=1,
        name="DHW",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:water-boiler",
    ),
    LGSwitchDescription(
        key="silent_mode",
        data_key="coil_silent_mode",
        coil_address=2,
        name="Silent Mode",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:volume-off",
    ),
    LGSwitchDescription(
        key="emergency_stop",
        data_key="coil_emergency_stop",
        coil_address=4,
        name="Emergency Stop",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:stop-circle",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(LGSwitch(coordinator, entry, desc) for desc in _SWITCHES)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="LG ThermaV R290",
        manufacturer="LG",
        model="ThermaV R290",
    )


class LGSwitch(CoordinatorEntity[LGThermaVCoordinator], SwitchEntity):
    """A switch that controls a Modbus coil register."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._data_key = description.data_key
        self._coil_address = description.coil_address
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_coil(self._coil_address, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_coil(self._coil_address, False)
        await self.coordinator.async_request_refresh()
