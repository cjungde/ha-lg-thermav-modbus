"""The logic layer: derived behaviour that sits on top of the Modbus read.

The coordinator reads the registers and builds one dict of raw values. Anything
that is not a register but a judgement about one -- "this reading means nothing
in this state" -- belongs here, one function per judgement, each switchable in
the options. A function gets the poll's data and may overwrite values in it;
the entities then read the conditioned values and never know the difference.

Keeping this apart from the register map matters because the two change for
different reasons. The register map follows the unit, the logic follows what
someone wants to do with the numbers, and a user who wants the plain registers
must be able to have exactly that: every function here is off unless its
`default_enabled` says otherwise, and a layer with nothing enabled returns the
data untouched.

The flush pulse tracker (flush_pulse.py) is the next tenant. It is still wired
into the coordinator directly; moving it means implementing `LogicFunction` for
it, and it gets its switch in the options for free.

Deliberately free of Home Assistant imports, like flush_pulse.py, so it can be
tested on its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

#: Prefix of the option key a function is switched with. The options flow and
#: the translations derive their entries from `FUNCTIONS`, so a new function
#: needs no change outside this module apart from its two translated labels.
OPTION_PREFIX = "logic_"


def option_key(key: str) -> str:
    """The options key that switches the function `key`."""
    return f"{OPTION_PREFIX}{key}"


class LogicFunction(Protocol):
    """One switchable judgement over the poll's data."""

    #: Registry name, and the part after `logic_` in the option key.
    key: str
    #: What a fresh installation does. Off for anything that changes a value
    #: an existing installation already reports.
    default_enabled: bool

    def apply(self, data: dict[str, Any]) -> None:
        """Overwrite values in `data` in place; leave it alone if unsure."""


class FlowGate:
    """Report no flow while the circulation pump is off.

    The flow sensor is a SIKA VVX20 vortex meter with a measuring range of
    5-80 l/min. It cannot measure below the start of its range, so with the
    pump stopped the unit reports exactly 5.0 -- never less, and nothing between
    5.0 and about 6. On one installation that was 2535 hours between May and
    October 2026, all with the compressor at 0 rpm, and every 1 K of residual
    spread at standstill turned into roughly 350 W of thermal power that was
    never delivered (about 925 kWh over the period).

    The pump bit is the right gate rather than a threshold on the value: in the
    four weeks the bit was recorded (136,583 flow samples), 5.0 never occurred
    with the pump on, and the pump bit and the flow bit (10001) agreed in every
    hour. The ramp samples between 5 and about 12 l/min that arrive while the
    bit is still off are dropped as well -- about 0.1 % of samples, all of them
    transitions.

    The register value is kept as `flow_rate_raw` for anyone who wants it.
    """

    key = "flow_gate"
    default_enabled = False

    def apply(self, data: dict[str, Any]) -> None:
        pump = data.get("di_water_pump")
        flow = data.get("flow_rate")
        # Without both there is nothing to judge, and guessing would replace a
        # real reading with a made-up one.
        if pump is None or flow is None:
            return
        data["flow_rate_raw"] = flow
        if not pump:
            data["flow_rate"] = 0.0


#: Every function the integration has, in the order they are applied.
FUNCTIONS: dict[str, LogicFunction] = {f.key: f for f in (FlowGate(),)}


class LogicLayer:
    """The functions that are switched on, applied in registry order."""

    def __init__(self, enabled: Iterable[str]) -> None:
        wanted = set(enabled)
        unknown = wanted - FUNCTIONS.keys()
        if unknown:
            raise ValueError(f"unknown logic function(s): {sorted(unknown)}")
        self._active = [f for key, f in FUNCTIONS.items() if key in wanted]

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> LogicLayer:
        """Build from a config entry's options; absent keys take the default."""
        return cls(
            key
            for key, function in FUNCTIONS.items()
            if bool(options.get(option_key(key), function.default_enabled))
        )

    @property
    def active(self) -> list[str]:
        """Keys of the functions that will run."""
        return [f.key for f in self._active]

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Run the enabled functions over `data`, in place, and return it."""
        for function in self._active:
            function.apply(data)
        return data
