"""Binary sensor platform for LG Therma V R290 — discrete inputs.

Keys follow docs/naming.md: the entity key is the name as an entity id slug,
the data key is ``discrete_<key>``.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ENERGY_STATE_LABELS
from .coordinator import LGThermaVCoordinator
from .entity import LGEntity, english_entity_ids


@dataclass(frozen=True, kw_only=True)
class LGBinarySensorDescription(BinarySensorEntityDescription):
    data_key: str


def _discrete(
    key: str, name: str, device_class: BinarySensorDeviceClass | None = None
) -> LGBinarySensorDescription:
    return LGBinarySensorDescription(
        key=key, data_key=f"discrete_{key}", name=name, device_class=device_class
    )


_BINARY_SENSORS: tuple[LGBinarySensorDescription, ...] = (
    # Discrete input 10001 is set while water flows, the reverse of what the
    # manual says (see the comment in coordinator.py).
    _discrete("water_flow", "Water Flow", BinarySensorDeviceClass.RUNNING),
    _discrete("water_pump", "Water Pump", BinarySensorDeviceClass.RUNNING),
    _discrete(
        "external_water_pump", "External Water Pump", BinarySensorDeviceClass.RUNNING
    ),
    _discrete("compressor", "Compressor", BinarySensorDeviceClass.RUNNING),
    _discrete("defrost", "Defrost", BinarySensorDeviceClass.RUNNING),
    _discrete("dhw_heating", "DHW Heating", BinarySensorDeviceClass.RUNNING),
    _discrete("dhw_disinfection", "DHW Disinfection", BinarySensorDeviceClass.RUNNING),
    _discrete("silent_mode", "Silent Mode"),
    # Not reliable on the R290: set while heating (README, discrete input 10009).
    _discrete("cooling_active", "Cooling Active", BinarySensorDeviceClass.COLD),
    _discrete("solar_pump", "Solar Pump", BinarySensorDeviceClass.RUNNING),
    _discrete(
        "backup_heater_step_1", "Backup Heater Step 1", BinarySensorDeviceClass.HEAT
    ),
    _discrete(
        "backup_heater_step_2", "Backup Heater Step 2", BinarySensorDeviceClass.HEAT
    ),
    _discrete("dhw_boost_heater", "DHW Boost Heater", BinarySensorDeviceClass.HEAT),
    _discrete("fault", "Fault", BinarySensorDeviceClass.PROBLEM),
    _discrete(
        "emergency_heating_cooling_available", "Emergency Heating/Cooling Available"
    ),
    _discrete("emergency_dhw_available", "Emergency DHW Available"),
    _discrete("mixing_pump", "Mixing Pump", BinarySensorDeviceClass.RUNNING),
)


def _energy_state_key(label: str) -> str:
    """energy_state_<label slug>, e.g. energy_state_normal_operation."""
    return "energy_state_" + label.lower().replace(" ", "_")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        LGBinarySensor(coordinator, entry, description)
        for description in _BINARY_SENSORS
    ]
    entities.extend(
        LGEnergyStateBinarySensor(coordinator, entry, value, label)
        for value, label in ENERGY_STATE_LABELS.items()
    )
    async_add_entities(english_entity_ids("binary_sensor", entities))


class LGBinarySensor(LGEntity, BinarySensorEntity):
    """A binary sensor reading a discrete input from coordinator data."""

    entity_description: LGBinarySensorDescription

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        value = self._data(self.entity_description.data_key)
        return None if value is None else bool(value)


class LGEnergyStateBinarySensor(LGEntity, BinarySensorEntity):
    """On while the energy state (holding 9) has one particular value."""

    _attr_icon = "mdi:transmission-tower"

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        value: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry, _energy_state_key(label))
        self._value = value

    @property
    def is_on(self) -> bool | None:
        raw = self._data("holding_energy_state")
        if raw is None:
            return None
        return int(raw) == self._value
