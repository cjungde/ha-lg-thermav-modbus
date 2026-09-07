"""Sensor platform for LG ThermaV R290."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONTROL_METHOD_FROM_VALUE,
    DOMAIN,
    ENERGY_STATE_LABELS,
    OPERATION_MODE_FROM_VALUE,
)
from .coordinator import LGThermaVCoordinator


@dataclass(frozen=True, kw_only=True)
class LGSensorDescription(SensorEntityDescription):
    data_key: str = ""


_SENSORS: tuple[LGSensorDescription, ...] = (
    # --- Input registers: temperatures ---
    LGSensorDescription(
        key="inlet_temp",
        data_key="inlet_temp",
        name="Inlet Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="outlet_temp",
        data_key="outlet_temp",
        name="Outlet Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="backup_heater_outlet_temp",
        data_key="backup_heater_outlet_temp",
        name="Backup Heater Outlet Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="dhw_water_temp",
        data_key="dhw_water_temp",
        name="DHW Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="solar_collector_temp",
        data_key="solar_collector_temp",
        name="Solar Collector Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="room_air_temp_circuit1",
        data_key="room_air_temp_circuit1",
        name="Room Air Temperature Circuit 1",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="flow_temp_circle_2",
        data_key="flow_temp_circle_2",
        name="Flow Temperature Circuit 2",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="outside_temp",
        data_key="outside_temp",
        name="Outdoor Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="temp_liquid_gas",
        data_key="temp_liquid_gas",
        name="Liquid Gas Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="temp_suction",
        data_key="temp_suction",
        name="Suction Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="temp_heatgas",
        data_key="temp_heatgas",
        name="Hot Gas Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="temp_before_vaporiser",
        data_key="temp_before_vaporiser",
        name="Temperature Before Evaporator",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="temp_after_vaporiser",
        data_key="temp_after_vaporiser",
        name="Temperature After Evaporator",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # --- Input registers: other ---
    LGSensorDescription(
        key="flow_rate",
        data_key="flow_rate",
        name="Flow Rate",
        native_unit_of_measurement="l/min",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="room_air_temp_circuit2_in",
        data_key="room_air_temp_circuit2_in",
        name="Room Air Temperature Circuit 2",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="water_pressure",
        data_key="water_pressure",
        name="Water Pressure",
        native_unit_of_measurement="bar",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="high_pressure",
        data_key="high_pressure",
        name="High Pressure (Condenser)",
        native_unit_of_measurement="bar",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="low_pressure",
        data_key="low_pressure",
        name="Low Pressure (Evaporator)",
        native_unit_of_measurement="bar",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="compressor_rpm",
        data_key="compressor_rpm",
        name="Compressor Speed",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="error_code",
        data_key="error_code",
        name="Error Code",
        icon="mdi:alert-circle",
    ),
    LGSensorDescription(
        key="odu_operation_cycle",
        data_key="odu_operation_cycle",
        name="Operation Cycle (ODU)",
    ),
    LGSensorDescription(
        key="device_group",
        data_key="device_group",
        name="Device Group",
        icon="mdi:information",
        entity_registry_enabled_default=False,
    ),
    LGSensorDescription(
        key="product_info",
        data_key="product_info",
        name="Product Information",
        icon="mdi:information",
        entity_registry_enabled_default=False,
    ),
    LGSensorDescription(
        key="energy_state_input",
        data_key="energy_state_input",
        name="Energy Control Signal",
        icon="mdi:transmission-tower",
    ),
    # Holding-register read-back of room temps (may match input register; disabled by default)
    LGSensorDescription(
        key="room_air_temp_circuit1_hold",
        data_key="room_air_temp_circuit1_hold",
        name="Room Air Temperature Circuit 1 (Holding)",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    LGSensorDescription(
        key="room_air_temp_circuit2_hold",
        data_key="room_air_temp_circuit2_hold",
        name="Room Air Temperature Circuit 2 (Holding)",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        LGSensor(coordinator, entry, desc) for desc in _SENSORS
    ]
    # Special mapped sensors
    entities.append(
        LGMappedSensor(
            coordinator,
            entry,
            "operation_mode_label",
            "Operation Mode",
            OPERATION_MODE_FROM_VALUE,
            "operation_mode",
            "mdi:heat-pump",
        )
    )
    entities.append(
        LGMappedSensor(
            coordinator,
            entry,
            "control_method_label",
            "Control Method",
            CONTROL_METHOD_FROM_VALUE,
            "control_method",
            "mdi:tune",
        )
    )
    entities.append(
        LGMappedSensor(
            coordinator,
            entry,
            "energy_state_label",
            "Energy State",
            ENERGY_STATE_LABELS,
            "energy_state_raw",
            "mdi:lightning-bolt",
        )
    )
    # Computed thermal power sensors (Q = flow/60 * ΔT * cp_water)
    entities.append(
        LGThermalPowerSensor(
            coordinator,
            entry,
            "thermal_power_total",
            "Thermal Power Total",
            dhw_filter=None,
        )
    )
    entities.append(
        LGThermalPowerSensor(
            coordinator,
            entry,
            "thermal_power_dhw",
            "Thermal Power DHW",
            dhw_filter=True,
        )
    )
    entities.append(
        LGThermalPowerSensor(
            coordinator,
            entry,
            "thermal_power_heating_circuit",
            "Thermal Power Heating Circuit",
            dhw_filter=False,
        )
    )
    async_add_entities(entities)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="LG ThermaV R290",
        manufacturer="LG",
        model="ThermaV R290",
    )


class LGSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """A sensor reading a value directly from coordinator data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._data_key = description.data_key
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)


class LGMappedSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """A sensor that maps a raw integer register value to a human-readable string."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        mapping: dict[int, str],
        data_key: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._mapping = mapping
        self._data_key = data_key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry)
        self._attr_icon = icon

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._data_key)
        if raw is None:
            return None
        return self._mapping.get(raw, str(raw))


class LGThermalPowerSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """Computes thermal power output: Q = (flow_rate / 60) × ΔT × 4186 W.

    dhw_filter=True  → only when DHW heating is active (Warmwasser)
    dhw_filter=False → only when DHW heating is inactive (Heizkreis)
    dhw_filter=None  → always (Gesamt)
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:heat-wave"

    # Specific heat capacity of water [J/(kg·K)] × density [kg/l] = 4186 J/l/K
    _CP_WATER = 4186.0

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        dhw_filter: bool | None,
    ) -> None:
        super().__init__(coordinator)
        self._dhw_filter = dhw_filter
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int | None:
        d = self.coordinator.data
        if d is None:
            return None
        inlet = d.get("inlet_temp")
        outlet = d.get("outlet_temp")
        flow = d.get("flow_rate")
        if inlet is None or outlet is None or flow is None:
            return None
        # Apply DHW filter if set
        if self._dhw_filter is not None:
            dhw_on = d.get("di_dhw_heating")
            if dhw_on is None:
                return None
            if bool(dhw_on) != self._dhw_filter:
                return 0
        delta_t = float(outlet) - float(inlet)
        flow_ls = float(flow) / 60.0  # l/min → l/s
        power_w = flow_ls * delta_t * self._CP_WATER
        return max(0, int(round(power_w)))
