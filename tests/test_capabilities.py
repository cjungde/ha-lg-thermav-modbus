"""The rules that decide whether an optional register gets an entity.

Three addresses from the manual are served by some units and not by others,
and an unserved one is not refused but left unanswered. Each probe therefore
costs a full request timeout, so the answer is remembered -- and a remembered
`False` that is wrong hides a feature forever. The rules below are what keeps
that from happening, so they are what these tests pin down.

No Home Assistant install is needed: capabilities.py imports it only inside
`CapabilityStore`, which is not touched here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

COMPONENT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "lg_thermav_r290"
)


def _load(module_name: str):
    package = "lg_thermav_r290_under_test"
    if package not in sys.modules:
        stub = types.ModuleType(package)
        stub.__path__ = [str(COMPONENT)]
        sys.modules[package] = stub

    qualified = f"{package}.{module_name}"
    if qualified not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            qualified, COMPONENT / f"{module_name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
    return sys.modules[qualified]


capabilities = _load("capabilities")
const = _load("const")

IDENTITY = {"device_group": 0, "product_info": 8208}
FINGERPRINT = capabilities.definitions_fingerprint()


def _record(support: dict, *, fingerprint: str = FINGERPRINT, identity=IDENTITY):
    return {"fingerprint": fingerprint, "identity": dict(identity), "support": support}


# --- what the integration asks about ------------------------------------


def test_the_three_optional_addresses_are_the_measured_ones() -> None:
    """Holding 23, holding 24 and coil 6, measured silent here on 2026-10-17."""
    assert {(r.kind, r.address) for r in capabilities.OPTIONAL_REGISTERS} == {
        ("holding", 23),
        ("holding", 24),
        ("coil", 6),
    }


def test_each_feature_is_probed_on_its_own() -> None:
    """Holding 23 and 24 are neighbours, but a unit may serve only one.

    A block read spanning both would be dropped as a whole by such a unit, and
    the HM071HF UB40 is reported to be one: its manual lists 40025 but not
    40024.
    """
    assert all(r.probe_count == 1 for r in capabilities.OPTIONAL_REGISTERS)


def test_every_optional_address_is_writable() -> None:
    """A limit that cannot be set is not a feature.

    The guard in const.py refuses any other address before it reaches the bus.
    """
    for register in capabilities.OPTIONAL_REGISTERS:
        if register.kind == "coil":
            assert register.address in const.WRITABLE_COILS
        else:
            assert register.address in const.WRITABLE_HOLDING_REGISTERS


def test_coil_5_stays_unwritable() -> None:
    """Emergency operation is a documented omission, not an oversight."""
    assert 5 not in const.WRITABLE_COILS
    assert all(
        not (r.kind == "coil" and r.address == 5)
        for r in capabilities.OPTIONAL_REGISTERS
    )


def test_no_optional_address_collides_with_a_documented_register() -> None:
    """The manual's own registers are read in bulk and must stay untouched."""
    documented_holding = set(range(0, 10))
    documented_coils = set(range(0, 6))
    for register in capabilities.OPTIONAL_REGISTERS:
        if register.kind == "coil":
            assert register.address not in documented_coils
        else:
            assert register.address not in documented_holding


# --- what may be believed from storage ----------------------------------


def test_a_full_record_is_believed() -> None:
    support = {"power_limit": True, "compressor_modulation_limit": False}
    result, reason = capabilities.restore(_record(support), FINGERPRINT, IDENTITY)
    assert reason == "hit"
    assert result == support


def test_nothing_is_believed_without_a_record() -> None:
    assert capabilities.restore(None, FINGERPRINT, IDENTITY) == ({}, "miss")
    assert capabilities.restore({}, FINGERPRINT, IDENTITY) == ({}, "miss")


def test_changed_definitions_void_the_record() -> None:
    """Stored answers belong to the questions asked at the time."""
    record = _record({"power_limit": True}, fingerprint="0000000000000000")
    assert capabilities.restore(record, FINGERPRINT, IDENTITY) == (
        {},
        "definitions_changed",
    )


