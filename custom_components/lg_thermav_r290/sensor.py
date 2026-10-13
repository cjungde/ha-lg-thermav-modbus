"""Sensor platform for LG ThermaV R290.

Keys follow docs/naming.md: the entity key is the name as an entity id slug,
the data key is ``<register type>_<what the register holds>``.

Four kinds of sensors:

- register values, read as they are (scaled in the coordinator)
- labels, mapping a register's code to text
- calculated values: thermal power from flow × ΔT and the COPs
- optional groups: the energy registers (with the COPs that need them) and
  the experimental registers
"""

from __future__ import annotations

from collections.abc import Callable
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
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import cop
from .const import (
    CONF_ENERGY_REGISTERS,
    CONF_EXPERIMENTAL,
    CONTROL_METHOD_FROM_VALUE,
    DOMAIN,
    ENERGY_STATE_DISPLAY,
    ODU_OPERATION_CYCLE_LABELS,
    OPERATION_MODE_FROM_VALUE,
)
from .coordinator import LGThermaVCoordinator
from .energy import (
    DATA_KEY_ELECTRICAL_ENERGY_SPACE_HEATING,
    DATA_KEY_ELECTRICAL_POWER_HEAT_PUMP,
    DATA_KEY_ELECTRICAL_POWER_TOTAL_SYSTEM,
    DATA_KEY_THERMAL_ENERGY_SPACE_HEATING,
    DATA_KEY_THERMAL_POWER_REPORTED,
    ENERGY_REGISTERS,
    KIND_ENERGY,
    KIND_POWER,
    EnergyRegister,
)
from .entity import LGEntity, remove_entities
from .experimental import EXPERIMENTAL_REGISTERS, ExperimentalRegister

# Data keys the calculated sensors read.
DATA_KEY_INLET_TEMPERATURE = "input_inlet_temperature"
DATA_KEY_OUTLET_TEMPERATURE = "input_outlet_temperature"
DATA_KEY_FLOW_RATE = "input_flow_rate"
DATA_KEY_DHW_HEATING = "discrete_dhw_heating"

# Entity keys created by each option, for removing them when it is switched off.
ENERGY_OPTION_KEYS = (*(r.key for r in ENERGY_REGISTERS), *cop.COP_KEYS)
EXPERIMENTAL_OPTION_KEYS = tuple(r.key for r in EXPERIMENTAL_REGISTERS)


# --- Register values --------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class LGSensorDescription(SensorEntityDescription):
    data_key: str


def _temperature(
    key: str, data_key: str, name: str, *, enabled: bool = True
) -> LGSensorDescription:
    return LGSensorDescription(
        key=key,
        data_key=data_key,
        name=name,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled,
    )


def _pressure(key: str, data_key: str, name: str) -> LGSensorDescription:
    return LGSensorDescription(
        key=key,
        data_key=data_key,
        name=name,
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    )


