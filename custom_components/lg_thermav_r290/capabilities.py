"""Registers that only some units serve, and a memory of which ones they are.

Three addresses from the manual are not served by every unit. Measured on a
HN1639HC NK0 (9 kW) on 2026-10-03 and again on 2026-10-17: holding 23, holding
24 and coil 6 all stay silent, while holding 22 and coil 5 answer in the same
second. Other units differ -- a 12 kW unit serves holding 23, and the manual of
an HM071HF UB40 lists coil 6 and holding 24 but not holding 23. No two of the
three known units agree, so the only way to get this right is to ask the device
and remember the answer.

WHY THE ANSWER MUST BE REMEMBERED: an address this device does not serve is not
refused, it is *not answered at all*. Every probe therefore costs a full
request timeout, and this integration raises that timeout to 20 s because it
shares its connection (see `coordinator._REQUEST_TIMEOUT`). Probing on every
poll would stall the bus for everyone on it; probing once per installation
costs one timeout per absent feature, ever.

WHY A NEGATIVE NEEDS A WITNESS: a timeout means "not served" only if the link
was demonstrably alive at that moment. A dead gateway times out exactly the
same way. Probes therefore run only right after a complete, successful poll of
the mandatory blocks -- that poll is the witness. Without it a broken cable
would be remembered as missing hardware.

Deliberately free of Home Assistant imports except inside `CapabilityStore`,
so the decision rules can be tested without a Home Assistant install, like
connection.py and experimental.py.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import time
from typing import Any

_LOGGER = logging.getLogger(__name__)

#: Cache generation. Raise it to discard every stored record on upgrade.
STORE_VERSION = 1


@dataclass(frozen=True)
class OptionalRegister:
    """One feature the device may or may not serve.

    `kind` is the register space, `address` the address inside it, and
    `probe_count` how many registers one probe asks for. Each feature is probed
    on its own: holding 23 and 24 are neighbours, but a block read covering
    both would be dropped as a whole by a device that serves only one of them,
    and at least one such device exists.
    """

    key: str
    kind: str
    address: int
    probe_count: int = 1
    description: str = ""


OPTIONAL_REGISTERS: tuple[OptionalRegister, ...] = (
    OptionalRegister(
        key="compressor_modulation_limit",
        kind="holding",
        address=23,
        description="40024, max compressor modulation 40-100 %, 0 = not used",
    ),
    OptionalRegister(
        key="power_limit",
        kind="holding",
        address=24,
        description="40025, active power limit 0.1-25.0 kW",
    ),
    OptionalRegister(
        key="power_limit_enable",
        kind="coil",
        address=6,
        description="00007, 1 = limit power according to 40025",
    ),
)

OPTIONAL_KEYS: frozenset[str] = frozenset(reg.key for reg in OPTIONAL_REGISTERS)


def definitions_fingerprint() -> str:
    """Hash over what this module claims the optional registers are.

    A stored record describes the questions asked at the time. Change an
    address or add a feature and the old answers no longer line up with the new
    questions, so the record is void rather than reinterpreted.
    """
    payload = [
        [reg.key, reg.kind, reg.address, reg.probe_count] for reg in OPTIONAL_REGISTERS
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def device_key(host: str, port: int, slave_id: int) -> str:
    """Identify the physical unit, independently of its display name.

    Two entries on one RS485 gateway differ only in the slave id, and a unit
    renamed in the UI is still the same machine.
    """
    binding = [str(host), int(port), int(slave_id)]
    return hashlib.sha256(json.dumps(binding).encode()).hexdigest()[:16]


def identity_of(device_group: int | None, product_info: int | None) -> dict[str, int]:
    """The device's own account of what it is, as far as it tells us.

    Input 9997/9998 are optional themselves. A unit that does not serve them
    leaves this empty, which is not an error -- it only means negatives cannot
    be trusted across restarts (see `restore`).
    """
    identity: dict[str, int] = {}
    if device_group is not None:
        identity["device_group"] = int(device_group)
    if product_info is not None:
        identity["product_info"] = int(product_info)
    return identity


def restore(
    record: dict[str, Any] | None,
    fingerprint: str,
    identity: dict[str, int],
) -> tuple[dict[str, bool], str]:
    """Turn a stored record into what we may believe about this device now.

    Returns the support map and the reason it came out that way, which the
    caller logs. The rules, in order:

    * no record, or not a record -> believe nothing (`miss`)
    * the questions changed -> believe nothing (`definitions_changed`)
    * the device says it is a different one -> believe nothing
      (`identity_changed`)
    * the device does not say what it is -> believe only the positives
      (`positive_only`). A `False` would then rest on a timeout observed on
      hardware we cannot confirm is the same, and re-probing costs one timeout
      once, while a wrong `False` hides a feature forever.
    * otherwise -> believe all of it (`hit`)
    """
    if not isinstance(record, dict) or not record:
        return {}, "miss"
    if record.get("fingerprint") != fingerprint:
        return {}, "definitions_changed"

    stored_identity = record.get("identity")
    if not isinstance(stored_identity, dict):
        return {}, "invalid"

    support = record.get("support")
    if not isinstance(support, dict):
        return {}, "invalid"

    clean = {
        key: value
        for key, value in support.items()
        if key in OPTIONAL_KEYS and type(value) is bool
    }

    if identity and stored_identity and identity != stored_identity:
        return {}, "identity_changed"
    if not identity or not stored_identity:
        return {key: True for key, value in clean.items() if value}, "positive_only"
    return clean, "hit"


def pending_probes(support: dict[str, bool]) -> tuple[OptionalRegister, ...]:
    """The features whose presence is still unknown."""
    return tuple(reg for reg in OPTIONAL_REGISTERS if reg.key not in support)


def register_for(key: str) -> OptionalRegister:
    for reg in OPTIONAL_REGISTERS:
        if reg.key == key:
            return reg
    raise KeyError(key)


class CapabilityStore:
    """What this device served, kept across restarts in Home Assistant storage.

    One file per config entry, keyed inside by the physical unit, so moving an
    entry to another slave id does not inherit the wrong answers.
    """

    def __init__(self, hass, entry_id: str, *, store=None) -> None:
        if store is None:
            from homeassistant.helpers.storage import Store

            store = Store(
                hass,
                STORE_VERSION,
                f"{entry_id}.lg_thermav_r290_capabilities",
                private=True,
                atomic_writes=True,
            )
        self._store = store
        self._devices: dict[str, dict[str, Any]] = {}
        self.last_error: str | None = None

    async def async_load(self) -> None:
        """Read the file. A cache must never stop the device being asked."""
        try:
            data = await self._store.async_load()
        except Exception as ex:  # noqa: BLE001 - any failure falls back to probing
            self.last_error = type(ex).__name__
            _LOGGER.warning(
                "Cannot read the capability cache (%s); the optional registers "
                "will be probed again",
                self.last_error,
            )
            return
        if isinstance(data, dict) and isinstance(data.get("devices"), dict):
            self._devices = {
                key: value
                for key, value in data["devices"].items()
                if isinstance(value, dict)
            }

    def restore(
        self, key: str, fingerprint: str, identity: dict[str, int]
    ) -> tuple[dict[str, bool], str]:
        return restore(self._devices.get(key), fingerprint, identity)

    async def async_update(
        self,
        key: str,
        fingerprint: str,
        identity: dict[str, int],
        support: dict[str, bool],
    ) -> None:
        """Write the record, unless it says exactly what the file already says."""
        record = {
            "fingerprint": fingerprint,
            "identity": dict(identity),
            "support": {k: bool(v) for k, v in support.items() if k in OPTIONAL_KEYS},
        }
        previous = self._devices.get(key, {})
        if all(previous.get(field) == value for field, value in record.items()):
            return
        record["saved_at"] = time.time()
        self._devices[key] = record
        try:
            await self._store.async_save({"devices": dict(self._devices)})
            self.last_error = None
        except Exception as ex:  # noqa: BLE001 - losing the cache costs a probe
            self.last_error = type(ex).__name__
            _LOGGER.warning("Cannot write the capability cache (%s)", self.last_error)
