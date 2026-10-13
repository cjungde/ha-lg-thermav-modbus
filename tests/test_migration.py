"""Unique id renames for installations set up before 1.3.0 (migration.py).

migration.py imports nothing from Home Assistant, so no install is needed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
import types

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


migration = _load("migration")
energy = _load("energy")
experimental = _load("experimental")
cop = _load("cop")
limits = _load("limits")

ENTRY = "01JABCDEF"


def _slug(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


def test_renames_an_old_id() -> None:
    assert (
        migration.renamed_unique_id("sensor", f"{ENTRY}_inlet_temp", ENTRY)
        == f"{ENTRY}_inlet_temperature"
    )
    assert (
        migration.renamed_unique_id("switch", f"{ENTRY}_hauptschalter", ENTRY)
        == f"{ENTRY}_heat_pump"
    )
    assert (
        migration.renamed_unique_id("button", f"{ENTRY}_dhw_desinfection_start", ENTRY)
        == f"{ENTRY}_start_disinfection"
    )


def test_the_platform_decides() -> None:
    """silent_mode exists as switch and binary sensor; only di_ is renamed."""
    assert (
        migration.renamed_unique_id("binary_sensor", f"{ENTRY}_di_silent_mode", ENTRY)
        == f"{ENTRY}_silent_mode"
    )
    assert migration.renamed_unique_id("switch", f"{ENTRY}_silent_mode", ENTRY) is None


def test_unchanged_and_new_ids_are_left_alone() -> None:
    assert migration.renamed_unique_id("sensor", f"{ENTRY}_flow_rate", ENTRY) is None
    # Already migrated: running the migration twice changes nothing.
    assert (
        migration.renamed_unique_id("sensor", f"{ENTRY}_inlet_temperature", ENTRY)
        is None
    )


def test_ids_of_another_entry_are_left_alone() -> None:
    assert migration.renamed_unique_id("sensor", "OTHER_inlet_temp", ENTRY) is None


def test_old_and_new_keys_never_overlap_per_platform() -> None:
    """A new key that is also an old key would be renamed a second time."""
    for table in migration.UNIQUE_KEY_RENAMES.values():
        assert not set(table) & set(table.values())
        assert len(set(table.values())) == len(table)


def test_every_new_key_is_a_name_slug() -> None:
    """docs/naming.md: key = name slug. Checked here for the HA-free modules."""
    names = {r.key: r.name for r in energy.ENERGY_REGISTERS}
    names |= {r.key: r.name for r in experimental.EXPERIMENTAL_REGISTERS}
    names[limits.KEY_MAX_COMPRESSOR_MODULATION] = "Max Compressor Modulation"
    for key, name in names.items():
        assert key == _slug(name)


def test_optional_groups_are_all_migrated() -> None:
    sensor = set(migration.UNIQUE_KEY_RENAMES["sensor"].values())
    assert {r.key for r in energy.ENERGY_REGISTERS} <= sensor
    assert {r.key for r in experimental.EXPERIMENTAL_REGISTERS} <= sensor
    assert set(cop.COP_KEYS) <= sensor
    assert (
        limits.KEY_MAX_COMPRESSOR_MODULATION
        in migration.UNIQUE_KEY_RENAMES["number"].values()
    )


def test_experimental_ids_map_by_address() -> None:
    sensor = migration.UNIQUE_KEY_RENAMES["sensor"]
    assert sensor["exp_input_14"] == "experimental_input_30015"
    assert sensor["exp_holding_10"] == "experimental_holding_40011"
    assert sensor["exp_holding_63"] == "experimental_holding_40064"


def test_energy_state_binary_sensors_map_by_value() -> None:
    binary = migration.UNIQUE_KEY_RENAMES["binary_sensor"]
    assert binary["energy_state_0"] == "energy_state_not_used"
    assert binary["energy_state_2"] == "energy_state_normal_operation"
    assert binary["energy_state_8"] == "energy_state_super_energy_saving_mode"


def test_migration_size() -> None:
    """94 renamed ids; 9 kept theirs (flow rate, water pressure, error code,
    device group, both selects, three switches)."""
    assert sum(len(t) for t in migration.UNIQUE_KEY_RENAMES.values()) == 94


def test_steps_are_in_order_and_end_at_the_current_version() -> None:
    versions = [minor for minor, _ in migration.MIGRATION_STEPS]
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)
    assert migration.UNIQUE_ID_MINOR_VERSION == versions[-1] == 3


def test_coil_0_is_renamed_from_every_earlier_version() -> None:
    """hauptschalter (before 1.3.0) and heat_pump (1.3.0) both end up here."""
    for old, from_minor in (("hauptschalter", 1), ("heat_pump", 2)):
        assert (
            migration.migrated_unique_id("switch", f"{ENTRY}_{old}", ENTRY, from_minor)
            == f"{ENTRY}_heating_cooling"
        )


def test_an_entry_on_1_3_runs_only_the_new_step() -> None:
    """Already-migrated ids stay; only heat_pump moves."""
    assert (
        migration.migrated_unique_id("sensor", f"{ENTRY}_inlet_temperature", ENTRY, 2)
        == f"{ENTRY}_inlet_temperature"
    )
    # An id renamed in step 2 is not renamed again by step 2 when starting at 2.
    assert (
        migration.migrated_unique_id("switch", f"{ENTRY}_hauptschalter", ENTRY, 2)
        == f"{ENTRY}_hauptschalter"
    )


def test_a_current_entry_runs_no_step() -> None:
    assert (
        migration.migrated_unique_id("switch", f"{ENTRY}_heating_cooling", ENTRY, 3)
        == f"{ENTRY}_heating_cooling"
    )


def test_heat_pump_only_renamed_on_the_switch_platform() -> None:
    """electrical_power_heat_pump and friends are sensors; untouched."""
    assert (
        migration.migrated_unique_id(
            "sensor", f"{ENTRY}_electrical_power_heat_pump", ENTRY, 2
        )
        == f"{ENTRY}_electrical_power_heat_pump"
    )


def test_no_step_renames_onto_a_key_another_step_starts_from() -> None:
    """Within each step, old and new keys never overlap per platform."""
    for _, renames in migration.MIGRATION_STEPS:
        for table in renames.values():
            assert not set(table) & set(table.values())
