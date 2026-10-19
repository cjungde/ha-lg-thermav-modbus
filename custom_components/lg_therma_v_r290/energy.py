"""Electrical power, energy and thermal yield registers (input 34-51).

These registers are not in the manual's table and not every unit serves them:
a read-only scan of a 9 kW unit (see docs/register-scan.md) got no answer from
input 25-62, while a 12 kW unit answers on 34-51. The integration therefore
reads them only when the option asks for it, and never lets a failed read
fail the update of the documented registers.

Each value is an unsigned 32-bit number spread over two consecutive input
registers, high word first (the order Home Assistant's own modbus component
assumes by default, which is what the YAML setup this was taken from relies
on). Registers 52-55 (cumulative thermal yield for cooling and DHW) are left
out on purpose: they do not answer on a 12 kW unit, and a request that
includes an address the device does not serve is dropped as a whole.

Deliberately free of Home Assistant imports so the layout and the decoding can
be tested without a Home Assistant install, like experimental.py.

Everything here is read-only.
"""

from __future__ import annotations

from dataclasses import dataclass

# Input registers 34-51 in one request: every address in it answers on a unit
# that serves the block at all, and a request that includes an address the
# device does not serve is dropped as a whole.
ENERGY_BLOCK_START = 34
ENERGY_BLOCK_COUNT = 18

KIND_POWER = "power"  # W
KIND_ENERGY = "energy"  # Wh, cumulative
KIND_VALUE = "value"  # plain number, no unit


@dataclass(frozen=True)
class EnergyRegister:
    """One 32-bit value in the energy block."""

    key: str  # entity key: the name as an entity id slug (docs/naming.md)
    address: int  # first of the two registers (high word)
    name: str
    kind: str

    @property
    def data_key(self) -> str:
        """Key of the decoded value in the coordinator data."""
        return f"input_{self.key}"

    @property
    def modbus_number(self) -> int:
        """Register number in the manual's notation (30001 based)."""
        return 30001 + self.address


ENERGY_REGISTERS: tuple[EnergyRegister, ...] = (
    EnergyRegister(
        "electrical_power_total_system",
        34,
        "Electrical Power Total System",
        KIND_POWER,
    ),
    EnergyRegister(
        "electrical_power_heat_pump", 36, "Electrical Power Heat Pump", KIND_POWER
    ),
    EnergyRegister(
        "electrical_energy_total", 38, "Electrical Energy Total", KIND_ENERGY
    ),
    EnergyRegister(
        "electrical_energy_space_heating",
        40,
        "Electrical Energy Space Heating",
        KIND_ENERGY,
    ),
    EnergyRegister(
        "electrical_energy_space_cooling",
        42,
        "Electrical Energy Space Cooling",
        KIND_ENERGY,
    ),
    EnergyRegister("electrical_energy_dhw", 44, "Electrical Energy DHW", KIND_ENERGY),
    # Reads 0-12 on a 12 kW unit: not a percentage. What the number means (a
    # step, or kW of demand) is not established, so it carries no unit.
    EnergyRegister("demand_vs_supply", 46, "Demand vs Supply", KIND_VALUE),
    EnergyRegister(
        "thermal_power_reported", 48, "Thermal Power (Reported)", KIND_POWER
    ),
    EnergyRegister(
        "thermal_energy_space_heating",
        50,
        "Thermal Energy Space Heating",
        KIND_ENERGY,
    ),
)

_BY_ADDRESS = {register.address: register for register in ENERGY_REGISTERS}

# Coordinator data keys the COP sensors divide (see cop.py).
DATA_KEY_ELECTRICAL_POWER_TOTAL_SYSTEM = _BY_ADDRESS[34].data_key
DATA_KEY_ELECTRICAL_POWER_HEAT_PUMP = _BY_ADDRESS[36].data_key
DATA_KEY_ELECTRICAL_ENERGY_SPACE_HEATING = _BY_ADDRESS[40].data_key
DATA_KEY_THERMAL_POWER_REPORTED = _BY_ADDRESS[48].data_key
DATA_KEY_THERMAL_ENERGY_SPACE_HEATING = _BY_ADDRESS[50].data_key


