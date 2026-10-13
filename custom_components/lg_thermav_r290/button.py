"""Button platform for LG ThermaV R290 — momentary trigger coils.

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

from .const import DOMAIN
from .coordinator import LGThermaVCoordinator
from .entity import LGEntity


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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        LGButton(coordinator, entry, description) for description in _BUTTONS
    )


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
