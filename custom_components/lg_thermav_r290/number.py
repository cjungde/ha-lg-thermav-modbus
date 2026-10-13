"""Number platform for LG ThermaV R290 — writable holding registers.

Keys follow docs/naming.md: the entity key is the name as an entity id slug,
the data key is ``holding_<what the register holds>``. The coordinator data
already carries the scaled, signed value; writes scale back to the register.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import limits, power_limit
from .const import CONF_MODULATION_LIMIT, CONF_POWER_LIMIT, DOMAIN
from .coordinator import LGThermaVCoordinator
from .entity import LGEntity, remove_entities


@dataclass(frozen=True, kw_only=True)
class LGNumberDescription(NumberEntityDescription):
    data_key: str
    register_address: int
    # Factor from the displayed value to the register value (display × scale).
    write_scale: float = 1.0
    signed: bool = False


def _temperature(
    key: str,
    data_key: str,
    address: int,
    name: str,
    minimum: int,
    maximum: int,
    icon: str,
    *,
    write_scale: float = 10.0,
    signed: bool = False,
) -> LGNumberDescription:
    return LGNumberDescription(
        key=key,
        data_key=data_key,
        register_address=address,
        name=name,
        native_min_value=minimum,
        native_max_value=maximum,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.SLIDER,
        write_scale=write_scale,
        signed=signed,
        icon=icon,
    )


_NUMBERS: tuple[LGNumberDescription, ...] = (
    # 20-60 °C, the range the YAML setups offered. The unit applies its own
    # limits on top: a value outside what it accepts is acknowledged and then
    # stored clamped (seen on the DHW setpoint), and the refresh after the
    # write shows what it actually stored.
    _temperature(
        "target_temperature_circuit_1_radiators",
        "holding_target_temperature_circuit_1",
        2,
        "Target Temperature Circuit 1 (Radiators)",
        20,
        60,
        "mdi:radiator",
    ),
    _temperature(
        "target_temperature_circuit_2_underfloor",
        "holding_target_temperature_circuit_2",
        5,
        "Target Temperature Circuit 2 (Underfloor)",
        20,
        40,
        "mdi:floor-plan",
    ),
    # 65 °C is the device maximum, raised from 60 in the installer menu on
    # 2026-09-01 and verified over Modbus (a written 62 held over several
    # polls).
    #
    # CAREFUL WHEN DEBUGGING: the same day, writes seemed to fail at a 60 °C
    # limit - first 62, then 60, finally even the DHW coil. In fact the unit
    # was silently discarding EVERY write at that time, registers and coils
    # alike: Home Assistant wrote, and the next poll 10 s later returned the
    # old value. Restarting the heat pump resolved it. If a value limit seems
    # to be in the way, first check that the unit accepts writes at all; a
    # coil test is the quickest proof.
    _temperature(
        "dhw_target_temperature",
        "holding_dhw_target_temperature",
        8,
        "DHW Target Temperature",
        35,
        65,
        "mdi:water-boiler",
    ),
    _temperature(
        "setpoint_shift_circuit_1",
        "holding_setpoint_shift_circuit_1",
        4,
        "Setpoint Shift Circuit 1",
        -5,
        5,
        "mdi:thermometer-auto",
        write_scale=1.0,
        signed=True,
    ),
    _temperature(
        "setpoint_shift_circuit_2",
        "holding_setpoint_shift_circuit_2",
        7,
        "Setpoint Shift Circuit 2",
        -5,
        5,
        "mdi:thermometer-auto",
        write_scale=1.0,
        signed=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = [
        LGNumber(coordinator, entry, description) for description in _NUMBERS
    ]
    if entry.options.get(CONF_MODULATION_LIMIT, False):
        entities.append(LGMaxCompressorModulationNumber(coordinator, entry))
    else:
        remove_entities(hass, entry, "number", (limits.KEY_MAX_COMPRESSOR_MODULATION,))
    if entry.options.get(CONF_POWER_LIMIT, False):
        entities.append(LGMaxElectricalPowerNumber(coordinator, entry))
    else:
        remove_entities(hass, entry, "number", (power_limit.KEY_MAX_ELECTRICAL_POWER,))
    async_add_entities(entities)


class LGNumber(LGEntity, NumberEntity):
    """A number entity backed by a writable Modbus holding register."""

    entity_description: LGNumberDescription

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGNumberDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self._data(self.entity_description.data_key)

    async def async_set_native_value(self, value: float) -> None:
        description = self.entity_description
        raw = int(round(value * description.write_scale))
        if description.signed and raw < 0:
            raw += 65536
        raw = max(0, min(65535, raw))
        await self.coordinator.async_write_register(description.register_address, raw)
        await self.coordinator.async_request_refresh()


class LGMaxCompressorModulationNumber(LGEntity, NumberEntity):
    """Max compressor modulation, holding register 23 (see limits.py).

    Only created when the option is on. The register holds 40-100 for a limit
    in force and 0 for "not used"; 0 has no place on the slider, so it is shown
    as unknown, with the raw value as an attribute. Writes go through the
    coordinator, which accepts register 23 only while the option is on, and are
    clamped to 40-100 first. The coordinator is refreshed after every write,
    so the slider shows what the unit actually stored, not what was sent.
    """

    _attr_name = "Max Compressor Modulation"
    _attr_icon = "mdi:engine-outline"
    _attr_native_min_value = limits.MODULATION_LIMIT_MIN
    _attr_native_max_value = limits.MODULATION_LIMIT_MAX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, limits.KEY_MAX_COMPRESSOR_MODULATION)

    @property
    def available(self) -> bool:
        # Unavailable until the unit has answered on holding 23 in the current
        # data, e.g. while the read is paused after misses.
        return (
            super().available
            and self._data(limits.DATA_KEY_MAX_COMPRESSOR_MODULATION) is not None
        )

    @property
    def native_value(self) -> float | None:
        return limits.decode(self._data(limits.DATA_KEY_MAX_COMPRESSOR_MODULATION))

    @property
    def extra_state_attributes(self) -> dict[str, int | bool | None]:
        raw = self._data(limits.DATA_KEY_MAX_COMPRESSOR_MODULATION)
        return {
            "modbus_register": 40001 + limits.MODULATION_LIMIT_REGISTER,
            "register_value": raw,
            "limit_active": None if raw is None else raw != 0,
        }

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_register(
            limits.MODULATION_LIMIT_REGISTER, limits.encode(value)
        )
        await self.coordinator.async_request_refresh()


class LGMaxElectricalPowerNumber(LGEntity, NumberEntity):
    """Power limit value, holding register 24 (see power_limit.py).

    Only created with the power limit option. The limit applies only while
    the *Power Limit* switch (coil 6) is on. The register holds tenths of a
    kW; 0 is below the manual's range and shown as unknown, with the raw value
    as an attribute. Writes go through the coordinator, which accepts register
    24 only while the option is on, and are clamped to 0.1-25.0 kW first. The
    coordinator is refreshed after every write, so the slider shows what the
    unit actually stored.
    """

    _attr_name = "Max Electrical Power"
    _attr_icon = "mdi:flash"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_min_value = power_limit.POWER_LIMIT_MIN_KW
    _attr_native_max_value = power_limit.POWER_LIMIT_MAX_KW
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: LGThermaVCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, power_limit.KEY_MAX_ELECTRICAL_POWER)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._data(power_limit.DATA_KEY_MAX_ELECTRICAL_POWER) is not None
        )

    @property
    def native_value(self) -> float | None:
        return power_limit.decode_kw(
            self._data(power_limit.DATA_KEY_MAX_ELECTRICAL_POWER)
        )

    @property
    def extra_state_attributes(self) -> dict[str, int | bool | None]:
        active = self._data(power_limit.DATA_KEY_POWER_LIMIT)
        return {
            "modbus_register": 40001 + power_limit.POWER_LIMIT_REGISTER,
            "register_value": self._data(power_limit.DATA_KEY_MAX_ELECTRICAL_POWER),
            "limit_active": None if active is None else bool(active),
        }

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_register(
            power_limit.POWER_LIMIT_REGISTER, power_limit.encode_kw(value)
        )
        await self.coordinator.async_request_refresh()
