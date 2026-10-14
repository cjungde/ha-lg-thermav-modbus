"""Power limit (coil 6 / 00007 and holding 24 / 40025).

The manual lists both:

- coil 00007 "Wirkleistungsbegrenzung": 0 not used / 1 limit the power per
  register 40025
- holding 40025 "Leistungsbegrenzungswert": 0.1 kW ~ 25.0 kW, in tenths of a kW

Not every unit serves them: the 9 kW unit in docs/register-scan.md answers on
neither, and whether a unit that answers actually holds its power below the
limit is not confirmed yet. The integration therefore reads and writes them
only while the option asks for it, and the coordinator adds them to its write
whitelists only then. Every limit is clamped to 0.1-25.0 kW before it reaches
the bus.

Deliberately free of Home Assistant imports so the encoding can be tested
without a Home Assistant install, like limits.py.
"""

from __future__ import annotations

POWER_LIMIT_COIL = 6  # coil, 0-based (00007)
POWER_LIMIT_REGISTER = 24  # holding, 0-based (40025)

POWER_LIMIT_MIN_KW = 0.1
POWER_LIMIT_MAX_KW = 25.0
_RAW_MIN = 1  # 0.1 kW in tenths
_RAW_MAX = 250  # 25.0 kW in tenths

# Entity keys (docs/naming.md) and coordinator data keys (the raw registers).
KEY_POWER_LIMIT = "power_limit"  # switch, coil 6
KEY_MAX_ELECTRICAL_POWER = "max_electrical_power"  # number, holding 24
DATA_KEY_POWER_LIMIT = "coil_power_limit"
DATA_KEY_MAX_ELECTRICAL_POWER = "holding_max_electrical_power"


def decode_kw(raw: int | None) -> float | None:
    """The limit in kW, or None while the register holds 0 (or was not read).

    0 is below the manual's range and has no place on a 0.1-25.0 kW slider; it
    is shown as no value rather than as a power it is not. Any other value is
    reported as read, so a unit that holds something unexpected shows it
    rather than having it hidden by clamping.
    """
    if raw is None or raw == 0:
        return None
    return round(raw / 10, 1)


def encode_kw(kw: float) -> int:
    """Register value (tenths of a kW) for a requested limit, clamped."""
    raw = int(round(kw * 10))
    return max(_RAW_MIN, min(_RAW_MAX, raw))
