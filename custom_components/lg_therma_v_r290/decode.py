"""Turning raw register words into values.

Kept free of Home Assistant imports so the tests can load it on their own.
"""

from __future__ import annotations


def signed16(value: int) -> int:
    """Read an unsigned 16-bit register word as two's complement."""
    return value - 65536 if value >= 32768 else value


#: What a temperature input without a sensor sends: -64.9 °C as a signed word
#: (6488.7 °C read unsigned). Seen on Flow Temperature Circuit 2 (input 30010)
#: of a 12 kW unit with no second circuit, on the undocumented input 30015 of
#: two units (docs/register-scan.md), and in a forum report on input 30011.
#: No sensor of the unit reads that cold: the R290 runs down to -25 °C outdoors.
NO_SENSOR = 64887


def temperature(value: int) -> float | None:
    """Decode a temperature register in tenths of a degree.

    The unit sends temperatures as signed words: -0.2 °C arrives as 65534.
    Read unsigned, every value below zero became 6553.x °C -- outdoors in
    winter, and on the evaporator, suction and liquid gas sensors whenever
    the refrigerant runs below zero. Found and fixed first in cjungde's
    integration (cjungde/ha-lg-thermav-modbus@2bee3ce).

    None for NO_SENSOR: an input without a sensor has no temperature, and
    -64.9 °C would read as one (and drag down statistics and graphs).
    """
    if value == NO_SENSOR:
        return None
    return round(signed16(value) * 0.1, 1)
