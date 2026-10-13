"""Which optional register groups a unit answers on.

Asked once during setup, and again only when the user asks for it in the
options. Each group is read the way the coordinator reads it; any Modbus error
counts as "does not answer". A unit that does not serve an address usually
stays silent rather than refusing it, so every group it lacks costs one
request timeout. That is why this never runs while polling.

Answering only proves the register exists, not that writing it does anything.
So only groups that are safe to switch on are suggested: the energy registers
(read only) and the compressor modulation limit (adds a slider; nothing is
written until it is moved). The power limit is reported but not suggested
while its effect is unconfirmed. Coil 5 answers on every unit and is off by
default because of what it does, so the emergency operation button and the
experimental registers are never checked or suggested.

Deliberately free of Home Assistant imports so it can be tested without a
Home Assistant install, like energy.py.
"""

from __future__ import annotations

from typing import Any

from modbus_connection.exceptions import ModbusError

from .const import (
    CONF_EMERGENCY_OPERATION,
    CONF_ENERGY_REGISTERS,
    CONF_EXPERIMENTAL,
    CONF_MODULATION_LIMIT,
    CONF_POWER_LIMIT,
)
from .energy import ENERGY_BLOCK_COUNT, ENERGY_BLOCK_START
from .limits import MODULATION_LIMIT_REGISTER
from .power_limit import POWER_LIMIT_COIL, POWER_LIMIT_REGISTER

# Option keys under which the last result, and when it was taken (ISO 8601),
# are kept in the entry's options.
CONF_DETECTED = "detected"
CONF_DETECTED_AT = "detected_at"

# All optional register groups, in the order the forms show them.
GROUPS = (
    CONF_ENERGY_REGISTERS,
    CONF_MODULATION_LIMIT,
    CONF_POWER_LIMIT,
    CONF_EMERGENCY_OPERATION,
    CONF_EXPERIMENTAL,
)

# The groups that are checked, in the order they are asked.
CHECKED = (CONF_ENERGY_REGISTERS, CONF_MODULATION_LIMIT, CONF_POWER_LIMIT)
# The groups switched on by default when the unit answers.
SUGGESTED_WHEN_ANSWERING = frozenset({CONF_ENERGY_REGISTERS, CONF_MODULATION_LIMIT})

# What the setup and options forms show per group. Symbols rather than words,
# so the same placeholder works in every translation.
ANSWERS = "✓"
NO_ANSWER = "✗"
NOT_CHECKED = "–"
# Status table: whether an option is on, and the mark for "the unit answers
# but the option is off", i.e. what could be switched on.
ON = "✓"
OFF = "–"
CAN_BE_SWITCHED_ON = "➕"


async def _answers(read) -> bool:
    try:
        await read()
    except ModbusError:
        return False
    return True


async def detect(unit: Any) -> dict[str, bool]:
    """Ask the unit for each optional group once; True where it answered."""
    energy = await _answers(
        lambda: unit.read_input_registers(ENERGY_BLOCK_START, ENERGY_BLOCK_COUNT)
    )
    modulation = await _answers(
        lambda: unit.read_holding_registers(MODULATION_LIMIT_REGISTER, 1)
    )
    # The coordinator needs both addresses; when the coil does not answer, the
    # register is not asked as well, which saves one more timeout.
    power_limit = await _answers(
        lambda: unit.read_coils(POWER_LIMIT_COIL, 1)
    ) and await _answers(lambda: unit.read_holding_registers(POWER_LIMIT_REGISTER, 1))
    return {
        CONF_ENERGY_REGISTERS: energy,
        CONF_MODULATION_LIMIT: modulation,
        CONF_POWER_LIMIT: power_limit,
    }


def suggested(detected: dict[str, bool] | None, current: dict[str, Any]) -> dict:
    """Option defaults after a check: switch on what answered and is safe to.

    Never switches anything off: an option already on stays on, whatever the
    check found (a unit can miss one request).
    """
    result = dict(current)
    for key in SUGGESTED_WHEN_ANSWERING:
        if detected and detected.get(key):
            result[key] = True
    return result


def placeholders(detected: dict[str, bool] | None) -> dict[str, str]:
    """Description placeholders: one symbol per checked group."""
    result = {}
    for key in CHECKED:
        if not detected or key not in detected:
            result[key] = NOT_CHECKED
        else:
            result[key] = ANSWERS if detected[key] else NO_ANSWER
    return result


def status_placeholders(
    detected: dict[str, bool] | None, options: dict[str, Any]
) -> dict[str, str]:
    """Placeholders for the status table in Configure.

    Per group ``<key>_on`` (✓ on, – off) and ``<key>`` (✓ answers, ✗ no
    answer, – not checked), with ➕ after ✓ where the option is off: those
    are the groups that could be switched on.
    """
    answers = placeholders(detected)
    result = {}
    for key in GROUPS:
        on = bool(options.get(key, False))
        result[f"{key}_on"] = ON if on else OFF
        mark = answers.get(key, NOT_CHECKED)
        if mark == ANSWERS and not on:
            mark = f"{ANSWERS} {CAN_BE_SWITCHED_ON}"
        result[key] = mark
    return result
