"""Compressor modulation limit (holding register 23, 40024).

Holding 23 caps how far the compressor may modulate, in percent of its
maximum: 40-100 sets a limit, 0 means the limit is not used. It is not in the
manual's table and not every unit serves it: the 9 kW unit in
docs/register-scan.md does not answer on it, while a 12 kW unit answers on it
and is run with a limit set through it. The integration therefore reads and writes
it only when the option asks for it.

This is the one register outside the manual's write range that the integration
can write, and only while the option is on (see LGThermaVCoordinator). Every
value is clamped to 40-100 before it reaches the bus, so a slider, a service
call or an automation cannot send anything else.

Deliberately free of Home Assistant imports so the encoding can be tested
without a Home Assistant install, like energy.py and experimental.py.
"""

from __future__ import annotations

MODULATION_LIMIT_REGISTER = 23  # holding, 0-based (40024)
MODULATION_LIMIT_MIN = 40  # %
MODULATION_LIMIT_MAX = 100  # %
MODULATION_LIMIT_NOT_USED = 0  # raw value meaning "no limit set"

# Coordinator data keys.
DATA_KEY_LIMIT = "compressor_modulation_limit"  # % in force, None if not used
DATA_KEY_RAW = "compressor_modulation_limit_raw"  # register value as read

# Unique id suffix of the number entity, used to drop it from the entity
# registry when the option is switched off.
UNIQUE_ID_SUFFIX = "compressor_modulation_limit"


def decode(raw: int) -> dict[str, int | None]:
    """Coordinator data for one read of holding 23.

    0 is "limit not used", which has no place on a 40-100 slider; it is kept
    apart (limit None) instead of being shown as a percentage it is not.
    Any other value is reported as read, so a unit that holds something
    unexpected shows it rather than having it hidden by clamping.
    """
    if raw == MODULATION_LIMIT_NOT_USED:
        return {DATA_KEY_LIMIT: None, DATA_KEY_RAW: raw}
    return {DATA_KEY_LIMIT: raw, DATA_KEY_RAW: raw}


def encode(percent: float) -> int:
    """Register value for a requested limit, clamped to 40-100 %."""
    value = int(round(percent))
    return max(MODULATION_LIMIT_MIN, min(MODULATION_LIMIT_MAX, value))
