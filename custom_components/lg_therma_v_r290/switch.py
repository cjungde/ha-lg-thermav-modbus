"""Switch platform for LG Therma V R290 — state coil registers.

Only coils that hold a state belong here. The momentary trigger coils
("0: hold status / 1: start operation") are buttons instead — see button.py.

Keys follow docs/naming.md: the entity key is the name as an entity id slug,
the data key is ``coil_<key>``.
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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import power_limit
from .const import CONF_POWER_LIMIT, DOMAIN
from .coordinator import LGThermaVCoordinator
from .entity import LGEntity, english_entity_ids, remove_entities


@dataclass(frozen=True, kw_only=True)
class LGSwitchDescription(SwitchEntityDescription):
    data_key: str
    coil_address: int


def _coil(key: str, address: int, name: str, icon: str) -> LGSwitchDescription:
    return LGSwitchDescription(
        key=key,
        data_key=f"coil_{key}",
        coil_address=address,
        name=name,
        device_class=SwitchDeviceClass.SWITCH,
        icon=icon,
    )


_SWITCHES: tuple[LGSwitchDescription, ...] = (
    # Coil 0 (00001): "Aktivieren / Deaktivieren (Heizung / Kühlung)" -- space
    # heating/cooling only; DHW is coil 1.
    _coil("heating_cooling", 0, "Heating/Cooling", "mdi:heat-pump"),
    _coil("dhw", 1, "DHW", "mdi:water-boiler"),
    _coil("silent_mode", 2, "Silent Mode", "mdi:volume-off"),
    _coil("emergency_stop", 4, "Emergency Stop", "mdi:stop-circle"),
)

# Coil 6 (00007, "Wirkleistungsbegrenzung": 0 not used / 1 limit the power
# per 40025). Only created with the power limit option; the coordinator reads
# it on its own and accepts a write to it only then (see power_limit.py).
POWER_LIMIT_SWITCH = LGSwitchDescription(
    key=power_limit.KEY_POWER_LIMIT,
    data_key=power_limit.DATA_KEY_POWER_LIMIT,
    coil_address=power_limit.POWER_LIMIT_COIL,
    name="Power Limit",
    device_class=SwitchDeviceClass.SWITCH,
    icon="mdi:flash-alert",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [
        LGSwitch(coordinator, entry, description) for description in _SWITCHES
    ]
    if entry.options.get(CONF_POWER_LIMIT, False):
        entities.append(LGOptionalSwitch(coordinator, entry, POWER_LIMIT_SWITCH))
    else:
        remove_entities(hass, entry, "switch", (POWER_LIMIT_SWITCH.key,))
    async_add_entities(english_entity_ids("switch", entities))


class LGSwitch(LGEntity, SwitchEntity):
    """A switch that controls a Modbus coil register."""

    entity_description: LGSwitchDescription

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGSwitchDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        value = self._data(self.entity_description.data_key)
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_coil(
            self.entity_description.coil_address, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_coil(
            self.entity_description.coil_address, False
        )
        await self.coordinator.async_request_refresh()


class LGOptionalSwitch(LGSwitch):
    """A switch on a coil that not every unit serves.

    Unavailable, rather than off, until the unit has answered on its coil in
    the current data, e.g. while the read is paused after misses.
    """

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._data(self.entity_description.data_key) is not None
        )
