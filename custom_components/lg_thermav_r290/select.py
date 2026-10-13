"""Select platform for LG ThermaV R290 — operation mode and control method.

Keys follow docs/naming.md: the entity key is the name as an entity id slug,
the data key is ``holding_<key>``.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONTROL_METHOD_FROM_VALUE,
    CONTROL_METHOD_OPTIONS,
    CONTROL_METHOD_TO_VALUE,
    DOMAIN,
    OPERATION_MODE_FROM_VALUE,
    OPERATION_MODE_OPTIONS,
    OPERATION_MODE_TO_VALUE,
)
from .coordinator import LGThermaVCoordinator
from .entity import LGEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class LGSelectDescription(SelectEntityDescription):
    data_key: str
    register_address: int
    to_value: dict[str, int]
    from_value: dict[int, str]


_SELECTS: tuple[LGSelectDescription, ...] = (
    LGSelectDescription(
        key="operation_mode",
        data_key="holding_operation_mode",
        register_address=0,
        name="Operation Mode",
        options=OPERATION_MODE_OPTIONS,
        to_value=OPERATION_MODE_TO_VALUE,
        from_value=OPERATION_MODE_FROM_VALUE,
        icon="mdi:heat-pump",
    ),
    LGSelectDescription(
        key="control_method",
        data_key="holding_control_method",
        register_address=1,
        name="Control Method",
        options=CONTROL_METHOD_OPTIONS,
        to_value=CONTROL_METHOD_TO_VALUE,
        from_value=CONTROL_METHOD_FROM_VALUE,
        icon="mdi:tune",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LGThermaVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        LGSelect(coordinator, entry, description) for description in _SELECTS
    )


class LGSelect(LGEntity, SelectEntity):
    """A select entity backed by a writable Modbus holding register."""

    entity_description: LGSelectDescription

    def __init__(
        self,
        coordinator: LGThermaVCoordinator,
        entry: ConfigEntry,
        description: LGSelectDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_options = description.options

    @property
    def current_option(self) -> str | None:
        raw = self._data(self.entity_description.data_key)
        if raw is None:
            return None
        return self.entity_description.from_value.get(raw)

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        # The register value behind the option, as a number, so it reaches a
        # numeric time series database (see LGLabelSensor in sensor.py).
        return {"register_value": self._data(self.entity_description.data_key)}

    async def async_select_option(self, option: str) -> None:
        value = self.entity_description.to_value.get(option)
        if value is None:
            _LOGGER.warning("Unknown option '%s' for %s", option, self.entity_id)
            return
        await self.coordinator.async_write_register(
            self.entity_description.register_address, value
        )
        await self.coordinator.async_request_refresh()
