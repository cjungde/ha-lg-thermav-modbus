"""How long a poll takes, how much of the poll interval that is, and what failed.

The coordinator times every poll from its first request to its last and
counts the requests. Two diagnostic sensors show the result: Poll Duration
(ms) and Bus Load (% of the poll interval). The duration includes any time
spent waiting for the bus behind other integrations on a shared connection,
so on a bus of its own Bus Load is the whole bus, on a shared one this
integration's share plus its waiting.

Every request that fails is also written down (ErrorLog): two more diagnostic
sensors, Modbus Errors (a counter since start) and Last Modbus Error (its
message, with the request and the time as attributes), put on a dashboard
what otherwise only shows up in the log.

Deliberately free of Home Assistant imports so it can be tested without a
Home Assistant install, like energy.py.
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
import time
from typing import Any

# Entity keys (docs/naming.md) and coordinator data keys. The data keys carry
# the prefix poll_: these values come from no register, but from the polling.
KEY_POLL_DURATION = "poll_duration"
KEY_BUS_LOAD = "bus_load"
KEY_MODBUS_ERRORS = "modbus_errors"
KEY_LAST_MODBUS_ERROR = "last_modbus_error"
DATA_KEY_POLL_DURATION = "poll_duration_ms"
DATA_KEY_BUS_LOAD = "poll_bus_load"
DATA_KEY_POLL_REQUESTS = "poll_requests"

#: Longest state Home Assistant accepts; a longer message is cut to it.
MAX_STATE_LENGTH = 255

_READS = (
    "read_input_registers",
    "read_holding_registers",
    "read_coils",
    "read_discrete_inputs",
)
_WRITES = (
    "write_coil",
    "write_register",
)


class ErrorLog:
    """The requests that failed since start, and the last of them.

    Two kinds of failure are kept apart. An error is a request that got no
    valid answer: a timeout, a dropped link, a reply that does not belong to
    the request. That is what the log shows as a Modbus error and what the
    Modbus Errors sensor counts. A refusal is an exception response: the unit
    did answer, with "I do not serve that address". The optional reads run
    into those by design on units without those registers (the identity
    registers, an experimental block), so they are counted on their own and
    never become the last error, which would otherwise read like a fault on a
    healthy bus.

    Listeners are called after every recorded failure, so a sensor updates
    even while the polls keep failing, when the coordinator itself does not
    notify its entities again.
    """

    def __init__(
        self,
        refused: tuple[type[BaseException], ...] = (),
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._refused = refused
        self._clock = clock
        self._listeners: list[Callable[[], None]] = []
        #: When counting started (Unix time).
        self.since = clock()
        self.errors = 0
        self.refusals = 0
        #: The last error: error (exception type), message, request, time.
        self.last: dict[str, Any] | None = None

    def record(self, request: str, exc: BaseException) -> None:
        """Write down one failed request and tell the listeners."""
        if isinstance(exc, self._refused):
            self.refusals += 1
        else:
            self.errors += 1
            self.last = {
                "error": type(exc).__name__,
                "message": str(exc) or type(exc).__name__,
                "request": request,
                "time": self._clock(),
            }
        for listener in list(self._listeners):
            listener()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call listener after every failure; returns the function to stop."""
        self._listeners.append(listener)

        def remove() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return remove

    def last_text(self) -> str | None:
        """The last error as a state: '<type>: <message>', cut to fit."""
        if self.last is None:
            return None
        text = f"{self.last['error']}: {self.last['message']}"
        return text[:MAX_STATE_LENGTH]

    def state(self) -> dict[str, Any]:
        """Everything, for the diagnostics download."""
        return {
            "since": self.since,
            "errors": self.errors,
            "refusals": self.refusals,
            "last": self.last,
        }


def _request(name: str, args: tuple[Any, ...]) -> str:
    """How a request shows in Last Modbus Error, e.g. read_coils(0, 6)."""
    return f"{name}({', '.join(str(arg) for arg in args)})"


class CountingUnit:
    """A Modbus unit that counts the reads made through it.

    With an ErrorLog, every read or write that raises is written down there
    before the exception goes on to the caller unchanged. Everything else is
    passed through unchanged, so the coordinator uses it exactly like the
    unit it wraps.
    """

    def __init__(self, unit: Any, errors: ErrorLog | None = None) -> None:
        self._unit = unit
        self._errors = errors
        self.reads = 0

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._unit, name)
        is_read = name in _READS
        if not is_read and name not in _WRITES:
            return attribute

        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            if is_read:
                self.reads += 1
            try:
                return await attribute(*args, **kwargs)
            except Exception as exc:
                if self._errors is not None:
                    self._errors.record(_request(name, args), exc)
                raise

        return wrapped


def stats(duration_s: float, interval_s: float, requests: int) -> dict[str, Any]:
    """Coordinator data for one poll: duration in ms, bus load in %."""
    load = 100.0 * duration_s / interval_s if interval_s > 0 else None
    return {
        DATA_KEY_POLL_DURATION: int(round(duration_s * 1000)),
        DATA_KEY_BUS_LOAD: None if load is None else round(load, 1),
        DATA_KEY_POLL_REQUESTS: requests,
    }
