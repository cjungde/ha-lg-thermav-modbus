"""Button platform for LG Therma V R290 — momentary trigger coils.

Some coils are not state switches but one-shot triggers. The manual describes
them as "0: hold status / 1: start operation": writing 1 starts the operation
and the unit clears the coil again by itself. Reading such a coil back is
therefore never a confirmation — the operation's status lives in a separate
discrete input, exposed as its own binary sensor.

Keys follow docs/naming.md: the entity key is the name as an entity id slug.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_EMERGENCY_OPERATION, DOMAIN
from .coordinator import LGThermaVCoordinator
from .entity import LGEntity, remove_entities


@dataclass(frozen=True, kw_only=True)
class LGButtonDescription(ButtonEntityDescription):
    coil_address: int


_BUTTONS: tuple[LGButtonDescription, ...] = (
    # Coil 3 (00004). Status: binary_sensor DHW Disinfection (discrete 10007).
    LGButtonDescription(
        key="start_disinfection",
        coil_address=3,
        name="Start Disinfection",
        icon="mdi:shield-bug",
    ),
)

# Coil 5 (00006, "Auslöser Notaus-Betrieb": 0 hold status / 1 start).
# Starts emergency operation, which typically heats with the backup heater
# and draws far more power than the heat pump. Only created with its option,
# off by default; the coordinator accepts a write to coil 5 only then.
# Status: binary_sensors Emergency Heating/Cooling Available (10015) and
# Emergency DHW Available (10016) show whether emergency operation is possible.
EMERGENCY_OPERATION_BUTTON = LGButtonDescription(
    key="start_emergency_operation",
    coil_address=5,
    name="Start Emergency Operation",
    icon="mdi:alert-octagon",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [LGButton(coordinator, entry, d) for d in _BUTTONS]
    if entry.options.get(CONF_EMERGENCY_OPERATION, False):
        entities.append(LGButton(coordinator, entry, EMERGENCY_OPERATION_BUTTON))
    else:
        remove_entities(hass, entry, "button", (EMERGENCY_OPERATION_BUTTON.key,))
    async_add_entities(entities)


class LGButton(LGEntity, ButtonEntity):
    """A button that pulses a momentary Modbus trigger coil."""

    entity_description: LGButtonDescription

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGButtonDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.coordinator.async_write_coil(
            self.entity_description.coil_address, True
        )
        await self.coordinator.async_request_refresh()
