"""DataUpdateCoordinator for the LG ThermaV R290."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.modbus import async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection.exceptions import ModbusError, ModbusExceptionError

from .capabilities import (
    OPTIONAL_REGISTERS,
    CapabilityStore,
    definitions_fingerprint,
    device_key,
    identity_of,
    pending_probes,
)
from .connection import params_from_entry_data
from .const import (
    CONF_EXPERIMENTAL,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    WRITABLE_COILS,
    WRITABLE_HOLDING_REGISTERS,
)
from .experimental import EXPERIMENTAL_BLOCKS, INPUT_FROM_MAIN_READ, register_key

_LOGGER = logging.getLogger(__name__)

#: Per-request timeout floor for this unit. `modbus_connection`'s own default
#: is 10 s, which is not generous on a SHARED connection: requests from every
#: consumer on the endpoint queue behind one lock, so waiting time adds up
#: rather than overlapping. An answer that arrives after the client gave up on
#: it does not vanish — it is read as the reply to the NEXT request and shows
#: up as `Received unexpected response with Transaction ID`, followed by a
#: dropped link. That exact line stood in the log on 04.09.2026, back when two
#: sockets shared the RS485 gateway; sharing the connection removes that cause
#: but not this one.
#:
#: `require_timeout` raises the timeout of the whole LINK to at least this
#: value — it resolves to the maximum over all units on it, so the call is a
#: floor and not an assignment, and setting it here does not shorten anyone
#: else's. Raising it drops the current connection so the new value takes
#: effect at once, which is why this is called once at setup and never again.
#:
#: Needs `modbus-connection` 4.12.3 (Home Assistant 2026.10); the 4.10.0 that
#: the 2026.9 line pins has no such method.
_REQUEST_TIMEOUT = 20.0


def _signed16(value: int) -> int:
    """Convert an unsigned 16-bit register value to a signed integer."""
    return value - 65536 if value >= 32768 else value


class LGThermaVCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the LG ThermaV R290 at a fixed interval and distributes data to entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Take a unit on a shared connection and poll it.

        Asking for the unit performs no I/O, so a heat pump that is powered
        down or behind a dead gateway does not stop the entry setting up. The
        first read opens the link and a dropped link reopens on the next
        request, which is why nothing here reconnects, keeps a client of its
        own, or reloads the entry by hand. The connection carries its own lock,
        so the reads below and the writes further down cannot interleave —
        neither with each other nor with another integration on the same bus.
        That serialization is also why the timeout needs raising; see
        `_REQUEST_TIMEOUT`.
        """
        self.unit = async_get_unit(
            hass,
            entry,
            params_from_entry_data(dict(entry.data)),
            int(entry.data[CONF_SLAVE_ID]),
        )
        self.unit.require_timeout(_REQUEST_TIMEOUT)

        self._experimental = bool(entry.options.get(CONF_EXPERIMENTAL, False))

        #: What this unit served, as far as we know. Empty until the cache is
        #: read and, for anything the cache could not answer for, until the
        #: first successful poll has witnessed a probe. The platforms read it
        #: after `async_config_entry_first_refresh`, which is why detection
        #: happens inside the poll and not in a background task: an entity
        #: that appears only minutes later would miss its own history.
        self.capabilities: dict[str, bool] = {}
        self._capability_store = CapabilityStore(hass, entry.entry_id)
        self._device_key = device_key(
            entry.data.get("host", ""),
            int(entry.data.get("port", 0)),
            int(entry.data[CONF_SLAVE_ID]),
        )
        self._fingerprint = definitions_fingerprint()
        self._capabilities_saved: dict[str, bool] | None = None

        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    # Registers 9997/9998 carry the device's identity, which does not change
    # while the integration is loaded. None means "not asked yet"; the answer
    # is kept even when it is "this firmware does not serve them", so a device
    # without them is not re-asked every poll. Six requests per cycle on a
    # shared RS485 line is enough without one of them re-reading a constant.
    _identity: tuple[int | None, int | None] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            # Read all blocks
            # Register 15 is undefined on this device; split the input read to avoid it.
            inp_lo = await self.unit.read_input_registers(0, 14)  # addresses 0-13
            inp_hi = await self.unit.read_input_registers(16, 9)  # 16-24 (skips 14-15)
            hold_low = await self.unit.read_holding_registers(0, 10)  # addresses 0-9
            coils = await self.unit.read_coils(0, 6)  # addresses 0-5
            di = await self.unit.read_discrete_inputs(0, 17)  # addresses 0-16

            # Optional product info registers — not available on all firmware
            # versions. Only an exception response means "this device does not
            # serve that address"; a timeout or a dropped link has to keep
            # failing the update rather than being written off as absent.
            if self._identity is None:
                try:
                    registers = await self.unit.read_input_registers(9997, 2)
                except ModbusExceptionError:
                    self._identity = (None, None)
                else:
                    self._identity = (registers[0], registers[1])
            device_group, product_info = self._identity

        except ModbusError as exc:
            raise UpdateFailed(f"Modbus communication error: {exc}") from exc

        # Everything above answered, so the link is demonstrably alive. Only
        # now may a silent address be read as "this unit does not serve it".
        await self._async_detect_capabilities()
        optional = await self._async_read_optional()

        experimental = await self._async_read_experimental(inp_hi)

        return {
            **experimental,
            **optional,
            # Input registers (raw × scale)
            # inp_lo[n] = register n  (0-13)
            # inp_hi[n] = register 16+n (16-24)
            "error_code": inp_lo[0],
            "odu_operation_cycle": inp_lo[1],
            "inlet_temp": round(inp_lo[2] * 0.1, 1),
            "outlet_temp": round(inp_lo[3] * 0.1, 1),
            "backup_heater_outlet_temp": round(inp_lo[4] * 0.1, 1),
            "dhw_water_temp": round(inp_lo[5] * 0.1, 1),
            "solar_collector_temp": round(inp_lo[6] * 0.1, 1),
            "room_air_temp_circuit1": round(inp_lo[7] * 0.1, 1),
            "flow_rate": round(inp_lo[8] * 0.1, 1),
            "flow_temp_circle_2": round(inp_lo[9] * 0.1, 1),
            "room_air_temp_circuit2_in": round(inp_lo[10] * 0.1, 1),
            "energy_state_input": inp_lo[11],
            "outside_temp": round(inp_lo[12] * 0.1, 1),
            "water_pressure": round(inp_lo[13] * 0.1, 1),
            "temp_liquid_gas": round(inp_hi[0] * 0.1, 1),
            "temp_suction": round(inp_hi[2] * 0.1, 1),
            "temp_heatgas": round(inp_hi[3] * 0.1, 1),
            "temp_before_vaporiser": round(inp_hi[4] * 0.1, 1),
            "temp_after_vaporiser": round(inp_hi[5] * 0.1, 1),
            # Registers 22/23 count in hundredths of a bar, unlike register 13
            # (water pressure, tenths). Measured 2026-10-03: with 0.1 the
            # condenser read 63-80 bar at standstill and 220.6 bar at
            # 3600 rpm; with 0.01 that is 6-8 bar (pressure equalised, high
            # and low side within 1 bar) and 22.1 bar under load.
            "high_pressure": round(inp_hi[6] * 0.01, 2),
            "low_pressure": round(inp_hi[7] * 0.01, 2),
            "compressor_rpm": int(round(inp_hi[8] * 60)),
            "device_group": device_group,
            "product_info": product_info,
            # Holding registers
            "operation_mode": hold_low[0],
            "control_method": hold_low[1],
            "target_temp_circuit1": round(hold_low[2] * 0.1, 1),
            "room_air_temp_circuit1_hold": round(hold_low[3] * 0.1, 1),
            "shift_value_circuit1": _signed16(hold_low[4]),
            "target_temp_circuit2": round(hold_low[5] * 0.1, 1),
            "room_air_temp_circuit2_hold": round(hold_low[6] * 0.1, 1),
            "shift_value_circuit2": _signed16(hold_low[7]),
            "dhw_target_temp": round(hold_low[8] * 0.1, 1),
            "energy_state_raw": hold_low[9],
            # Coils
            "coil_hauptschalter": coils[0],
            "coil_dhw": coils[1],
            "coil_silent_mode": coils[2],
            "coil_dhw_desinfection": coils[3],
            "coil_emergency_stop": coils[4],
            "coil_emergency_trigger": coils[5],
            # Discrete inputs
            # Discrete input 10001. The manual documents this as
            # "0 = flow rate OK / 1 = flow rate too low", but on the R290
            # monoblock it reports the opposite: 1 means flow is present.
            # Measured 2026-08-18, four transitions in one session, di[0]
            # and di[1] (pump) identical in every sample of the same poll:
            #   flow  5.0 LPM, pump off -> di[0]=0, di[0:6]=[0,0,0,0,0,0]
            #   flow 15.3 LPM, pump on  -> di[0]=1, di[0:6]=[1,1,0,0,0,0]
            #   flow 29.5 LPM, pump on  -> di[0]=1, di[0:6]=[1,1,0,0,0,1]
            # Reporting "rate too low" at 29.5 LPM makes no sense, and a
            # read offset is ruled out because di[3] (compressor) and
            # di[5] (DHW heating) stay correctly aligned. Exposed as a
            # RUNNING sensor rather than a PROBLEM one, which previously
            # raised a false alert on every pump run.
            "di_water_flow": di[0],  # 1 = flow present
            "di_water_pump": di[1],
            "di_ext_water_pump": di[2],
            "di_compressor": di[3],
            "di_defrosting": di[4],
            "di_dhw_heating": di[5],
            "di_dhw_tank_desinfection": di[6],
            "di_silent_mode": di[7],
            "di_cooling": di[8],
            "di_solar_pump": di[9],
            "di_backup_heater_step1": di[10],
            "di_backup_heater_step2": di[11],
            "di_dhw_boost_heater": di[12],
            "di_error": di[13],
            "di_emergency_heating_cooling": di[14],
            "di_emergency_dhw": di[15],
            "di_mix_pump": di[16],
        }

    async def _async_read_experimental(
        self, inp_hi: list[int]
    ) -> dict[str, int | None]:
        """Read the undocumented registers, when the option asks for them.

        Unlike the documented reads these never fail the update. They exist to
        be looked at, so one that stops answering — another firmware, a bus
        hiccup — leaves its value empty and the heat pump data intact.
        """
        if not self._experimental:
            return {}

        values: dict[str, int | None] = {}
        for address in INPUT_FROM_MAIN_READ:
            values[register_key("input", address)] = inp_hi[address - 16]
        for kind, start, count in EXPERIMENTAL_BLOCKS:
            read = (
                self.unit.read_input_registers
                if kind == "input"
                else self.unit.read_holding_registers
            )
            try:
                registers = await read(start, count)
            except ModbusError as exc:
                _LOGGER.debug(
                    "Experimental %s registers %d-%d not read: %s",
                    kind,
                    start,
                    start + count - 1,
                    exc,
                )
                registers = [None] * count
            for offset, value in enumerate(registers):
                values[register_key(kind, start + offset)] = value
        return values

    async def async_load_capabilities(self) -> None:
        """Read the remembered capabilities before the first poll.

        Called from `async_setup_entry` ahead of the first refresh so that a
        known device needs no probe at all and its entities exist from the
        first second.
        """
        await self._capability_store.async_load()
        identity = identity_of(*(self._identity or (None, None)))
        support, reason = self._capability_store.restore(
            self._device_key, self._fingerprint, identity
        )
        self.capabilities = dict(support)
        self._capabilities_saved = dict(support)
        if reason != "hit":
            _LOGGER.debug(
                "Capability cache: %s (%d of %d features known)",
                reason,
                len(support),
                len(OPTIONAL_REGISTERS),
            )

    async def _async_detect_capabilities(self) -> None:
        """Ask the device once about each optional register.

        Runs only after a complete poll, which is the witness that a silence
        means "not served" rather than "cable unplugged". Each feature is asked
        separately: a block read spanning two neighbouring addresses would be
        dropped as a whole by a unit that serves only one of them.

        A probe for a feature the device lacks costs one request timeout, and
        on a shared connection that is 20 s. It is paid once per installation:
        the result is written to storage and read back on every later start.

        ONE PROBE PER CYCLE, deliberately. A unit that serves none of the
        three would otherwise stall the bus for a full minute in a single
        poll, and everything else on that bus with it -- on this installation
        an energy meter polling every 5 s. Three cycles with one 20 s stall
        each are survivable; one cycle with three is not. The cost arises once
        per installation either way.
        """
        pending = pending_probes(self.capabilities)
        if not pending:
            return

        for register in pending[:1]:
            try:
                if register.kind == "coil":
                    await self.unit.read_coils(register.address, register.probe_count)
                else:
                    await self.unit.read_holding_registers(
                        register.address, register.probe_count
                    )
            except ModbusError as exc:
                self.capabilities[register.key] = False
                _LOGGER.info(
                    "This unit does not serve %s (%s): %s",
                    register.key,
                    register.description,
                    exc,
                )
            else:
                self.capabilities[register.key] = True
                _LOGGER.info(
                    "This unit serves %s (%s)", register.key, register.description
                )

        if self.capabilities != self._capabilities_saved:
            await self._capability_store.async_update(
                self._device_key,
                self._fingerprint,
                identity_of(*(self._identity or (None, None))),
                self.capabilities,
            )
            self._capabilities_saved = dict(self.capabilities)

    async def _async_read_optional(self) -> dict[str, Any]:
        """Read the optional registers this unit actually serves.

        A read that fails here leaves the value empty instead of failing the
        poll: the mandatory blocks are what the heat pump is watched by, and a
        limit setting is not worth taking the rest down for.
        """
        values: dict[str, Any] = {}
        for register in OPTIONAL_REGISTERS:
            if not self.capabilities.get(register.key):
                continue
            try:
                if register.kind == "coil":
                    bits = await self.unit.read_coils(register.address, 1)
                    values[register.key] = bool(bits[0])
                else:
                    registers = await self.unit.read_holding_registers(
                        register.address, 1
                    )
                    values[register.key] = registers[0]
            except ModbusError as exc:
                _LOGGER.debug("Optional register %s not read: %s", register.key, exc)
                values[register.key] = None
        return values

    async def async_write_coil(self, address: int, value: bool) -> None:
        """Write a single coil register (FC05).

        A failure is raised, not just logged: these calls come from a button
        press or a switch being thrown, and a control that reports success
        while the machine did not move is worse than one that reports an error.
        """
        if address not in WRITABLE_COILS:
            raise HomeAssistantError(f"Coil {address} is not writable")
        try:
            await self.unit.write_coil(address, value)
        except ModbusError as exc:
            _LOGGER.error("Modbus error writing coil %d: %s", address, exc)
            raise HomeAssistantError(f"Writing coil {address} failed: {exc}") from exc

    async def async_write_register(self, address: int, value: int) -> None:
        """Write a single holding register (FC06).

        Note what this can and cannot promise. A write that returns without
        raising was acknowledged by the device, which is not the same as
        accepted: measured on 07.09.2026, writing 70.0 C to the DHW setpoint
        was echoed back byte for byte and then stored as 65.0, the device
        maximum. Callers that must know the value took should read it back —
        the entities do, by refreshing the coordinator after a write.
        """
        if address not in WRITABLE_HOLDING_REGISTERS:
            raise HomeAssistantError(f"Register {address} is not writable")
        try:
            await self.unit.write_register(address, value)
        except ModbusError as exc:
            _LOGGER.error("Modbus error writing register %d: %s", address, exc)
            raise HomeAssistantError(
                f"Writing register {address} failed: {exc}"
            ) from exc
