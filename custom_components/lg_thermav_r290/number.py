"""Number platform for LG ThermaV R290 — writable holding registers."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LGThermaVCoordinator


@dataclass(frozen=True, kw_only=True)
class LGNumberDescription(NumberEntityDescription):
    data_key: str = ""
    register_address: int = 0
    # Factor applied to raw register value when reading (raw × read_scale = display)
    read_scale: float = 1.0
    # Factor applied to display value when writing (display × write_scale = raw)
    write_scale: float = 1.0
    signed: bool = False


_NUMBERS: tuple[LGNumberDescription, ...] = (
    LGNumberDescription(
        key="target_temp_circuit1",
        data_key="target_temp_circuit1",
        register_address=2,
        name="Target Temperature Circuit 1 (Radiators)",
        native_min_value=30,
        native_max_value=50,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.SLIDER,
        read_scale=0.1,
        write_scale=10.0,
        icon="mdi:radiator",
    ),
    LGNumberDescription(
        key="target_temp_circuit2",
        data_key="target_temp_circuit2",
        register_address=5,
        name="Target Temperature Circuit 2 (Underfloor)",
        native_min_value=20,
        native_max_value=40,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.SLIDER,
        read_scale=0.1,
        write_scale=10.0,
        icon="mdi:floor-plan",
    ),
    LGNumberDescription(
        key="dhw_target_temp",
        data_key="dhw_target_temp",
        register_address=8,
        name="DHW Target Temperature",
        native_min_value=35,
        # 65 = Geraetemaximum, im Installateursmenue am 01.09.2026 von 60
        # angehoben und per Modbus verifiziert (Schreibwert 62 haelt ueber
        # mehrere Poll-Zyklen).
        #
        # VORSICHT BEI DER FEHLERSUCHE: Am selben Tag schienen Schreibvorgaenge
        # an einer 60-C-Grenze zu scheitern - erst 62, dann auch 60, zuletzt
        # sogar der DHW-Coil. Tatsaechlich verwarf die WP zu dem Zeitpunkt
        # SAEMTLICHE Schreibvorgaenge, Register wie Coils, ohne Fehlermeldung:
        # HA schrieb, der naechste Poll 10 s spaeter lieferte den alten Wert
        # zurueck. Ein Neustart der Waermepumpe hat das aufgeloest. Wer hier
        # eine Wertgrenze vermutet, pruefe also zuerst, ob das Geraet
        # ueberhaupt noch Schreibvorgaenge annimmt - ein Coil-Test ist dafuer
        # der schnellste Nachweis.
        native_max_value=65,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.SLIDER,
        read_scale=0.1,
        write_scale=10.0,
        icon="mdi:water-boiler",
    ),
    LGNumberDescription(
        key="shift_value_circuit1",
        data_key="shift_value_circuit1",
        register_address=4,
        name="Setpoint Shift Circuit 1",
        native_min_value=-5,
        native_max_value=5,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.SLIDER,
        read_scale=1.0,
        write_scale=1.0,
        signed=True,
        icon="mdi:thermometer-auto",
    ),
    LGNumberDescription(
        key="shift_value_circuit2",
        data_key="shift_value_circuit2",
        register_address=7,
        name="Setpoint Shift Circuit 2",
        native_min_value=-5,
        native_max_value=5,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.SLIDER,
        read_scale=1.0,
        write_scale=1.0,
        signed=True,
        icon="mdi:thermometer-auto",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(LGNumber(coordinator, entry, desc) for desc in _NUMBERS)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="LG ThermaV R290",
        manufacturer="LG",
        model="ThermaV R290",
    )


class LGNumber(CoordinatorEntity[LGThermaVCoordinator], NumberEntity):
    """A number entity backed by a writable Modbus holding register."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._data_key = description.data_key
        self._register_address = description.register_address
        self._write_scale = description.write_scale
        self._signed = description.signed
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)

    async def async_set_native_value(self, value: float) -> None:
        raw = int(round(value * self._write_scale))
        if self._signed and raw < 0:
            raw = raw + 65536
        raw = max(0, min(65535, raw))
        await self.coordinator.async_write_register(self._register_address, raw)
        await self.coordinator.async_request_refresh()
