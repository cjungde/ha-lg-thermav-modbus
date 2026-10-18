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
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .capabilities import OPTIONAL_REGISTERS
from .const import (
    CONF_EXPERIMENTAL,
    CONTROL_METHOD_FROM_VALUE,
    DOMAIN,
    ENERGY_STATE_LABELS,
    OPERATION_MODE_FROM_VALUE,
)
from .coordinator import LGThermaVCoordinator
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
    if entry.options.get(CONF_EXPERIMENTAL, False):
        entities.extend(
            LGExperimentalSensor(coordinator, entry, register)
            for register in EXPERIMENTAL_REGISTERS
        )
    else:
        _remove_experimental_entities(hass, entry)
    entities.append(LGOptionalRegisterSensor(coordinator, entry))
    entities.append(LGFlushPulseRuntimeSensor(coordinator, entry))
    entities.append(LGFlushPulseExpectedSensor(coordinator, entry))
    async_add_entities(entities)


def _remove_experimental_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the experimental sensors when the option is switched off.

    Left in the registry they would sit there unavailable for good.
    """
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_exp_"
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == "sensor" and entity.unique_id.startswith(prefix):
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


class LGOptionalRegisterSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """Which of the optional registers this unit serves, and on what grounds.

    Three addresses from the manual are served by some units and not others
    (see capabilities.py). Whether an entity for them exists is decided per
    device, which makes their absence indistinguishable from a bug unless the
    decision itself is visible somewhere. It used to be visible only at INFO
    level and in the storage file -- that is, not at all on an installation
    running the default WARNING.

    The state is how many of them answered. The attributes carry each one's
    verdict and, more importantly, `source`:

    * `hit` -- read from the cache, device confirmed as the same one
    * `positive_only` -- the unit does not say what it is, so a stored "no"
      was discarded and will be probed again. A `false` seen here is this
      session's own measurement, not a remembered one.
    * `miss`, `definitions_changed`, `identity_changed` -- nothing was
      believed; everything was probed in this session
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:format-list-checks"
    # No state class on purpose: this is a property of the hardware, not a
    # measurement, and averaging it over time would mean nothing.

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "Optional Registers"
        self._attr_unique_id = f"{entry.entry_id}_optional_registers"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        return sum(1 for value in self.coordinator.capabilities.values() if value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        known = self.coordinator.capabilities
        attributes: dict[str, Any] = {
            "source": self.coordinator.capability_reason,
            "pending": [
                register.key
                for register in OPTIONAL_REGISTERS
                if register.key not in known
            ],
        }
        for register in OPTIONAL_REGISTERS:
            attributes[register.key] = known.get(register.key)
            attributes[f"{register.key}_register"] = register.description
        return attributes


class LGFlushPulseRuntimeSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """Uninterrupted running time at or below 25 Hz, in minutes.

    This is the unit's own count-down towards the oil-return flush pulse, read
    from the outside. It reaches about 60.5 minutes and then the pulse comes.
    Empty whenever the clock is not running -- the compressor is stopped or out
    of the band -- rather than showing a stale number.
    """

    _attr_has_entity_name = True
    _attr_name = "Flush Pulse Runtime"
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_flush_pulse_runtime"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        runtime = self.coordinator.flush_pulse.runtime_minutes
        return round(runtime, 1) if runtime is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tracker = self.coordinator.flush_pulse
        remaining = tracker.minutes_remaining()
        return {
            "minutes_remaining": round(remaining, 1) if remaining is not None else None,
            "trigger_minutes": tracker.config.trigger_minutes,
            "low_load_rpm": tracker.config.low_load_rpm,
        }


class LGFlushPulseExpectedSensor(CoordinatorEntity[LGThermaVCoordinator], SensorEntity):
    """When the next flush pulse is expected.

    Derived from the clock above plus the measured 60.5 minutes, so it is only
    as good as that figure -- which held for 29 of 29 pulses within half a
    minute. Empty while the clock is not running, because there is then nothing
    to predict: a compressor stop resets the count rather than pausing it.

    After a Home Assistant restart the clock starts from zero while the unit's
    own timer keeps running, so the first prediction after a restart can be
    late. The runtime attribute of the recorded pulse is `null` in that case
    instead of a wrong number.
    """

    _attr_has_entity_name = True
    _attr_name = "Flush Pulse Expected"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-alert-outline"

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_flush_pulse_expected"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        return self.coordinator.flush_pulse.expected_at()
