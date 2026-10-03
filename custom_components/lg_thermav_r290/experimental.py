"""Registers the device answers on although the manual does not list them.

A scan of the address space (2026-10-03, R290 9 kW, read-only) found 18
addresses that respond but are not in the manual's Modbus table. Nothing in
the manual, the manufacturer's material or the community projects explains
them, so the only way to learn what they are is to record them over weeks and
compare them with what the machine is doing. That is what the optional
experimental sensors are for.

Deliberately free of Home Assistant imports so the layout can be tested
without a Home Assistant install, like connection.py.

Everything here is read-only. These addresses are never written: the write
paths on the coordinator accept a fixed set of known addresses only.
"""

from __future__ import annotations

from dataclasses import dataclass

# (register type, first address, count). Blocks are read as one request each,
# and only contiguous answering addresses are grouped: one unanswered address
# in a block makes the device drop the whole request (input 15 does).
EXPERIMENTAL_BLOCKS: tuple[tuple[str, int, int], ...] = (
    ("input", 14, 1),  # 30015
    ("input", 63, 1),  # 30064
    ("holding", 10, 13),  # 40011-40023
    ("holding", 62, 2),  # 40063-40064
)

# Input 17 (30018) answers too, but it lies inside the block the coordinator
# already reads for the documented registers 16-24, so it is taken from there.
INPUT_FROM_MAIN_READ: tuple[int, ...] = (17,)

_MODBUS_BASE = {"input": 30001, "holding": 40001}


@dataclass(frozen=True)
class ExperimentalRegister:
    """One undocumented register that answers."""

    kind: str
    address: int

    @property
    def key(self) -> str:
        """Key of the raw value in the coordinator data."""
        return register_key(self.kind, self.address)

    @property
    def modbus_number(self) -> int:
        """Register number in the manual's notation (30001 / 40001 based)."""
        return _MODBUS_BASE[self.kind] + self.address

    @property
    def name(self) -> str:
        """Entity name; the number is the one a datasheet would use."""
        label = "Input" if self.kind == "input" else "Holding"
        return f"Experimental {label} {self.modbus_number}"


def register_key(kind: str, address: int) -> str:
    """Coordinator data key for an experimental register."""
    return f"exp_{kind}_{address}"


def _registers() -> tuple[ExperimentalRegister, ...]:
    found = [
        ExperimentalRegister(kind, start + offset)
        for kind, start, count in EXPERIMENTAL_BLOCKS
        for offset in range(count)
    ]
    found.extend(ExperimentalRegister("input", a) for a in INPUT_FROM_MAIN_READ)
    return tuple(sorted(found, key=lambda r: (r.kind, r.address)))


EXPERIMENTAL_REGISTERS: tuple[ExperimentalRegister, ...] = _registers()
