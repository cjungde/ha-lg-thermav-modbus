"""Config flow for the LG ThermaV R290 integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from modbus_connection.exceptions import ModbusError, ModbusExceptionError
import voluptuous as vol

from .connection import params_from_entry_data
from .const import (
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_EMERGENCY_OPERATION,
    CONF_ENERGY_REGISTERS,
    CONF_EXPERIMENTAL,
    CONF_MODULATION_LIMIT,
    CONF_PARITY,
    CONF_POWER_LIMIT,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_PORT,
    CONF_SLAVE_ID,
    CONF_STOPBITS,
    CONNECTION_RTU,
    CONNECTION_TCP,
    CONNECTION_TCP_RTU,
    DEFAULT_BAUDRATE,
    DEFAULT_PARITY,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE_ID,
    DEFAULT_STOPBITS,
    DOMAIN,
)
from .detect import CONF_DETECTED, detect, placeholders, suggested
from .migration import UNIQUE_ID_MINOR_VERSION

_LOGGER = logging.getLogger(__name__)

_SLAVE_ID_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=247, step=1, mode=NumberSelectorMode.BOX)
)

_SCHEMA_CONNECTION_TYPE = vol.Schema(
    {
        vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TCP): vol.In(
            [CONNECTION_TCP, CONNECTION_TCP_RTU, CONNECTION_RTU]
        )
    }
)


def _schema_tcp(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("host", default=defaults.get("host", "")): str,
            vol.Required("port", default=defaults.get("port", DEFAULT_PORT)): vol.All(
                int, vol.Range(min=1, max=65535)
            ),
            vol.Required(
                CONF_SLAVE_ID, default=defaults.get(CONF_SLAVE_ID, DEFAULT_SLAVE_ID)
            ): _SLAVE_ID_SELECTOR,
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(int, vol.Range(min=5, max=3600)),
        }
    )


def _schema_rtu(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_SERIAL_PORT,
                default=defaults.get(CONF_SERIAL_PORT, "/dev/ttyUSB0"),
            ): str,
            vol.Required(
                CONF_BAUDRATE, default=defaults.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
            ): vol.In([1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]),
            vol.Required(
                CONF_PARITY, default=defaults.get(CONF_PARITY, DEFAULT_PARITY)
            ): vol.In(["N", "E", "O"]),
            vol.Required(
                CONF_STOPBITS, default=defaults.get(CONF_STOPBITS, DEFAULT_STOPBITS)
            ): vol.In([1, 2]),
            vol.Required(
                CONF_SLAVE_ID, default=defaults.get(CONF_SLAVE_ID, DEFAULT_SLAVE_ID)
            ): _SLAVE_ID_SELECTOR,
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(int, vol.Range(min=5, max=3600)),
        }
    )


async def _test_connection(hass: HomeAssistant, data: dict) -> str | None:
    """Try to read one input register. Returns an error key or None.

    The unit is borrowed for the length of the check. If the entry being
    created shares its endpoint with one that already exists, the borrow lands
    on that connection and the probe queues behind its traffic instead of
    opening a competing socket; otherwise a connection is opened here and
    closed again on the way out.
    """
    try:
        async with async_get_temporary_unit(
            hass,
            params_from_entry_data(data),
            int(data[CONF_SLAVE_ID]),
        ) as unit:
            await unit.read_input_registers(0, 1)
    except HomeAssistantError as exc:
        # The endpoint is already held with link settings that cannot be
        # reconciled with these — a different framing on the same socket. The
        # form can only show a fixed sentence, and which settings collided is
        # exactly what makes this fixable, so it goes to the log.
        _LOGGER.error("Cannot take a unit on this device: %s", exc)
        return "link_settings_conflict"
    except ModbusExceptionError:
        # Something answered but refused the request, which for register 0 of
        # a ThermaV means we are talking to the wrong unit.
        return "invalid_slave_id"
    except ModbusError:
        return "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error testing LG ThermaV connection")
        return "unknown"
    return None


async def _detect(hass: HomeAssistant, data: dict) -> dict[str, bool]:
    """Which optional register groups the unit answers on (see detect.py).

    Borrows a unit like _test_connection, so on a connection that is already
    held (the entry's own, in the options) the checks queue behind its
    traffic. Never raises: a check that cannot run reports nothing, and the
    form then simply suggests nothing.
    """
    try:
        async with async_get_temporary_unit(
            hass,
            params_from_entry_data(data),
            int(data[CONF_SLAVE_ID]),
        ) as unit:
            return await detect(unit)
    except Exception:
        _LOGGER.exception("Checking the optional registers failed")
        return {}


# CONF_DETECT_AGAIN is a one-shot checkbox in the options, never stored.
CONF_DETECT_AGAIN = "detect_again"
# The optional register groups, in the order the forms show them.
_OPTION_GROUPS = (
    CONF_ENERGY_REGISTERS,
    CONF_MODULATION_LIMIT,
    CONF_POWER_LIMIT,
    CONF_EMERGENCY_OPERATION,
    CONF_EXPERIMENTAL,
)


def _option_group_fields(defaults: dict[str, Any]) -> dict:
    return {
        vol.Required(key, default=bool(defaults.get(key, False))): bool
        for key in _OPTION_GROUPS
    }


class LGThermaVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow for LG ThermaV R290."""

    VERSION = 1
    # Minor versions carry the unique id renames (migration.MIGRATION_STEPS):
    # 2: unique ids follow docs/naming.md; 3: coil 0 switch is heating_cooling;
    # 4: holding 40004/40007 sensors are target_room_air_temperature_circuit_*.
    MINOR_VERSION = UNIQUE_ID_MINOR_VERSION
    _connection_type: str = CONNECTION_TCP
    _reconfigure_entry: config_entries.ConfigEntry | None = None
    # A new entry, between the connection test and the options step.
    _data: dict[str, Any]
    _title: str
    _detect_task: asyncio.Task | None = None
    _detected: dict[str, bool] | None = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            if self._connection_type in (CONNECTION_TCP, CONNECTION_TCP_RTU):
                return await self.async_step_tcp()
            return await self.async_step_rtu()

        return self.async_show_form(step_id="user", data_schema=_SCHEMA_CONNECTION_TYPE)

    async def async_step_tcp(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        defaults = self._reconfigure_entry.data if self._reconfigure_entry else {}
        if user_input is not None:
            data = {CONF_CONNECTION_TYPE: self._connection_type, **user_input}
            error = await _test_connection(self.hass, data)
            if error is None:
                if self._reconfigure_entry:
                    return self.async_update_reload_and_abort(
                        self._reconfigure_entry,
                        title=f"LG ThermaV {data['host']}",
                        data=data,
                    )
                await self.async_set_unique_id(
                    f"{data['host']}:{data['port']}:{data[CONF_SLAVE_ID]}"
                )
                self._abort_if_unique_id_configured()
                self._data = data
                self._title = f"LG ThermaV {data['host']}"
                return await self.async_step_detect()
            errors["base"] = error

        return self.async_show_form(
            step_id="tcp",
            data_schema=_schema_tcp(user_input or defaults),
            errors=errors,
        )

    async def async_step_rtu(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        defaults = self._reconfigure_entry.data if self._reconfigure_entry else {}
        if user_input is not None:
            data = {CONF_CONNECTION_TYPE: CONNECTION_RTU, **user_input}
            error = await _test_connection(self.hass, data)
            if error is None:
                if self._reconfigure_entry:
                    return self.async_update_reload_and_abort(
                        self._reconfigure_entry,
                        title=f"LG ThermaV {data[CONF_SERIAL_PORT]}",
                        data=data,
                    )
                await self.async_set_unique_id(
                    f"{data[CONF_SERIAL_PORT]}:{data[CONF_SLAVE_ID]}"
                )
                self._abort_if_unique_id_configured()
                self._data = data
                self._title = f"LG ThermaV {data[CONF_SERIAL_PORT]}"
                return await self.async_step_detect()
            errors["base"] = error

        return self.async_show_form(
            step_id="rtu",
            data_schema=_schema_rtu(user_input or defaults),
            errors=errors,
        )

    async def async_step_detect(self, user_input=None) -> FlowResult:
        """Check which optional registers the new unit answers on.

        Shown as progress: on a unit that lacks a group, each missing one
        waits for a request timeout.
        """
        if self._detect_task is None:
            self._detect_task = self.hass.async_create_task(
                _detect(self.hass, self._data)
            )
        if not self._detect_task.done():
            return self.async_show_progress(
                step_id="detect",
                progress_action="detect",
                progress_task=self._detect_task,
            )
        self._detected = self._detect_task.result()
        return self.async_show_progress_done(next_step_id="features")

    async def async_step_features(self, user_input=None) -> FlowResult:
        """The optional register groups, ticked where the unit answered."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._title,
                data=self._data,
                options={**user_input, CONF_DETECTED: self._detected},
            )
        return self.async_show_form(
            step_id="features",
            data_schema=vol.Schema(_option_group_fields(suggested(self._detected, {}))),
            description_placeholders=placeholders(self._detected),
        )

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
        # Known limitation: the entry being reconfigured still holds its unit
        # while this flow runs. Changing the framing (tcp <-> tcp_rtu) without
        # changing host or port therefore collides with the entry's own hold and
        # is reported as "link_settings_conflict" -- technically true, but it
        # names the user's own entry as the other party. Removing and re-adding
        # the entry is the way through. Fixing it properly means releasing the
        # hold before probing, which needs care around a failed probe leaving
        # the entry unloaded.
        self._reconfigure_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        current_type = self._reconfigure_entry.data.get(
            CONF_CONNECTION_TYPE, CONNECTION_TCP
        )

        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            if self._connection_type in (CONNECTION_TCP, CONNECTION_TCP_RTU):
                return await self.async_step_tcp()
            return await self.async_step_rtu()

        schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_TYPE, default=current_type): vol.In(
                    [CONNECTION_TCP, CONNECTION_TCP_RTU, CONNECTION_RTU]
                )
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LGThermaVOptionsFlow(config_entry)


class LGThermaVOptionsFlow(config_entries.OptionsFlow):
    """Allow changing the scan interval and the optional register groups.

    Neither needs the connection details entered again. The result of the
    last register check is shown next to the groups; ticking "check again"
    runs it anew and then shows the form once more.
    """

    def __init__(self, entry) -> None:
        self._entry = entry
        self._detected: dict[str, bool] | None = entry.options.get(CONF_DETECTED)
        self._detect_task: asyncio.Task | None = None
        # The form's values while a check runs, to show them again after it.
        self._pending: dict[str, Any] | None = None

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            values = dict(user_input)
            if values.pop(CONF_DETECT_AGAIN, False):
                self._pending = values
                self._detect_task = None
                return await self.async_step_detect()
            return self.async_create_entry(
                title="", data={**values, CONF_DETECTED: self._detected}
            )

        if self._pending is not None:
            defaults = suggested(self._detected, self._pending)
        else:
            defaults = {
                CONF_SCAN_INTERVAL: self._entry.options.get(
                    CONF_SCAN_INTERVAL,
                    self._entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ),
                **{key: self._entry.options.get(key, False) for key in _OPTION_GROUPS},
            }
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=defaults[CONF_SCAN_INTERVAL]
                ): vol.All(int, vol.Range(min=5, max=3600)),
                **_option_group_fields(defaults),
                vol.Required(CONF_DETECT_AGAIN, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders=placeholders(self._detected),
        )

    async def async_step_detect(self, user_input=None) -> FlowResult:
        """Check the optional registers again, on the entry's own connection."""
        if self._detect_task is None:
            self._detect_task = self.hass.async_create_task(
                _detect(self.hass, dict(self._entry.data))
            )
        if not self._detect_task.done():
            return self.async_show_progress(
                step_id="detect",
                progress_action="detect",
                progress_task=self._detect_task,
            )
        self._detected = self._detect_task.result()
        return self.async_show_progress_done(next_step_id="init")