def test_a_different_device_voids_the_record() -> None:
    """The entry was moved to another machine; its answers do not travel."""
    record = _record({"power_limit": True}, identity={"device_group": 1})
    assert capabilities.restore(record, FINGERPRINT, IDENTITY) == (
        {},
        "identity_changed",
    )


def test_without_a_known_identity_only_positives_survive() -> None:
    """The core safeguard: an unconfirmed `False` is dropped, not kept.

    Registers 9997/9998 are optional themselves, so some units never say what
    they are. A stored `False` then rests on a silence observed on hardware we
    cannot confirm is the same one -- and re-probing costs one timeout once,
    while a wrong `False` hides the feature for good.
    """
    support = {"power_limit": True, "compressor_modulation_limit": False}
    result, reason = capabilities.restore(_record(support), FINGERPRINT, {})
    assert reason == "positive_only"
    assert result == {"power_limit": True}


def test_a_record_without_identity_is_also_trusted_for_positives_only() -> None:
    """Same the other way round: the device says who it is, the record did not."""
    support = {"power_limit": True, "power_limit_enable": False}
    result, reason = capabilities.restore(
        _record(support, identity={}), FINGERPRINT, IDENTITY
    )
    assert reason == "positive_only"
    assert result == {"power_limit": True}


@pytest.mark.parametrize(
    "support",
    [
        {"power_limit": "yes"},
        {"power_limit": 1},
        {"power_limit": None},
        {"unknown_feature": True},
    ],
)
def test_junk_in_the_record_is_dropped_not_interpreted(support) -> None:
    result, reason = capabilities.restore(_record(support), FINGERPRINT, IDENTITY)
    assert reason == "hit"
    assert result == {}


def test_a_malformed_record_is_rejected() -> None:
    assert capabilities.restore(
        {"fingerprint": FINGERPRINT, "identity": IDENTITY, "support": "no"},
        FINGERPRINT,
        IDENTITY,
    ) == ({}, "invalid")
    assert capabilities.restore(
        {"fingerprint": FINGERPRINT, "identity": "no", "support": {}},
        FINGERPRINT,
        IDENTITY,
    ) == ({}, "invalid")


# --- what still has to be asked -----------------------------------------


def test_everything_is_pending_when_nothing_is_known() -> None:
    assert capabilities.pending_probes({}) == capabilities.OPTIONAL_REGISTERS


def test_a_known_negative_is_not_asked_again() -> None:
    """This is what makes the 20-second timeout a one-off cost."""
    known = {r.key: False for r in capabilities.OPTIONAL_REGISTERS}
    assert capabilities.pending_probes(known) == ()


def test_only_the_unknown_rest_is_asked() -> None:
    pending = capabilities.pending_probes({"power_limit": True})
    assert [r.key for r in pending] == [
        "compressor_modulation_limit",
        "power_limit_enable",
    ]


# --- keys -----------------------------------------------------------------


def test_the_device_key_separates_slaves_on_one_gateway() -> None:
    """Two units behind one RS485 gateway differ only in the slave id."""
    a = capabilities.device_key("192.168.0.10", 502, 33)
    b = capabilities.device_key("192.168.0.10", 502, 1)
    assert a != b
    assert a == capabilities.device_key("192.168.0.10", 502, 33)


def test_the_fingerprint_follows_the_definitions() -> None:
    first = capabilities.definitions_fingerprint()
    original = capabilities.OPTIONAL_REGISTERS
    try:
        capabilities.OPTIONAL_REGISTERS = original[:-1]
        assert capabilities.definitions_fingerprint() != first
    finally:
        capabilities.OPTIONAL_REGISTERS = original
    assert capabilities.definitions_fingerprint() == first


def test_identity_leaves_out_what_the_device_did_not_say() -> None:
    assert capabilities.identity_of(None, None) == {}
    assert capabilities.identity_of(0, None) == {"device_group": 0}
    assert capabilities.identity_of(0, 8208) == IDENTITY
