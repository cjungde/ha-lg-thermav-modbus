"""Turning raw register words into values.

Kept free of Home Assistant imports so the tests can load it on their own.
"""

from __future__ import annotations


def signed16(value: int) -> int:
    """Read an unsigned 16-bit register word as two's complement."""
    return value - 65536 if value >= 32768 else value


def temperature(value: int) -> float:
    """Decode a temperature register in tenths of a degree.

    The unit sends temperatures as signed words: -0.2 °C arrives as 65534.
    Read unsigned, every value below zero became 6553.x °C -- outdoors in
    winter, and on the evaporator, suction and liquid gas sensors whenever
    the refrigerant runs below zero. Found and fixed first in cjungde's
    integration (cjungde/ha-lg-thermav-modbus@2bee3ce).
    """
    return round(signed16(value) * 0.1, 1)
