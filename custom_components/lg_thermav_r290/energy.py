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

    key: str
    address: int  # first of the two registers (high word)
    name: str
    kind: str

    @property
    def data_key(self) -> str:
        """Key of the decoded value in the coordinator data."""
        return f"energy_reg_{self.key}"

    @property
    def modbus_number(self) -> int:
        """Register number in the manual's notation (30001 based)."""
        return 30001 + self.address


ENERGY_REGISTERS: tuple[EnergyRegister, ...] = (
    EnergyRegister(
        "power_total_system", 34, "Electrical Power Total System", KIND_POWER
    ),
    EnergyRegister("power_heat_pump", 36, "Electrical Power Heat Pump", KIND_POWER),
    EnergyRegister("energy_total", 38, "Electrical Energy Total", KIND_ENERGY),
    EnergyRegister(
        "energy_heating", 40, "Electrical Energy Space Heating", KIND_ENERGY
    ),
    EnergyRegister(
        "energy_cooling", 42, "Electrical Energy Space Cooling", KIND_ENERGY
    ),
    EnergyRegister("energy_dhw", 44, "Electrical Energy DHW", KIND_ENERGY),
    # Reads 0-12 on a 12 kW unit: not a percentage. What the number means (a
    # step, or kW of demand) is not established, so it carries no unit.
    EnergyRegister("demand_vs_supply", 46, "Demand vs Supply", KIND_VALUE),
    EnergyRegister(
        "thermal_power", 48, "Thermal Power (Heat Pump Register)", KIND_POWER
    ),
    EnergyRegister(
        "thermal_energy_heating",
        50,
        "Thermal Energy Space Heating",
        KIND_ENERGY,
    ),
)

# Prefix of the unique ids of these sensors (after the config entry id), used to
# drop them from the entity registry when the option is switched off.
ENERGY_UNIQUE_ID_PREFIX = "energy_reg_"


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


class RetryBackoff:
    """Stop asking a unit that does not answer, but ask again later.

    A unit that does not serve the block never answers it (a timeout, not an
    exception), and every timeout holds the shared bus for its whole length.
    After a few misses in a row the read is skipped for a number of polls, so
    an option switched on by mistake costs a few timeouts, not one per poll —
    while a transient bus problem on a unit that does serve the block heals
    itself on the next attempt.
    """

    def __init__(self, failures_before_pause: int = 3, pause_polls: int = 20) -> None:
        self._threshold = failures_before_pause
        self._pause_polls = pause_polls
        self._failures = 0
        self._pause = 0

    def should_try(self) -> bool:
        """Whether this poll may read; a skipped poll counts the pause down."""
        if self._pause > 0:
            self._pause -= 1
            return False
        return True

    def record(self, ok: bool) -> bool:
        """Record an attempt; returns True when it starts a pause."""
        if ok:
            self._failures = 0
            return False
        self._failures += 1
        if self._failures >= self._threshold:
            self._failures = 0
            self._pause = self._pause_polls
            return True
        return False
