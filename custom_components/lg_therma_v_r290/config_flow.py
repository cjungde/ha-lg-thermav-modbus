"""Config flow for the LG Therma V R290 integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify
from modbus_connection.exceptions import ModbusError, ModbusExceptionError
import voluptuous as vol

from .connection import params_from_entry_data
from .const import (
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_EXTERNAL_ENERGY,
    CONF_EXTERNAL_POWER,
    CONF_PARITY,
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
from .detect import (
    CONF_DETECTED,
    CONF_DETECTED_AT,
    GROUPS,
    detect,
    placeholders,
    status_placeholders,
    suggested,
)
from .entity import DEVICE_NAME
from .migration import UNIQUE_ID_MINOR_VERSION
from .register_status import since_start_placeholders
from .yaml_takeover import UNIT_SPELLING, Found, plan

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


#: How long the form waits for the connection test. The link's own timeout is no help
#: here: the borrowed unit may land on an EXISTING connection whose timeout the
#: coordinator has already raised to 20 s (coordinator._REQUEST_TIMEOUT), and
#: the probe would then inherit that wait. A form has to answer sooner than
#: that, so the wait is bounded here instead of relying on the transport.
_PROBE_TIMEOUT = 10  # seconds


def _device_key(data: dict) -> str:
    """The entry's unique id: address (or serial port) and slave id.

    Kept exactly as setup has always written it -- the form hands the slave
    id over as a float, so existing entries carry e.g. "…:1.0" -- because
    duplicate detection compares it with the ids already in place. TCP and
    TCP-RTU on one host share it: two framings for the same unit.
    """
    if data[CONF_CONNECTION_TYPE] == CONNECTION_RTU:
        return f"{data[CONF_SERIAL_PORT]}:{data[CONF_SLAVE_ID]}"
    return f"{data['host']}:{data['port']}:{data[CONF_SLAVE_ID]}"


def _same_unit(old: dict, new: dict) -> bool:
    """Whether two sets of link settings point at the same unit.

    Compared as values, not as unique id strings: a slave id stored as 1 and
    one typed as 1.0 are the same unit.
    """

    def where(data: dict) -> tuple:
        if data[CONF_CONNECTION_TYPE] == CONNECTION_RTU:
            return ("serial", data[CONF_SERIAL_PORT], int(data[CONF_SLAVE_ID]))
        return ("tcp", data["host"], int(data["port"]), int(data[CONF_SLAVE_ID]))

    return where(old) == where(new)


async def _test_connection(hass: HomeAssistant, data: dict) -> str | None:
    """Try to read one input register. Returns an error key or None.

    The unit is borrowed for the length of the check. If the entry being
    created shares its endpoint with one that already exists, the borrow lands
    on that connection and the probe queues behind its traffic instead of
    opening a competing socket; otherwise a connection is opened here and
    closed again on the way out.
    """
    try:
        async with (
            asyncio.timeout(_PROBE_TIMEOUT),
            async_get_temporary_unit(
                hass,
                params_from_entry_data(data),
                int(data[CONF_SLAVE_ID]),
            ) as unit,
        ):
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
        # a Therma V means we are talking to the wrong unit.
        return "invalid_slave_id"
    except (ModbusError, TimeoutError):
        # A queued probe that ran out of time is indistinguishable, from the
        # form's side, from a device that never answered.
        return "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error testing LG Therma V connection")
        return "unknown"
    return None


async def _detect(hass: HomeAssistant, data: dict) -> dict[str, bool] | None:
    """Which optional register groups the unit answers on (see detect.py).

    Borrows a unit like _test_connection, so on a connection that is already
    held (the entry's own, in the options) the checks queue behind its
    traffic. Never raises: a check that cannot run, or whose link was not
    shown to be up, returns None; nothing is recorded then, and the form
    says so.
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
        return None


def _option_group_fields(defaults: dict[str, Any]) -> dict:
    """One collapsible section per option, holding its toggle.

    Collapsed, a section shows the option's name; expanded, what the option
    is for (the section's description), its toggle, and the entities it adds
    (the toggle's help text, which Home Assistant renders as Markdown). The
    sections of options that are on open expanded, so the form shows at a
    glance what is on; the others can be expanded to see what they would add.
    """
    fields = {}
    for key in GROUPS:
        on = bool(defaults.get(key, False))
        fields[vol.Required(key)] = section(
            vol.Schema({vol.Required(key, default=on): bool}),
            {"collapsed": not on},
        )
    return fields


# The section with the sensors of the user's own electricity meter.
EXTERNAL_METER_SECTION = "external_meter"
_EXTERNAL_METER_FIELDS = (
    (CONF_EXTERNAL_POWER, SensorDeviceClass.POWER),
    (CONF_EXTERNAL_ENERGY, SensorDeviceClass.ENERGY),
)


def _external_meter_field(current: dict[str, Any]) -> dict:
    """Two optional sensor pickers, expanded while one of them is set."""
    fields = {
        vol.Optional(key, description={"suggested_value": current.get(key)}): (
            EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class=device_class)
            )
        )
        for key, device_class in _EXTERNAL_METER_FIELDS
    }
    is_set = any(current.get(key) for key, _ in _EXTERNAL_METER_FIELDS)
    return {
        vol.Required(EXTERNAL_METER_SECTION): section(
            vol.Schema(fields), {"collapsed": not is_set}
        )
    }


