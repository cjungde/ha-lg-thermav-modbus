"""DataUpdateCoordinator for the LG Therma V R290."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.components.modbus import async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from modbus_connection.exceptions import ModbusError, ModbusExceptionError

from .compressor_stats import CompressorStats
from .connection import params_from_entry_data
from .const import (
    CONF_COMPRESSOR_STATISTICS,
    CONF_EMERGENCY_OPERATION,
    CONF_ENERGY_REGISTERS,
    CONF_EXPERIMENTAL,
    CONF_MODULATION_LIMIT,
    CONF_POWER_LIMIT,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EMERGENCY_OPERATION_WRITABLE_COILS,
    MODULATION_LIMIT_WRITABLE_HOLDING_REGISTERS,
    POWER_LIMIT_WRITABLE_COILS,
    POWER_LIMIT_WRITABLE_HOLDING_REGISTERS,
    WRITABLE_COILS,
    WRITABLE_HOLDING_REGISTERS,
)
from .energy import (
    ENERGY_BLOCK_COUNT,
    ENERGY_BLOCK_START,
    RetryBackoff,
    decode_block,
)
from .experimental import (
    EXPERIMENTAL_BLOCKS,
    INPUT_FROM_MAIN_READ,
    BlockGate,
    data_key,
)
from .limits import DATA_KEY_MAX_COMPRESSOR_MODULATION, MODULATION_LIMIT_REGISTER
from .pollstats import CountingUnit, stats
from .power_limit import (
    DATA_KEY_MAX_ELECTRICAL_POWER,
    DATA_KEY_POWER_LIMIT,
    POWER_LIMIT_COIL,
    POWER_LIMIT_REGISTER,
)

_LOGGER = logging.getLogger(__name__)

#: Per-request timeout floor for this unit (taken over from cjungde's
#: integration). `modbus_connection`'s own default is 10 s, which is not
#: generous on a SHARED connection: requests from every consumer on the
#: endpoint queue behind one lock, so waiting time adds up rather than
#: overlapping. An answer that arrives after the client gave up on it does not
#: vanish -- it is read as the reply to the NEXT request and shows up as
#: `Received unexpected response with Transaction ID`, followed by a dropped
#: link.
#:
#: `require_timeout` raises the timeout of the whole LINK to at least this
#: value -- it resolves to the maximum over all units on it, so the call is a
#: floor and not an assignment, and setting it here does not shorten anyone
#: else's. Raising it drops the current connection so the new value takes
#: effect at once, which is why this is called once at setup and never again.
#:
#: Needs `modbus-connection` 4.12.3 (Home Assistant 2026.10); the 4.10.0 that
#: the 2026.9 line pins has no such method.
_REQUEST_TIMEOUT = 20.0


def _monotonic() -> float:
    """The clock the compressor statistics run on (replaced in tests)."""
    return time.monotonic()


def _signed16(value: int) -> int:
    """Convert an unsigned 16-bit register value to a signed integer."""
    return value - 65536 if value >= 32768 else value


class LGThermaVCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the LG Therma V R290 at a fixed interval and distributes data to entities."""

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
        # Counts the reads of each poll for the poll statistics (pollstats.py).
        self.unit = CountingUnit(
            async_get_unit(
                hass,
                entry,
                params_from_entry_data(dict(entry.data)),
                int(entry.data[CONF_SLAVE_ID]),
            )
        )
        self.unit.require_timeout(_REQUEST_TIMEOUT)

        self._experimental = bool(entry.options.get(CONF_EXPERIMENTAL, False))
        self._experimental_gate = BlockGate()
        # Starts, run time and average speed, counted per poll from data
        # already read (compressor_stats.py); only with its option.
        self.compressor_stats = (
            CompressorStats()
            if entry.options.get(CONF_COMPRESSOR_STATISTICS, False)
            else None
        )
        self._energy = bool(entry.options.get(CONF_ENERGY_REGISTERS, False))
        self._energy_backoff = RetryBackoff()
        self._modulation_limit = bool(entry.options.get(CONF_MODULATION_LIMIT, False))
        self._modulation_backoff = RetryBackoff()
        self._power_limit = bool(entry.options.get(CONF_POWER_LIMIT, False))
        self._power_limit_backoff = RetryBackoff()
        # Holding 23, holding 24 and coils 5 and 6 join the write whitelists
        # only while their option is on; with the option off the integration
        # cannot write them at all.
        writable_holding = set(WRITABLE_HOLDING_REGISTERS)
        writable_coils = set(WRITABLE_COILS)
        if self._modulation_limit:
            writable_holding |= MODULATION_LIMIT_WRITABLE_HOLDING_REGISTERS
        if entry.options.get(CONF_EMERGENCY_OPERATION, False):
            writable_coils |= EMERGENCY_OPERATION_WRITABLE_COILS
        if self._power_limit:
            writable_holding |= POWER_LIMIT_WRITABLE_HOLDING_REGISTERS
            writable_coils |= POWER_LIMIT_WRITABLE_COILS
        self._writable_holding = frozenset(writable_holding)
        self._writable_coils = frozenset(writable_coils)

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
        """Poll the unit, and time the poll for Poll Duration and Bus Load."""
        self.unit.reads = 0
        start = time.monotonic()
        data = await self._async_poll()
        if self.compressor_stats is not None:
            on = data.get("discrete_compressor")
            self.compressor_stats.add(
                None if on is None else bool(on),
                data.get("input_compressor_speed"),
                _monotonic(),
                dt_util.now().date().isoformat(),
            )
        data.update(
            stats(
                time.monotonic() - start,
                self.update_interval.total_seconds(),
                self.unit.reads,
            )
        )
        return data

    async def _async_poll(self) -> dict[str, Any]:
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

        experimental = await self._async_read_experimental(inp_hi)
        energy = await self._async_read_energy()
        modulation_limit = await self._async_read_modulation_limit()
        power_limit = await self._async_read_power_limit()

        return {
            **experimental,
            **energy,
            **modulation_limit,
            **power_limit,
            # Input registers (raw × scale)
            # inp_lo[n] = register n  (0-13)
            # inp_hi[n] = register 16+n (16-24)
            "input_error_code": inp_lo[0],
            "input_operation_cycle_odu": inp_lo[1],
            "input_inlet_temperature": round(inp_lo[2] * 0.1, 1),
            "input_outlet_temperature": round(inp_lo[3] * 0.1, 1),
            "input_backup_heater_outlet_temperature": round(inp_lo[4] * 0.1, 1),
            "input_dhw_temperature": round(inp_lo[5] * 0.1, 1),
            "input_solar_collector_temperature": round(inp_lo[6] * 0.1, 1),
            "input_room_air_temperature_circuit_1": round(inp_lo[7] * 0.1, 1),
            "input_flow_rate": round(inp_lo[8] * 0.1, 1),
            "input_flow_temperature_circuit_2": round(inp_lo[9] * 0.1, 1),
            "input_room_air_temperature_circuit_2": round(inp_lo[10] * 0.1, 1),
            "input_energy_control_signal": inp_lo[11],
            "input_outdoor_temperature": round(inp_lo[12] * 0.1, 1),
            "input_water_pressure": round(inp_lo[13] * 0.1, 1),
            "input_liquid_gas_temperature": round(inp_hi[0] * 0.1, 1),
            "input_suction_temperature": round(inp_hi[2] * 0.1, 1),
            "input_hot_gas_temperature": round(inp_hi[3] * 0.1, 1),
            "input_temperature_before_evaporator": round(inp_hi[4] * 0.1, 1),
            "input_temperature_after_evaporator": round(inp_hi[5] * 0.1, 1),
            # Registers 22/23 count in hundredths of a bar, unlike register 13
            # (water pressure, tenths). Measured 2026-10-03: with 0.1 the
            # condenser read 63-80 bar at standstill and 220.6 bar at
            # 3600 rpm; with 0.01 that is 6-8 bar (pressure equalised, high
            # and low side within 1 bar) and 22.1 bar under load.
            "input_high_pressure_condenser": round(inp_hi[6] * 0.01, 2),
            "input_low_pressure_evaporator": round(inp_hi[7] * 0.01, 2),
            "input_compressor_speed": int(round(inp_hi[8] * 60)),
            "input_device_group": device_group,
            "input_product_information": product_info,
            # Holding registers
            "holding_operation_mode": hold_low[0],
            "holding_control_method": hold_low[1],
            "holding_target_temperature_circuit_1": round(hold_low[2] * 0.1, 1),
            "holding_target_room_air_temperature_circuit_1": round(
                hold_low[3] * 0.1, 1
            ),
            "holding_setpoint_shift_circuit_1": _signed16(hold_low[4]),
            "holding_target_temperature_circuit_2": round(hold_low[5] * 0.1, 1),
            "holding_target_room_air_temperature_circuit_2": round(
                hold_low[6] * 0.1, 1
            ),
            "holding_setpoint_shift_circuit_2": _signed16(hold_low[7]),
            "holding_dhw_target_temperature": round(hold_low[8] * 0.1, 1),
            "holding_energy_state": hold_low[9],
            # Coils
            "coil_heating_cooling": coils[0],
            "coil_dhw": coils[1],
            "coil_silent_mode": coils[2],
            "coil_start_disinfection": coils[3],
            "coil_emergency_stop": coils[4],
            "coil_start_emergency_operation": coils[5],
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
            "discrete_water_flow": di[0],  # 1 = flow present
            "discrete_water_pump": di[1],
            "discrete_external_water_pump": di[2],
            "discrete_compressor": di[3],
            "discrete_defrost": di[4],
            "discrete_dhw_heating": di[5],
            "discrete_dhw_disinfection": di[6],
            "discrete_silent_mode": di[7],
            "discrete_cooling_active": di[8],
            "discrete_solar_pump": di[9],
            "discrete_backup_heater_step_1": di[10],
            "discrete_backup_heater_step_2": di[11],
            "discrete_dhw_boost_heater": di[12],
            "discrete_fault": di[13],
            "discrete_emergency_heating_cooling_available": di[14],
            "discrete_emergency_dhw_available": di[15],
            "discrete_mixing_pump": di[16],
        }

    def diagnostics(self) -> dict[str, Any]:
        """The state of the optional reads, for the diagnostics download."""
        return {
            "identity_registers": (
                None
                if self._identity is None
                else {"39998": self._identity[0], "39999": self._identity[1]}
            ),
            "energy_registers": {
                "enabled": self._energy,
                **self._energy_backoff.state(),
            },
            "compressor_modulation_limit": {
                "enabled": self._modulation_limit,
                **self._modulation_backoff.state(),
            },
            "power_limit": {
                "enabled": self._power_limit,
                **self._power_limit_backoff.state(),
            },
            "experimental_registers": {
                "enabled": self._experimental,
                "blocks_given_up": sorted(
                    f"{kind} {start}"
                    for kind, start in self._experimental_gate.given_up
                ),
            },
            "writable_holding_registers": sorted(self._writable_holding),
            "writable_coils": sorted(self._writable_coils),
        }

    async def _async_read_experimental(
        self, inp_hi: list[int]
    ) -> dict[str, int | None]:
        """Read the undocumented registers, when the option asks for them.

        Unlike the documented reads these never fail the update. They exist to
        be looked at, so one that does not answer leaves its values empty and
        the heat pump data intact. A block the unit does not answer is not
        asked again until the next restart (see BlockGate).
        """
        if not self._experimental:
            return {}

        values: dict[str, int | None] = {}
        for address in INPUT_FROM_MAIN_READ:
            values[data_key("input", address)] = inp_hi[address - 16]
        for kind, start, count in EXPERIMENTAL_BLOCKS:
            read = (
                self.unit.read_input_registers
                if kind == "input"
                else self.unit.read_holding_registers
            )
            registers: list[int | None] = [None] * count
            if self._experimental_gate.should_read(kind, start):
                try:
                    registers = await read(start, count)
                except ModbusError as exc:
                    refused = isinstance(exc, ModbusExceptionError)
                    if self._experimental_gate.record(
                        kind, start, ok=False, refused=refused
                    ):
                        _LOGGER.warning(
                            "Experimental %s registers %d-%d %s; not asking "
                            "for them again until the next restart (%s)",
                            kind,
                            start,
                            start + count - 1,
                            "are refused by this unit" if refused else "do not answer",
                            exc,
                        )
                    else:
                        _LOGGER.debug(
                            "Experimental %s registers %d-%d not read: %s",
                            kind,
                            start,
                            start + count - 1,
                            exc,
                        )
                else:
                    self._experimental_gate.record(kind, start, ok=True)
            for offset, value in enumerate(registers):
                values[data_key(kind, start + offset)] = value
        return values

    async def _async_read_energy(self) -> dict[str, int]:
        """Read the electrical power / energy block, when the option asks for it.

        Like the experimental registers this never fails the update: not every
        unit serves input 34-51, and one that does not leaves the sensors
        without a value while the documented data stays intact. A unit that
        keeps not answering is asked again only every few polls (see
        RetryBackoff), because each unanswered request is a timeout on a bus
        that other integrations share.
        """
        if not self._energy or not self._energy_backoff.should_try():
            return {}
        try:
            registers = await self.unit.read_input_registers(
                ENERGY_BLOCK_START, ENERGY_BLOCK_COUNT
            )
        except ModbusError as exc:
            if self._energy_backoff.record(False):
                _LOGGER.warning(
                    "Energy registers %d-%d did not answer; pausing the read "
                    "for a while. This unit may not serve them - switch the "
                    "option off in the integration's options if so (%s)",
                    ENERGY_BLOCK_START,
                    ENERGY_BLOCK_START + ENERGY_BLOCK_COUNT - 1,
                    exc,
                )
            else:
                _LOGGER.debug("Energy registers not read: %s", exc)
            return {}
        self._energy_backoff.record(True)
        return decode_block(registers)

    async def _async_read_modulation_limit(self) -> dict[str, int]:
        """Read the compressor modulation limit, when the option asks for it.

        Same rules as the energy block: a unit that does not serve holding 23
        leaves the entity unavailable without failing the update, and is asked
        again only every few polls.
        """
        if not self._modulation_limit or not self._modulation_backoff.should_try():
            return {}
        try:
            registers = await self.unit.read_holding_registers(
                MODULATION_LIMIT_REGISTER, 1
            )
        except ModbusError as exc:
            if self._modulation_backoff.record(False):
                _LOGGER.warning(
                    "Compressor modulation limit (holding %d) did not answer; "
                    "pausing the read for a while. This unit may not serve "
                    "it - switch the option off in the integration's options "
                    "if so (%s)",
                    MODULATION_LIMIT_REGISTER,
                    exc,
                )
            else:
                _LOGGER.debug("Compressor modulation limit not read: %s", exc)
            return {}
        self._modulation_backoff.record(True)
        return {DATA_KEY_MAX_COMPRESSOR_MODULATION: registers[0]}

    async def _async_read_power_limit(self) -> dict[str, int]:
        """Read the power limit (coil 6 and holding 24), when the option asks.

        Each address in its own request: a coil that does not answer must not
        take the main coil read with it. Same rules as the other optional
        reads otherwise: the pair counts as one feature, a unit that does not
        serve it leaves both entities unavailable without failing the update,
        and is asked again only every few polls.
        """
        if not self._power_limit or not self._power_limit_backoff.should_try():
            return {}
        try:
            coils = await self.unit.read_coils(POWER_LIMIT_COIL, 1)
            registers = await self.unit.read_holding_registers(POWER_LIMIT_REGISTER, 1)
        except ModbusError as exc:
            if self._power_limit_backoff.record(False):
                _LOGGER.warning(
                    "Power limit (coil %d / holding %d) did not answer; pausing "
                    "the read for a while. This unit may not serve it - switch "
                    "the option off in the integration's options if so (%s)",
                    POWER_LIMIT_COIL,
                    POWER_LIMIT_REGISTER,
                    exc,
                )
            else:
                _LOGGER.debug("Power limit not read: %s", exc)
            return {}
        self._power_limit_backoff.record(True)
        return {
            DATA_KEY_POWER_LIMIT: int(bool(coils[0])),
            DATA_KEY_MAX_ELECTRICAL_POWER: registers[0],
        }

    async def async_write_coil(self, address: int, value: bool) -> None:
        """Write a single coil register (FC05).

        A failure is raised, not just logged: these calls come from a button
        press or a switch being thrown, and a control that reports success
        while the machine did not move is worse than one that reports an error.
        """
        if address not in self._writable_coils:
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
        if address not in self._writable_holding:
            raise HomeAssistantError(f"Register {address} is not writable")
        try:
            await self.unit.write_register(address, value)
        except ModbusError as exc:
            _LOGGER.error("Modbus error writing register %d: %s", address, exc)
            raise HomeAssistantError(
                f"Writing register {address} failed: {exc}"
            ) from exc
