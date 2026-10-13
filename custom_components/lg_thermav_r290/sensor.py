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
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENERGY_REGISTERS,
    CONF_EXPERIMENTAL,
    CONTROL_METHOD_FROM_VALUE,
    DOMAIN,
    ENERGY_STATE_DISPLAY,
    OPERATION_MODE_FROM_VALUE,
)
from .coordinator import LGThermaVCoordinator
from .cop import (
    COP_CURRENT_KEY,
    COP_SYSTEM_KEY,
    ELECTRICAL_POWER_KEY,
    ELECTRICAL_POWER_SYSTEM_KEY,
    THERMAL_POWER_KEY,
    current_cop,
)
from .energy import (
    ELECTRICAL_ENERGY_HEATING_KEY,
    ENERGY_REGISTERS,
    ENERGY_UNIQUE_ID_PREFIX,
    HEATING_COP_KEY,
    KIND_ENERGY,
    KIND_POWER,
    THERMAL_ENERGY_HEATING_KEY,
    EnergyRegister,
    heating_cop,
)
from .experimental import EXPERIMENTAL_REGISTERS, ExperimentalRegister


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
        # A device class makes the unit convertible in the UI (m³/h, gal/min)
        # and gives the sensor the matching icon. It requires Home Assistant's
        # own unit string, "L/min"; the value from the coordinator is still
        # litres per minute, which the thermal power sensors below rely on.
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
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
            ENERGY_STATE_DISPLAY,
            "energy_state_raw",
            "mdi:lightning-bolt",
        )
    )
    # The same 0-8 labels for input 11, the state the unit reports as active.
    # "Energy State" above labels holding 9, the command register; when the
    # SG-Ready state arrives through the unit's contacts rather than a Modbus
    # write, only input 11 may change, so both get a label.
    entities.append(
        LGMappedSensor(
            coordinator,
            entry,
            "energy_state_reported_label",
            "Energy State (Reported)",
            ENERGY_STATE_DISPLAY,
            "energy_state_input",
            "mdi:lightning-bolt-outline",
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
    if entry.options.get(CONF_ENERGY_REGISTERS, False):
        entities.extend(
            LGEnergyRegisterSensor(coordinator, entry, register)
            for register in ENERGY_REGISTERS
        )
        entities.append(LGHeatingCopSensor(coordinator, entry))
    else:
        _remove_sensors(hass, entry, ENERGY_UNIQUE_ID_PREFIX)
    if entry.options.get(CONF_EXPERIMENTAL, False):
        entities.extend(
            LGExperimentalSensor(coordinator, entry, register)
            for register in EXPERIMENTAL_REGISTERS
        )
    else:
        _remove_sensors(hass, entry, "exp_")
    # Current and system COP need the power registers of the energy option; their
    # unique ids carry the energy prefix, so switching the option off removes
    # them too.
    if entry.options.get(CONF_ENERGY_REGISTERS, False):
        entities.append(LGCurrentCopSensor(coordinator, entry))
        entities.append(LGSystemCopSensor(coordinator, entry))
    async_add_entities(entities)


def _remove_sensors(hass: HomeAssistant, entry: ConfigEntry, prefix: str) -> None:
    """Drop an optional group of sensors when its option is switched off.

    Left in the registry they would sit there unavailable for good.
    """
    registry = er.async_get(hass)
    full_prefix = f"{entry.entry_id}_{prefix}"
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == "sensor" and entity.unique_id.startswith(full_prefix):
            registry.async_remove(entity.entity_id)


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


class LGEnergyRegisterSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """A power, energy or plain value from the 32-bit energy block."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        register: EnergyRegister,
    ) -> None:
        super().__init__(coordinator)
        self._data_key = register.data_key
        self._attr_name = register.name
        self._attr_unique_id = f"{entry.entry_id}_{register.data_key}"
        self._attr_device_info = _device_info(entry)
        self._attr_extra_state_attributes = {
            "modbus_register": register.modbus_number,
        }
        if register.kind == KIND_POWER:
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif register.kind == KIND_ENERGY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
            self._attr_suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        else:
            # No unit: demand vs. supply reads 0-12, which is not a percentage.
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)


class LGHeatingCopSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """Cumulative heating COP: input 50 (thermal) / input 40 (electrical).

    Only created with the energy registers option, which provides both
    counters. A long-term average since the counters were last reset, not
    the COP of the moment; see energy.heating_cop.
    """

    _attr_has_entity_name = True
    _attr_name = "Heating COP (Cumulative)"
    _attr_icon = "mdi:heat-pump-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{HEATING_COP_KEY}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        return heating_cop(
            data.get(THERMAL_ENERGY_HEATING_KEY),
            data.get(ELECTRICAL_ENERGY_HEATING_KEY),
        )


class LGExperimentalSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """The raw 16-bit value of a register the manual does not document.

    Unscaled and unsigned, exactly as the device returns it, because what the
    value means is the open question. A measurement state class gives it
    long-term statistics, which is the point: the values are there to be
    compared with the machine's behaviour over weeks.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flask-outline"

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        register: ExperimentalRegister,
    ) -> None:
        super().__init__(coordinator)
        self._data_key = register.key
        self._attr_name = register.name
        self._attr_unique_id = f"{entry.entry_id}_{register.key}"
        self._attr_device_info = _device_info(entry)
        self._attr_extra_state_attributes = {
            "modbus_register": register.modbus_number,
            "register_type": register.kind,
        }

    @property
    def native_value(self) -> int | None:
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


class LGCurrentCopSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """COP of the moment: input 48 (thermal power) / input 36 (electrical).

    Only created with the energy registers option, which provides both. No
    value while the unit idles below cop.MIN_ELECTRICAL_POWER_W; see
    cop.current_cop.
    """

    _attr_has_entity_name = True
    _attr_name = "COP Current"
    _attr_icon = "mdi:heat-pump"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _cop_key = COP_CURRENT_KEY
    _electrical_key = ELECTRICAL_POWER_KEY

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{self._cop_key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        return current_cop(data.get(THERMAL_POWER_KEY), data.get(self._electrical_key))


class LGSystemCopSensor(LGCurrentCopSensor):
    """System COP of the moment: input 48 (thermal) / input 34 (total system).

    Same calculation and idle threshold as COP Current, but over the total
    system's electrical power, which also counts consumers the heat pump
    figure (input 36) leaves out, such as a backup heater. Where 34 and 36
    are equal, both COPs are equal.
    """

    _attr_name = "COP System"
    _attr_icon = "mdi:home-lightning-bolt-outline"
    _cop_key = COP_SYSTEM_KEY
    _electrical_key = ELECTRICAL_POWER_SYSTEM_KEY