def _flatten_option_groups(user_input: dict[str, Any]) -> dict[str, Any]:
    """The submitted form as plain options: toggles and meter sensors.

    A meter sensor that was cleared is not in the submission and so not in
    the options any more.
    """
    values = dict(user_input)
    for key in GROUPS:
        if isinstance(values.get(key), dict):
            values[key] = bool(values[key].get(key, False))
    meter = values.pop(EXTERNAL_METER_SECTION, None) or {}
    for key, _ in _EXTERNAL_METER_FIELDS:
        if meter.get(key):
            values[key] = meter[key]
    return values


# Markers in the takeover tables; their meaning is in the step's text, so
# the tables work in every language.
_LEFT_MARKERS = {
    "scale": "①",
    "not_a_temperature": "②",
    "unit": "③",
    "text": "④",
    "other_type": "⑤",
    "still_loaded": "⑥",
    "target_taken": "⑦",
}


def _plan_yaml_takeover(hass: HomeAssistant) -> tuple[list[Found], list]:
    """The YAML entities whose history can be taken over, and the others."""
    registry = er.async_get(hass)
    yaml_entries = [
        (e.platform, e.unique_id, e.domain, e.entity_id)
        for e in registry.entities.values()
        if e.config_entry_id is None and e.platform in ("modbus", "template")
    ]
    live = {
        state.entity_id
        for state in hass.states.async_all()
        if not state.attributes.get("restored", False)
    }
    return plan(yaml_entries, live, set(registry.entities.keys()), slugify(DEVICE_NAME))


def _take_over(hass: HomeAssistant, found: list[Found]) -> None:
    """Move each YAML entity's history to the integration's id, then drop it.

    Renaming in the registry makes the recorder move the history and the
    long-term statistics to the new id; removing the registry entry keeps
    them. The integration's entity then registers under that id.
    """
    registry = er.async_get(hass)
    for item in found:
        registry.async_update_entity(
            item.old_entity_id, new_entity_id=item.new_entity_id
        )
        registry.async_remove(item.new_entity_id)
        _LOGGER.info(
            "History of %s continues as %s", item.old_entity_id, item.new_entity_id
        )


def _takeover_table(found: list[Found]) -> str:
    rows = ["| YAML | | |", "|---|---|---|"]
    for item in found:
        note = " ⚠" if item.takeover.note == UNIT_SPELLING else ""
        rows.append(f"| `{item.old_entity_id}` | → | `{item.new_entity_id}`{note} |")
    return "\n".join(rows)


def _left_table(left: list) -> str:
    if not left:
        return "–"
    return "\n".join(
        f"- `{entity_id}` {_LEFT_MARKERS[reason]}" for entity_id, reason in left
    )


class LGThermaVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow for LG Therma V R290."""

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
    # The check ran but proved nothing (the link was not up); the features
    # step says so.
    _check_failed = False

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            if self._connection_type in (CONNECTION_TCP, CONNECTION_TCP_RTU):
                return await self.async_step_tcp()
            return await self.async_step_rtu()

        return self.async_show_form(step_id="user", data_schema=_SCHEMA_CONNECTION_TYPE)

    async def _test(self, data: dict) -> str | None:
        """Test the connection settings; for a reconfigure, around the entry.

        While the entry being reconfigured is loaded, it holds its unit on the
        shared connection. New settings for the same device with different
        link settings (TCP <-> TCP-RTU on one host, another baud rate on one
        serial port) then collide with the entry's own hold and are refused as
        "link_settings_conflict", naming the user's own entry as the other
        party. So on that error the entry is unloaded, releasing its hold, and
        the test is repeated. If the new settings still fail, the entry is set
        up again with its old ones; if they work, the reconfigure reloads it
        with the new ones.
        """
        error = await _test_connection(self.hass, data)
        entry = self._reconfigure_entry
        if (
            error != "link_settings_conflict"
            or entry is None
            or entry.state is not config_entries.ConfigEntryState.LOADED
        ):
            return error
        await self.hass.config_entries.async_unload(entry.entry_id)
        error = "unknown"
        try:
            error = await _test_connection(self.hass, data)
        finally:
            if error is not None:
                await self.hass.config_entries.async_setup(entry.entry_id)
        return error

    def _finish_reconfigure(self, data: dict, title: str) -> FlowResult:
        """Save new link settings and reload the entry.

        When they point at a different unit -- another address, port, serial
        port or slave id (_same_unit) -- the stored result of the optional
        register check belongs to the old unit and is cleared, and the unique
        id follows the new address. A change of framing on the same address
        (TCP <-> TCP-RTU) keeps both. From the address alone a move of the
        same unit to another path (USB adapter -> gateway) cannot be told
        apart from another unit, so it clears the result too: the cheap
        mistake, since the check is one click under Configure.
        """
        entry = self._reconfigure_entry
        if _same_unit(dict(entry.data), data):
            return self.async_update_reload_and_abort(entry, title=title, data=data)
        new_key = _device_key(data)
        for other in self.hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != entry.entry_id and (
                other.unique_id == new_key or _same_unit(dict(other.data), data)
            ):
                return self.async_abort(reason="already_configured")
        return self.async_update_reload_and_abort(
            entry,
            unique_id=new_key,
            title=title,
            data=data,
            options={**entry.options, CONF_DETECTED: None, CONF_DETECTED_AT: None},
            reason="reconfigure_successful_check_cleared",
        )

    async def async_step_tcp(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        defaults = self._reconfigure_entry.data if self._reconfigure_entry else {}
        if user_input is not None:
            data = {CONF_CONNECTION_TYPE: self._connection_type, **user_input}
            error = await self._test(data)
            if error is None:
                if self._reconfigure_entry:
                    return self._finish_reconfigure(data, f"LG Therma V {data['host']}")
                await self.async_set_unique_id(_device_key(data))
                self._abort_if_unique_id_configured()
                self._data = data
                self._title = f"LG Therma V {data['host']}"
                return await self.async_step_check()
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
            error = await self._test(data)
            if error is None:
                if self._reconfigure_entry:
                    return self._finish_reconfigure(
                        data, f"LG Therma V {data[CONF_SERIAL_PORT]}"
                    )
                await self.async_set_unique_id(_device_key(data))
                self._abort_if_unique_id_configured()
                self._data = data
                self._title = f"LG Therma V {data[CONF_SERIAL_PORT]}"
                return await self.async_step_check()
            errors["base"] = error

        return self.async_show_form(
            step_id="rtu",
            data_schema=_schema_rtu(user_input or defaults),
            errors=errors,
        )

    async def async_step_check(self, user_input=None) -> FlowResult:
        """Ask whether to check the optional registers now.

        Which registers a unit serves only changes with its firmware, so the
        check is worth running once, but not something to impose: on a unit
        that serves none of the groups each of them waits for a request
        timeout, and on a shared link that wait holds up everyone else on it.
        Skipped, the options come up unticked and unchecked (–), and the check
        is under Configure whenever it is wanted.
        """
        return self.async_show_menu(
            step_id="check", menu_options=["detect", "features"]
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
        self._check_failed = self._detected is None
        return self.async_show_progress_done(next_step_id="features")

    async def async_step_features(self, user_input=None) -> FlowResult:
        """The optional register groups, ticked where the unit answered."""
        if user_input is not None:
            self._options = {
                **_flatten_option_groups(user_input),
                CONF_DETECTED: self._detected,
                # No time without a result: the status table under Configure
                # then shows the check as never run.
                CONF_DETECTED_AT: (
                    None if self._detected is None else dt_util.utcnow().isoformat()
                ),
            }
            self._takeover, self._left = _plan_yaml_takeover(self.hass)
            if self._takeover:
                return await self.async_step_yaml_takeover()
            return self._create()
        return self.async_show_form(
            step_id="features",
            data_schema=vol.Schema(_option_group_fields(suggested(self._detected, {}))),
            description_placeholders=placeholders(self._detected),
            errors={"base": "check_inconclusive"} if self._check_failed else None,
        )

    async def async_step_yaml_takeover(self, user_input=None) -> FlowResult:
        """Offer to continue the history of the YAML setup (yaml_takeover.py).

        Shown only when orphaned entities of the isarrider YAML package are in
        the registry. Done here, before the entry exists, so the integration's
        entities register under the ids the old history was moved to.
        """
        if user_input is not None:
            if user_input.get("take_over", False):
                _take_over(self.hass, self._takeover)
            return self._create()
        return self.async_show_form(
            step_id="yaml_takeover",
            data_schema=vol.Schema({vol.Required("take_over", default=True): bool}),
            description_placeholders={
                "count": str(len(self._takeover)),
                "takeover_table": _takeover_table(self._takeover),
                "left_table": _left_table(self._left),
            },
        )

    def _create(self) -> FlowResult:
        return self.async_create_entry(
            title=self._title, data=self._data, options=self._options
        )

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
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


def _checked_at(value: str | None) -> str:
    """When the registers were last checked, in local time, or – if never."""
    when = dt_util.parse_datetime(value) if value else None
    if when is None:
        return "–"
    return dt_util.as_local(when).strftime("%Y-%m-%d %H:%M")


class LGThermaVOptionsFlow(config_entries.OptionsFlow):
    """Configure: a menu with a status table, the options, and the check.

    The menu shows per optional group whether it is on and whether the unit
    answered on the last check, so it is visible what could be switched on.
    "Check the optional registers" runs the check (see detect.py) and then
    opens the options with what answered ticked; nothing is switched off.
    """

    def __init__(self, entry) -> None:
        self._entry = entry
        self._detected: dict[str, bool] | None = entry.options.get(CONF_DETECTED)
        self._detected_at: str | None = entry.options.get(CONF_DETECTED_AT)
        self._detect_task: asyncio.Task | None = None
        # Option values to show after a check: the current ones plus what
        # answered.
        self._suggested: dict[str, Any] | None = None
        self._check_failed = False

    def _current(self) -> dict[str, Any]:
        return {
            CONF_SCAN_INTERVAL: self._entry.options.get(
                CONF_SCAN_INTERVAL,
                self._entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ),
            **{key: self._entry.options.get(key, False) for key in GROUPS},
        }

    def _placeholders(self, options: dict[str, Any]) -> dict[str, str]:
        # What the reads did since start, from the running coordinator; None
        # (every row –) while the entry is not loaded.
        coordinator = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        snapshot = None if coordinator is None else coordinator.optional_snapshot()
        return {
            **status_placeholders(self._detected, options),
            **since_start_placeholders(snapshot, GROUPS),
            "checked": _checked_at(self._detected_at),
        }

    async def async_step_init(self, user_input=None) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["options", "detect"],
            description_placeholders=self._placeholders(self._current()),
        )

    async def async_step_options(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **_flatten_option_groups(user_input),
                    CONF_DETECTED: self._detected,
                    CONF_DETECTED_AT: self._detected_at,
                },
            )

        defaults = self._suggested or self._current()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=defaults[CONF_SCAN_INTERVAL]
                ): vol.All(int, vol.Range(min=5, max=3600)),
                **_option_group_fields(defaults),
                **_external_meter_field(dict(self._entry.options)),
            }
        )
        return self.async_show_form(
            step_id="options",
            data_schema=schema,
            description_placeholders=self._placeholders(self._current()),
            errors={"base": "check_inconclusive"} if self._check_failed else None,
        )

    async def async_step_detect(self, user_input=None) -> FlowResult:
        """Check the optional registers, on the entry's own connection."""
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
        result = self._detect_task.result()
        self._detect_task = None
        if result is None:
            # Proved nothing: keep the last result and say so on the form.
            self._check_failed = True
        else:
            self._check_failed = False
            self._detected = result
            self._detected_at = dt_util.utcnow().isoformat()
            self._suggested = suggested(self._detected, self._current())
        return self.async_show_progress_done(next_step_id="options")