def decode_uint32(high: int, low: int) -> int:
    """Join two 16-bit registers, high word first."""
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


def decode_block(registers: list[int]) -> dict[str, int]:
    """Decode a read of the energy block into coordinator data."""
    if len(registers) != ENERGY_BLOCK_COUNT:
        raise ValueError(
            f"expected {ENERGY_BLOCK_COUNT} registers, got {len(registers)}"
        )
    values: dict[str, int] = {}
    for register in ENERGY_REGISTERS:
        offset = register.address - ENERGY_BLOCK_START
        values[register.data_key] = decode_uint32(
            registers[offset], registers[offset + 1]
        )
    return values


#: What an optional read has done since the integration started, as
#: RetryBackoff.status() reports it.
STATUS_NOT_READ = "not_read"  # no attempt yet
STATUS_ANSWERING = "answering"  # the last attempt answered
STATUS_MISSING = "missing"  # missed, but not often enough to pause yet
STATUS_PAUSED = "paused"  # answered before; resting after missing a few times
STATUS_GIVEN_UP = "given_up"  # never answered; not asked again until a reload

#: What RetryBackoff.record() reports when a miss changes what happens next.
EVENT_PAUSED = "paused"
EVENT_GAVE_UP = "gave_up"


class RetryBackoff:
    """Stop asking a unit that does not answer; ask again later only if it ever did.

    A unit that does not serve the block never answers it (a timeout, not an
    exception), and every timeout holds the shared bus for its whole length.
    After a few misses in a row the read stops, and what happens next depends
    on whether the block has ever answered since the integration started:

    * **Never answered:** the unit most likely does not serve it, and a
      register a unit lacks does not appear without a firmware update. The
      read is given up until the integration is reloaded or Home Assistant
      restarts, so an option switched on by mistake costs one round of
      timeouts, not one every few minutes for good.
    * **Answered before:** most likely a hiccup on the bus. The read is skipped
      for a number of polls and then tried again, so it heals by itself.
    """

    def __init__(self, failures_before_pause: int = 3, pause_polls: int = 20) -> None:
        self._threshold = failures_before_pause
        self._pause_polls = pause_polls
        self._failures = 0
        self._pause = 0
        self._attempted = False
        self._ever_answered = False
        self._given_up = False

    def should_try(self) -> bool:
        """Whether this poll may read; a skipped poll counts the pause down."""
        if self._given_up:
            return False
        if self._pause > 0:
            self._pause -= 1
            return False
        return True

    def status(self) -> str:
        """One of the STATUS_* values above."""
        if self._given_up:
            return STATUS_GIVEN_UP
        if self._pause > 0:
            return STATUS_PAUSED
        if not self._attempted:
            return STATUS_NOT_READ
        if self._failures:
            return STATUS_MISSING
        return STATUS_ANSWERING

    def state(self) -> dict[str, int | bool | str]:
        """The status with its counters, for diagnostics."""
        return {
            "status": self.status(),
            "ever_answered": self._ever_answered,
            "misses_in_a_row": self._failures,
            "paused_polls_left": self._pause,
        }

    def record(self, ok: bool) -> str | None:
        """Record an attempt; returns EVENT_PAUSED or EVENT_GAVE_UP when the
        read stops, None otherwise."""
        self._attempted = True
        if ok:
            self._ever_answered = True
            self._failures = 0
            return None
        self._failures += 1
        if self._failures < self._threshold:
            return None
        self._failures = 0
        if not self._ever_answered:
            self._given_up = True
            return EVENT_GAVE_UP
        self._pause = self._pause_polls
        return EVENT_PAUSED
