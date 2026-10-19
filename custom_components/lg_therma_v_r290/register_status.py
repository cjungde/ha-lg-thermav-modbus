"""What the optional reads have done since the integration started.

The check under Configure says what the unit answered when it was last asked;
this says what happened while polling: whether a group answers, missed a few
times, is resting after misses, or has been given up because it never
answered (energy.RetryBackoff). Four places show it, all from the same
coordinator snapshot: a Repairs notice for a group that was given up
(issues.py), a column in the status table under Configure, the "Optional
Registers" diagnostic sensor, and the diagnostics download.

Deliberately free of Home Assistant imports so it can be tested without a
Home Assistant install, like energy.py and detect.py.
"""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_ENERGY_REGISTERS,
    CONF_EXPERIMENTAL,
    CONF_MODULATION_LIMIT,
    CONF_POWER_LIMIT,
)
from .energy import (
    STATUS_ANSWERING,
    STATUS_GIVEN_UP,
    STATUS_MISSING,
    STATUS_NOT_READ,
    STATUS_PAUSED,
)

#: The groups read with a RetryBackoff, i.e. the ones that can be given up
#: and get a Repairs notice.
BACKOFF_GROUPS = (CONF_ENERGY_REGISTERS, CONF_MODULATION_LIMIT, CONF_POWER_LIMIT)

# Marks for the "Since start" column. Symbols rather than words, so the same
# placeholder works in every translation (like detect.py).
MARK_ANSWERING = "✓"
MARK_MISSING = "⚠"
MARK_PAUSED = "⏸"
MARK_GIVEN_UP = "⛔"
MARK_NONE = "–"  # option off, not read yet, or nothing to read

_MARKS = {
    STATUS_ANSWERING: MARK_ANSWERING,
    STATUS_MISSING: MARK_MISSING,
    STATUS_PAUSED: MARK_PAUSED,
    STATUS_GIVEN_UP: MARK_GIVEN_UP,
    STATUS_NOT_READ: MARK_NONE,
}

# States of the "Optional Registers" sensor: the worst of the groups that are
# on. A single miss is not a state of its own -- it is in the attributes --
# so an automation on the sensor does not fire on every hiccup on the bus.
STATE_OK = "ok"
STATE_PAUSED = "paused"
STATE_GIVEN_UP = "given_up"
STATE_NOT_USED = "not_used"
STATES = [STATE_OK, STATE_PAUSED, STATE_GIVEN_UP, STATE_NOT_USED]

#: Snapshot key of the experimental blocks given up (a list of "kind start").
EXPERIMENTAL_GIVEN_UP = "experimental_blocks_given_up"


def overall_state(snapshot: dict[str, Any]) -> str:
    """The sensor state for a coordinator snapshot (see LGThermaVCoordinator).

    ``snapshot`` holds, per backoff group, its status or None while the
    option is off. The experimental registers do not count: blocks of them
    are given up on many units, which is expected rather than a fault.
    """
    statuses = [snapshot.get(g) for g in BACKOFF_GROUPS if snapshot.get(g)]
    if not statuses:
        return STATE_NOT_USED
    if STATUS_GIVEN_UP in statuses:
        return STATE_GIVEN_UP
    if STATUS_PAUSED in statuses:
        return STATE_PAUSED
    return STATE_OK


def attributes(snapshot: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    """Attributes of the "Optional Registers" sensor.

    Per backoff group its status since start ("off" while the option is off)
    and what the last check found ("answers", "no_answer", "not_checked");
    the experimental registers as on/off with the blocks given up; and when
    the last check ran.
    """
    detected = options.get("detected") or {}
    result: dict[str, Any] = {}
    for group in BACKOFF_GROUPS:
        result[group] = snapshot.get(group) or "off"
        if group not in detected:
            result[f"{group}_last_check"] = "not_checked"
        else:
            result[f"{group}_last_check"] = (
                "answers" if detected[group] else "no_answer"
            )
    result[CONF_EXPERIMENTAL] = "on" if snapshot.get(CONF_EXPERIMENTAL) else "off"
    result[EXPERIMENTAL_GIVEN_UP] = list(snapshot.get(EXPERIMENTAL_GIVEN_UP, []))
    result["last_check"] = options.get("detected_at")
    return result


def since_start_placeholders(
    snapshot: dict[str, Any] | None, groups: tuple[str, ...]
) -> dict[str, str]:
    """Placeholders ``<group>_now`` for the "Since start" column.

    ``snapshot`` is None when the entry is not loaded: then nothing has been
    read, and every row shows –.
    """
    result = {}
    for group in groups:
        mark = MARK_NONE
        if snapshot is not None:
            if group in BACKOFF_GROUPS and snapshot.get(group):
                mark = _MARKS[snapshot[group]]
            elif group == CONF_EXPERIMENTAL and snapshot.get(CONF_EXPERIMENTAL):
                given_up = len(snapshot.get(EXPERIMENTAL_GIVEN_UP, ()))
                mark = f"{MARK_GIVEN_UP} {given_up}" if given_up else MARK_ANSWERING
        result[f"{group}_now"] = mark
    return result