_SENSORS: tuple[LGSensorDescription, ...] = (
    # Input registers: water side
    _temperature("inlet_temperature", "input_inlet_temperature", "Inlet Temperature"),
    _temperature(
        "outlet_temperature", "input_outlet_temperature", "Outlet Temperature"
    ),
    _temperature(
        "backup_heater_outlet_temperature",
        "input_backup_heater_outlet_temperature",
        "Backup Heater Outlet Temperature",
    ),
    _temperature("dhw_temperature", "input_dhw_temperature", "DHW Temperature"),
    _temperature(
        "solar_collector_temperature",
        "input_solar_collector_temperature",
        "Solar Collector Temperature",
    ),
    _temperature(
        "room_air_temperature_circuit_1",
        "input_room_air_temperature_circuit_1",
        "Room Air Temperature Circuit 1",
    ),
    _temperature(
        "room_air_temperature_circuit_2",
        "input_room_air_temperature_circuit_2",
        "Room Air Temperature Circuit 2",
    ),
    _temperature(
        "flow_temperature_circuit_2",
        "input_flow_temperature_circuit_2",
        "Flow Temperature Circuit 2",
    ),
    _temperature(
        "outdoor_temperature", "input_outdoor_temperature", "Outdoor Temperature"
    ),
    LGSensorDescription(
        key="flow_rate",
        data_key="input_flow_rate",
        name="Flow Rate",
        # A device class makes the unit convertible in the UI (m³/h, gal/min)
        # and gives the sensor the matching icon. It requires Home Assistant's
        # own unit string, "L/min"; the value is still litres per minute, which
        # the calculated thermal power relies on.
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _pressure("water_pressure", "input_water_pressure", "Water Pressure"),
    # Input registers: refrigerant side
    _temperature(
        "liquid_gas_temperature",
        "input_liquid_gas_temperature",
        "Liquid Gas Temperature",
    ),
    _temperature(
        "suction_temperature", "input_suction_temperature", "Suction Temperature"
    ),
    _temperature(
        "hot_gas_temperature", "input_hot_gas_temperature", "Hot Gas Temperature"
    ),
    _temperature(
        "temperature_before_evaporator",
        "input_temperature_before_evaporator",
        "Temperature Before Evaporator",
    ),
    _temperature(
        "temperature_after_evaporator",
        "input_temperature_after_evaporator",
        "Temperature After Evaporator",
    ),
    _pressure(
        "high_pressure_condenser",
        "input_high_pressure_condenser",
        "High Pressure (Condenser)",
    ),
    _pressure(
        "low_pressure_evaporator",
        "input_low_pressure_evaporator",
        "Low Pressure (Evaporator)",
    ),
    LGSensorDescription(
        key="compressor_speed",
        data_key="input_compressor_speed",
        name="Compressor Speed",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Input registers: status and identity
    LGSensorDescription(
        key="error_code",
        data_key="input_error_code",
        name="Error Code",
        icon="mdi:alert-circle",
        # Codes, not quantities: the hourly mean means little, but a state
        # class keeps them in long-term statistics (min/max per hour show any
        # code that occurred) instead of losing them with the recorder purge.
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="operation_cycle_odu",
        data_key="input_operation_cycle_odu",
        name="Operation Cycle (ODU)",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="energy_control_signal",
        data_key="input_energy_control_signal",
        name="Energy Control Signal",
        icon="mdi:transmission-tower",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="device_group",
        data_key="input_device_group",
        name="Device Group",
        icon="mdi:information",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    LGSensorDescription(
        key="product_information",
        data_key="input_product_information",
        name="Product Information",
        icon="mdi:information",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # Holding-register read-back of the room temperatures (may match the input
    # registers; disabled by default)
    _temperature(
        "room_air_temperature_circuit_1_holding",
        "holding_room_air_temperature_circuit_1",
        "Room Air Temperature Circuit 1 (Holding)",
        enabled=False,
    ),
    _temperature(
        "room_air_temperature_circuit_2_holding",
        "holding_room_air_temperature_circuit_2",
        "Room Air Temperature Circuit 2 (Holding)",
        enabled=False,
    ),
)


# --- Labels -----------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class LGLabelSensorDescription(SensorEntityDescription):
    data_key: str
    labels: dict[int, str]


_LABEL_SENSORS: tuple[LGLabelSensorDescription, ...] = (
    LGLabelSensorDescription(
        key="operation_mode",
        data_key="holding_operation_mode",
        labels=OPERATION_MODE_FROM_VALUE,
        name="Operation Mode",
        icon="mdi:heat-pump",
    ),
    LGLabelSensorDescription(
        key="control_method",
        data_key="holding_control_method",
        labels=CONTROL_METHOD_FROM_VALUE,
        name="Control Method",
        icon="mdi:tune",
    ),
    # Input 30002, the outdoor unit's cycle; the raw value stays available as
    # "Operation Cycle (ODU)", so its history and automations are untouched.
    LGLabelSensorDescription(
        key="operation_state_odu",
        data_key="input_operation_cycle_odu",
        labels=ODU_OPERATION_CYCLE_LABELS,
        name="Operation State (ODU)",
        icon="mdi:hvac",
    ),
    # Holding 9, the energy state command register.
    LGLabelSensorDescription(
        key="energy_state",
        data_key="holding_energy_state",
        labels=ENERGY_STATE_DISPLAY,
        name="Energy State",
        icon="mdi:lightning-bolt",
    ),
    # The same 0-8 labels for input 11, the state the unit reports as active.
    # When the SG-Ready state arrives through the unit's contacts rather than a
    # Modbus write, only input 11 may change, so both get a label.
    LGLabelSensorDescription(
        key="energy_state_reported",
        data_key="input_energy_control_signal",
        labels=ENERGY_STATE_DISPLAY,
        name="Energy State (Reported)",
        icon="mdi:lightning-bolt-outline",
    ),
)


# --- Calculated values ------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class LGCalculatedSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


def _thermal_power(data: dict[str, Any], dhw: bool | None) -> int | None:
    """Flow × ΔT; with dhw set, only while DHW heating is (True) / is not (False) on."""
    power = cop.thermal_power_w(
        data.get(DATA_KEY_FLOW_RATE),
        data.get(DATA_KEY_INLET_TEMPERATURE),
        data.get(DATA_KEY_OUTLET_TEMPERATURE),
    )
    if power is None or dhw is None:
        return power
    dhw_heating = data.get(DATA_KEY_DHW_HEATING)
    if dhw_heating is None:
        return None
    return power if bool(dhw_heating) == dhw else 0


def _thermal_power_description(
    key: str, name: str, dhw: bool | None
) -> LGCalculatedSensorDescription:
    return LGCalculatedSensorDescription(
        key=key,
        name=name,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:heat-wave",
        value_fn=lambda data: _thermal_power(data, dhw),
    )


# Q = flow/60 × ΔT × 4186 W, always created. The heating circuit / DHW split
# follows discrete input 10006 (DHW heating): while it is on, the full flow
# counts as DHW and the heating circuit reports 0, and vice versa.
_THERMAL_POWER_SENSORS: tuple[LGCalculatedSensorDescription, ...] = (
    _thermal_power_description(
        "thermal_power_calculated", "Thermal Power (Calculated)", None
    ),
    _thermal_power_description(
        "thermal_power_heating_circuit_calculated",
        "Thermal Power Heating Circuit (Calculated)",
        False,
    ),
    _thermal_power_description(
        "thermal_power_dhw_calculated", "Thermal Power DHW (Calculated)", True
    ),
)


def _cop_description(
    key: str, name: str, icon: str, value_fn: Callable[[dict[str, Any]], Any]
) -> LGCalculatedSensorDescription:
    return LGCalculatedSensorDescription(
        key=key,
        name=name,
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=value_fn,
    )


# Created with the energy registers option, which provides the power and
# energy values they divide (see cop.py).
_COP_SENSORS: tuple[LGCalculatedSensorDescription, ...] = (
    _cop_description(
        cop.KEY_COP_REPORTED,
        "COP (Reported)",
        "mdi:heat-pump",
        lambda data: cop.instantaneous_cop(
            data.get(DATA_KEY_THERMAL_POWER_REPORTED),
            data.get(DATA_KEY_ELECTRICAL_POWER_HEAT_PUMP),
        ),
    ),
    _cop_description(
        cop.KEY_COP_SYSTEM_REPORTED,
        "COP System (Reported)",
        "mdi:home-lightning-bolt-outline",
        lambda data: cop.instantaneous_cop(
            data.get(DATA_KEY_THERMAL_POWER_REPORTED),
            data.get(DATA_KEY_ELECTRICAL_POWER_TOTAL_SYSTEM),
        ),
    ),
    _cop_description(
        cop.KEY_COP_CALCULATED,
        "COP (Calculated)",
        "mdi:calculator-variant-outline",
        lambda data: cop.instantaneous_cop(
            _thermal_power(data, None), data.get(DATA_KEY_ELECTRICAL_POWER_HEAT_PUMP)
        ),
    ),
    _cop_description(
        cop.KEY_COP_HEATING_CUMULATIVE,
        "COP Heating (Cumulative)",
        "mdi:heat-pump-outline",
        lambda data: cop.cumulative_cop(
            data.get(DATA_KEY_THERMAL_ENERGY_SPACE_HEATING),
            data.get(DATA_KEY_ELECTRICAL_ENERGY_SPACE_HEATING),
        ),
    ),
)


# --- Setup ------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        *(LGSensor(coordinator, entry, d) for d in _SENSORS),
        *(LGLabelSensor(coordinator, entry, d) for d in _LABEL_SENSORS),
        *(LGCalculatedSensor(coordinator, entry, d) for d in _THERMAL_POWER_SENSORS),
    ]
    if entry.options.get(CONF_ENERGY_REGISTERS, False):
        entities.extend(LGEnergySensor(coordinator, entry, r) for r in ENERGY_REGISTERS)
        entities.extend(LGCalculatedSensor(coordinator, entry, d) for d in _COP_SENSORS)
    else:
        remove_entities(hass, entry, "sensor", ENERGY_OPTION_KEYS)
    if entry.options.get(CONF_EXPERIMENTAL, False):
        entities.extend(
            LGExperimentalSensor(coordinator, entry, r) for r in EXPERIMENTAL_REGISTERS
        )
    else:
        remove_entities(hass, entry, "sensor", EXPERIMENTAL_OPTION_KEYS)
    async_add_entities(entities)


# --- Entities ---------------------------------------------------------------


class LGSensor(LGEntity, SensorEntity):
    """A register value, read from the coordinator data as it is."""

    entity_description: LGSensorDescription

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self._data(self.entity_description.data_key)


class LGLabelSensor(LGEntity, SensorEntity):
    """A register code shown as text; a code without a label shows as the number."""

    entity_description: LGLabelSensorDescription

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGLabelSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | None:
        raw = self._data(self.entity_description.data_key)
        if raw is None:
            return None
        return self.entity_description.labels.get(raw, str(raw))

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        # The code behind the text, as a number. A text state cannot go into
        # long-term statistics or a numeric time series database (Influx/
        # VictoriaMetrics drop string fields); a numeric attribute is exported
        # as a field by the influxdb integration and arrives there.
        return {"register_value": self._data(self.entity_description.data_key)}


class LGCalculatedSensor(LGEntity, SensorEntity):
    """A value calculated from the coordinator data (thermal power, COP)."""

    entity_description: LGCalculatedSensorDescription

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGCalculatedSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class LGEnergySensor(LGEntity, SensorEntity):
    """A power, energy or plain value from the 32-bit energy block."""

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        register: EnergyRegister,
    ) -> None:
        super().__init__(coordinator, entry, register.key)
        self._data_key = register.data_key
        self._attr_name = register.name
        self._attr_extra_state_attributes = {"modbus_register": register.modbus_number}
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
        return self._data(self._data_key)


class LGExperimentalSensor(LGEntity, SensorEntity):
    """The raw 16-bit value of a register the manual does not document.

    Unscaled and unsigned, exactly as the device returns it, because what the
    value means is the open question. A measurement state class gives it
    long-term statistics, which is the point: the values are there to be
    compared with the machine's behaviour over weeks.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flask-outline"

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        register: ExperimentalRegister,
    ) -> None:
        super().__init__(coordinator, entry, register.key)
        self._data_key = register.data_key
        self._attr_name = register.name
        self._attr_extra_state_attributes = {
            "modbus_register": register.modbus_number,
            "register_type": register.kind,
        }

    @property
    def native_value(self) -> int | None:
        return self._data(self._data_key)
