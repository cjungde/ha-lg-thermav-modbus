"""Sensor platform for LG Therma V R290.

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
import contextlib
from dataclasses import dataclass
import time
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter, PowerConverter

from . import compressor_stats, cop, external_meter, pollstats, register_status
from .const import (
    CONF_COMPRESSOR_STATISTICS,
    CONF_ENERGY_REGISTERS,
    CONF_EXPERIMENTAL,
    CONF_EXTERNAL_ENERGY,
    CONF_EXTERNAL_POWER,
    CONF_POLL_STATISTICS,
    CONTROL_METHOD_FROM_VALUE,
    DOMAIN,
    ENERGY_STATE_DISPLAY,
    ODU_OPERATION_CYCLE_LABELS,
    OPERATION_MODE_FROM_VALUE,
)
from .coordinator import DATA_KEY_OPTIONAL_REGISTERS, LGThermaVCoordinator
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
from .entity import LGEntity, english_entity_ids, remove_entities
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
    # Input 39998 / 39999: read once per start (or reload), not per poll, so
    # being enabled costs nothing on the bus. Shown as the raw numbers.
    LGSensorDescription(
        key="device_group",
        data_key="input_device_group",
        name="Device Group",
        icon="mdi:information",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LGSensorDescription(
        key="product_information",
        data_key="input_product_information",
        name="Product Information",
        icon="mdi:information",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Holding 40004 / 40007, "Raumlufttemp. Kreislauf 1/2" in the manual's
    # holding table: the room temperature target (the measured value is input
    # 30008 / 30011). Read only; whether writing them has an effect is
    # untested. Disabled by default.
    _temperature(
        "target_room_air_temperature_circuit_1",
        "holding_target_room_air_temperature_circuit_1",
        "Target Room Air Temperature Circuit 1",
        enabled=False,
    ),
    _temperature(
        "target_room_air_temperature_circuit_2",
        "holding_target_room_air_temperature_circuit_2",
        "Target Room Air Temperature Circuit 2",
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


# How long a poll takes and how much of the poll interval that is (see
# pollstats.py). Diagnostic, created only with the poll statistics option:
# they change on every poll, so they are not there unless asked for.
_POLL_SENSORS: tuple[LGSensorDescription, ...] = (
    LGSensorDescription(
        key=pollstats.KEY_POLL_DURATION,
        data_key=pollstats.DATA_KEY_POLL_DURATION,
        name="Poll Duration",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        device_class=SensorDeviceClass.DURATION,
        suggested_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LGSensorDescription(
        key=pollstats.KEY_BUS_LOAD,
        data_key=pollstats.DATA_KEY_BUS_LOAD,
        name="Bus Load",
        icon="mdi:gauge",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


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
        LGOptionalRegistersSensor(coordinator, entry),
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
    if entry.options.get(CONF_COMPRESSOR_STATISTICS, False):
        entities.extend(
            [
                LGCompressorStartsSensor(coordinator, entry),
                LGCompressorRunTimeSensor(coordinator, entry),
                LGCompressorAverageSpeedSensor(coordinator, entry),
            ]
        )
    else:
        remove_entities(hass, entry, "sensor", compressor_stats.KEYS)
    power_sensor = entry.options.get(CONF_EXTERNAL_POWER)
    energy_sensor = entry.options.get(CONF_EXTERNAL_ENERGY)
    if power_sensor:
        entities.append(LGExternalMeterCopSensor(coordinator, entry, power_sensor))
    else:
        remove_entities(hass, entry, "sensor", external_meter.POWER_KEYS)
    if energy_sensor:
        entities.append(LGThermalEnergySensor(coordinator, entry))
        entities.append(LGCumulativeCopSensor(coordinator, entry, energy_sensor))
    else:
        remove_entities(hass, entry, "sensor", external_meter.ENERGY_KEYS)
    if entry.options.get(CONF_POLL_STATISTICS, False):
        entities.extend(LGPollSensor(coordinator, entry, d) for d in _POLL_SENSORS)
    else:
        remove_entities(hass, entry, "sensor", tuple(d.key for d in _POLL_SENSORS))
    async_add_entities(english_entity_ids("sensor", entities))


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
        # One translation per register type, with the number as placeholder:
        # "Experimental Input 30015" / "Experimentelles Input-Register 30015".
        super().__init__(
            coordinator, entry, register.key, f"experimental_{register.kind}"
        )
        self._attr_translation_placeholders = {"register": str(register.modbus_number)}
        self._data_key = register.data_key
        self._attr_extra_state_attributes = {
            "modbus_register": register.modbus_number,
            "register_type": register.kind,
        }

    @property
    def available(self) -> bool:
        # Unavailable while its block is not read: missed in this poll, or
        # given up on because the unit does not answer it (see BlockGate).
        return super().available and self._data(self._data_key) is not None

    @property
    def native_value(self) -> int | None:
        return self._data(self._data_key)


class LGOptionalRegistersSensor(LGEntity, SensorEntity):
    """What the optional reads have done since start (register_status.py).

    The state is the worst of the optional groups that are on: ok, paused
    (answered before, resting after a few misses) or given up (never
    answered; see Settings > Repairs), or not used when none is on. The
    attributes have each group's status since start and what the last check
    under Configure found, so it is visible why an entity is unavailable.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = register_status.STATES
    _attr_icon = "mdi:format-list-checks"

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "optional_registers")
        self._entry = entry

    @property
    def native_value(self) -> str | None:
        snapshot = self._data(DATA_KEY_OPTIONAL_REGISTERS)
        if snapshot is None:
            return None
        return register_status.overall_state(snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self._data(DATA_KEY_OPTIONAL_REGISTERS) or {}
        return register_status.attributes(snapshot, dict(self._entry.options))


class LGPollSensor(LGSensor):
    """Poll Duration / Bus Load, with the requests of the poll as attribute."""

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        return {"requests": self._data(pollstats.DATA_KEY_POLL_REQUESTS)}


# --- External electricity meter (external_meter.py) --------------------------


def _monotonic() -> float:
    """The clock the energy integration runs on (replaced in tests)."""
    return time.monotonic()


def _external_value(hass, entity_id: str, converter, unit: str) -> float | None:
    """A sensor of the user's meter, converted to W or kWh; None if unusable."""
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    from_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if from_unit is None:
        return None
    try:
        return converter.convert(value, from_unit, unit)
    except HomeAssistantError:
        return None


class LGExternalMeterCopSensor(LGEntity, SensorEntity):
    """COP of the moment: flow × ΔT over the power of the user's own meter.

    Like the other COPs, no value while the meter shows less than
    cop.MIN_ELECTRICAL_POWER_W (standby). Updated on every poll.
    """

    _attr_icon = "mdi:heat-pump-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(
        self, coordinator: LGThermaVCoordinator, entry: ConfigEntry, power_sensor: str
    ) -> None:
        super().__init__(coordinator, entry, external_meter.KEY_COP_EXTERNAL_METER)
        self._power_sensor = power_sensor
        self._attr_extra_state_attributes = {"power_sensor": power_sensor}

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        power = _external_value(
            self.hass, self._power_sensor, PowerConverter, UnitOfPower.WATT
        )
        thermal = _thermal_power(self.coordinator.data, None)
        return cop.instantaneous_cop(thermal, power)


