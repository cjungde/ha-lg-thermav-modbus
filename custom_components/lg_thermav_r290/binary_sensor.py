"""Binary sensor platform for LG ThermaV R290 — discrete inputs."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LGThermaVCoordinator


@dataclass(frozen=True, kw_only=True)
class LGBinarySensorDescription(BinarySensorEntityDescription):
    data_key: str = ""


_BINARY_SENSORS: tuple[LGBinarySensorDescription, ...] = (
    LGBinarySensorDescription(
        key="di_water_flow",
        data_key="di_water_flow",
        name="Water Flow",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    LGBinarySensorDescription(
        key="di_water_pump",
        data_key="di_water_pump",
        name="Water Pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    LGBinarySensorDescription(
        key="di_ext_water_pump",
        data_key="di_ext_water_pump",
        name="External Water Pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    LGBinarySensorDescription(
        key="di_compressor",
        data_key="di_compressor",
        name="Compressor",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    LGBinarySensorDescription(
        key="di_defrosting",
        data_key="di_defrosting",
        name="Defrost",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    LGBinarySensorDescription(
        key="di_dhw_heating",
        data_key="di_dhw_heating",
        name="DHW Heating",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    LGBinarySensorDescription(
        key="di_dhw_tank_desinfection",
        data_key="di_dhw_tank_desinfection",
        name="DHW Disinfection",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    LGBinarySensorDescription(
        key="di_silent_mode",
        data_key="di_silent_mode",
        name="Silent Mode",
    ),
    LGBinarySensorDescription(
        key="di_cooling",
        data_key="di_cooling",
        name="Cooling Active",
        device_class=BinarySensorDeviceClass.COLD,
    ),
    LGBinarySensorDescription(
        key="di_solar_pump",
        data_key="di_solar_pump",
        name="Solar Pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    LGBinarySensorDescription(
        key="di_backup_heater_step1",
        data_key="di_backup_heater_step1",
        name="Backup Heater Step 1",
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    LGBinarySensorDescription(
        key="di_backup_heater_step2",
        data_key="di_backup_heater_step2",
        name="Backup Heater Step 2",
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    LGBinarySensorDescription(
        key="di_dhw_boost_heater",
        data_key="di_dhw_boost_heater",
        name="DHW Boost Heater",
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    LGBinarySensorDescription(
        key="di_error",
        data_key="di_error",
        name="Fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    LGBinarySensorDescription(
        key="di_emergency_heating_cooling",
        data_key="di_emergency_heating_cooling",
        name="Emergency Heating/Cooling Available",
    ),
    LGBinarySensorDescription(
        key="di_emergency_dhw",
        data_key="di_emergency_dhw",
        name="Emergency DHW Available",
    ),
    LGBinarySensorDescription(
        key="di_mix_pump",
        data_key="di_mix_pump",
        name="Mixing Pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)


_ENERGY_STATE_BINARY_SENSORS: tuple[tuple[str, str, int], ...] = (
    # (key, name, matching energy_state_raw value)
    ("energy_state_0", "Energy State: Not Used", 0),
    ("energy_state_1", "Energy State: Forced Off", 1),
    ("energy_state_2", "Energy State: Normal Operation", 2),
    ("energy_state_3", "Energy State: On Recommendation", 3),
    ("energy_state_4", "Energy State: On Command", 4),
    ("energy_state_5", "Energy State: On Command Step 2", 5),
    ("energy_state_6", "Energy State: On Recommendation Step 1", 6),
    ("energy_state_7", "Energy State: Energy Saving Mode", 7),
    ("energy_state_8", "Energy State: Super Energy Saving Mode", 8),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        LGBinarySensor(coordinator, entry, desc) for desc in _BINARY_SENSORS
    ]
    entities.extend(
        LGEnergyStateBinarySensor(coordinator, entry, key, name, value)
        for key, name, value in _ENERGY_STATE_BINARY_SENSORS
    )
    async_add_entities(entities)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="LG ThermaV R290",
        manufacturer="LG",
        model="ThermaV R290",
    )


class LGBinarySensor(CoordinatorEntity[LGThermaVCoordinator], BinarySensorEntity):
    """A binary sensor reading a discrete input from coordinator data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._data_key = description.data_key
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)


class LGEnergyStateBinarySensor(
    CoordinatorEntity[LGThermaVCoordinator], BinarySensorEntity
):
    """Binary sensor that is ON when energy_state_raw matches a specific value."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:transmission-tower"

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        match_value: int,
    ) -> None:
        super().__init__(coordinator)
        self._match_value = match_value
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get("energy_state_raw")
        if raw is None:
            return None
        return int(raw) == self._match_value
