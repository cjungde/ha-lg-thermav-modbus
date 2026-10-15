"""How long a poll takes, and how much of the poll interval that is.

The coordinator times every poll from its first request to its last and
counts the requests. Two diagnostic sensors show the result: Poll Duration
(ms) and Bus Load (% of the poll interval). The duration includes any time
spent waiting for the bus behind other integrations on a shared connection,
so on a bus of its own Bus Load is the whole bus, on a shared one this
integration's share plus its waiting.

Deliberately free of Home Assistant imports so it can be tested without a
Home Assistant install, like energy.py.
"""

from __future__ import annotations

from typing import Any

# Entity keys (docs/naming.md) and coordinator data keys. The data keys carry
# the prefix poll_: these values come from no register, but from the polling.
KEY_POLL_DURATION = "poll_duration"
KEY_BUS_LOAD = "bus_load"
DATA_KEY_POLL_DURATION = "poll_duration_ms"
DATA_KEY_BUS_LOAD = "poll_bus_load"
DATA_KEY_POLL_REQUESTS = "poll_requests"

_READS = (
    "read_input_registers",
    "read_holding_registers",
    "read_coils",
    "read_discrete_inputs",
)


class CountingUnit:
    """A Modbus unit that counts the reads made through it.

    Everything else is passed through unchanged, so the coordinator uses it
    exactly like the unit it wraps.
    """

    def __init__(self, unit: Any) -> None:
        self._unit = unit
        self.reads = 0

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._unit, name)
        if name not in _READS:
            return attribute

        async def counted(*args: Any, **kwargs: Any) -> Any:
            self.reads += 1
            return await attribute(*args, **kwargs)

        return counted


def stats(duration_s: float, interval_s: float, requests: int) -> dict[str, Any]:
    """Coordinator data for one poll: duration in ms, bus load in %."""
    load = 100.0 * duration_s / interval_s if interval_s > 0 else None
    return {
        DATA_KEY_POLL_DURATION: int(round(duration_s * 1000)),
        DATA_KEY_BUS_LOAD: None if load is None else round(load, 1),
        DATA_KEY_POLL_REQUESTS: requests,
    }