class LGThermalEnergySensor(LGEntity, RestoreEntity, SensorEntity):
    """Thermal power (Calculated) added up over time, in kWh.

    A counter of its own, independent of the unit's thermal counter. Kept
    across restarts; the time Home Assistant is down is a gap, not counted.
    """

    _attr_icon = "mdi:heat-wave"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator, entry, external_meter.KEY_THERMAL_ENERGY_CALCULATED
        )
        self._integrator = external_meter.EnergyIntegrator()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            with contextlib.suppress(ValueError):
                self._integrator.kwh = float(last.state)
        self._sample()

    def _sample(self) -> None:
        data = self.coordinator.data
        power = _thermal_power(data, None) if data else None
        self._integrator.add(power, _monotonic())

    def _handle_coordinator_update(self) -> None:
        self._sample()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        return round(self._integrator.kwh, 3)


class _CumulativeCopData(ExtraStoredData):
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def as_dict(self) -> dict[str, Any]:
        return self._data


class LGCumulativeCopSensor(LGEntity, RestoreEntity, SensorEntity):
    """Thermal energy over the meter's energy since the option was set up (JAZ).

    Both sides are counted from the same moment: the thermal energy by adding
    up flow × ΔT, the electrical energy as the growth of the meter's counter
    (a reset of the meter counts as growth from zero). Both are kept across
    restarts. Switching the option off and on again starts a new period.
    """

    _attr_icon = "mdi:chart-timeline-variant"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(
        self, coordinator: LGThermaVCoordinator, entry: ConfigEntry, energy_sensor: str
    ) -> None:
        super().__init__(
            coordinator, entry, external_meter.KEY_COP_CUMULATIVE_EXTERNAL_METER
        )
        self._energy_sensor = energy_sensor
        self._thermal = external_meter.EnergyIntegrator()
        self._electrical = external_meter.CounterDelta()
        self._since: str | None = None

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return _CumulativeCopData(
            {
                **external_meter.state(self._thermal, self._electrical),
                "since": self._since,
                "energy_sensor": self._energy_sensor,
            }
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_extra_data()
        stored = last.as_dict() if last is not None else {}
        # A different meter starts a new period: its counter is another one.
        if stored.get("energy_sensor") == self._energy_sensor:
            self._thermal.kwh = float(stored.get("thermal_kwh") or 0.0)
            self._electrical.kwh = float(stored.get("electrical_kwh") or 0.0)
            self._electrical.last = stored.get("electrical_last")
            self._since = stored.get("since")
        if self._since is None:
            self._since = dt_util.utcnow().isoformat()
        self._sample()

    def _sample(self) -> None:
        data = self.coordinator.data
        power = _thermal_power(data, None) if data else None
        self._thermal.add(power, _monotonic())
        self._electrical.add(
            _external_value(
                self.hass,
                self._energy_sensor,
                EnergyConverter,
                UnitOfEnergy.KILO_WATT_HOUR,
            )
        )

    def _handle_coordinator_update(self) -> None:
        self._sample()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float | None:
        return external_meter.ratio(self._thermal.kwh, self._electrical.kwh)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "energy_sensor": self._energy_sensor,
            "since": self._since,
            "thermal_energy_kwh": round(self._thermal.kwh, 3),
            "electrical_energy_kwh": round(self._electrical.kwh, 3),
        }


# --- Compressor statistics (compressor_stats.py) -----------------------------


class _CompressorStatsData(ExtraStoredData):
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def as_dict(self) -> dict[str, Any]:
        return self._data


class LGCompressorStartsSensor(LGEntity, RestoreEntity, SensorEntity):
    """How often the compressor started; also keeps all counts over restarts.

    The coordinator does the counting; this entity stores the whole state as
    restore data, so starts, run time and today's average continue after a
    restart.
    """

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, compressor_stats.KEY_COMPRESSOR_STARTS)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_extra_data()
        if last is not None and self.coordinator.compressor_stats is not None:
            self.coordinator.compressor_stats.restore(last.as_dict())

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        stats = self.coordinator.compressor_stats
        return _CompressorStatsData(stats.state() if stats else {})

    @property
    def native_value(self) -> int | None:
        stats = self.coordinator.compressor_stats
        return None if stats is None else stats.starts

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.coordinator.compressor_stats
        last = None if stats is None else stats.last_run_s
        return {"last_run_minutes": None if last is None else round(last / 60, 1)}


class LGCompressorRunTimeSensor(LGEntity, SensorEntity):
    """Hours the compressor ran, a total counter."""

    _attr_icon = "mdi:timer-cog-outline"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, compressor_stats.KEY_COMPRESSOR_RUN_TIME)

    @property
    def native_value(self) -> float | None:
        stats = self.coordinator.compressor_stats
        return None if stats is None else round(stats.run_hours, 3)


class LGCompressorAverageSpeedSensor(LGEntity, SensorEntity):
    """Average compressor speed while running, today (reset at midnight)."""

    _attr_icon = "mdi:speedometer"
    _attr_native_unit_of_measurement = "rpm"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator, entry, compressor_stats.KEY_COMPRESSOR_AVERAGE_SPEED
        )

    @property
    def native_value(self) -> int | None:
        stats = self.coordinator.compressor_stats
        return None if stats is None else stats.average_rpm_today

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.coordinator.compressor_stats
        if stats is None:
            return {}
        return {"day": stats.day, "run_hours_today": round(stats.day_run_s / 3600, 2)}
