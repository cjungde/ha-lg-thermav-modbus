"""Taking over the history of the isarrider YAML setup (yaml_takeover.py).

yaml_takeover.py imports nothing from Home Assistant, so none of this needs
an install.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
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


cs = _load("compressor_stats")

yt = _load("yaml_takeover")

# Every entity with a unique_id in modbus_lg_heatpump.yaml (isarrider/
# homeassistant_lg_therma_v_modbus, a37a8af): (platform, unique_id, domain).
YAML_ENTITIES = (
    ("modbus", "modbus.hp_error_code", "sensor"),
    ("modbus", "modbus.hp_odu_operation_cycle", "sensor"),
    ("modbus", "modbus.hp_inlet_temp", "sensor"),
    ("modbus", "modbus.hp_outlet_temp", "sensor"),
    ("modbus", "modbus.hp_backup_heater_outlet_temp", "sensor"),
    ("modbus", "modbus.hp_dhw_water_temp", "sensor"),
    ("modbus", "modbus.hp_solar_collector_temp", "sensor"),
    ("modbus", "modbus.hp_temp_technikraum", "sensor"),
    ("modbus", "modbus.hp_flow_rate", "sensor"),
    ("modbus", "modbus.hp_flow_temp_circle_2", "sensor"),
    ("modbus", "modbus.hp_room_air_temp_circuit2_input", "sensor"),
    ("modbus", "modbus.hp_energy_state_input", "sensor"),
    ("modbus", "modbus.hp_outside_temp", "sensor"),
    ("modbus", "modbus.hp_water_pressure", "sensor"),
    ("modbus", "modbus.hp_temp_liquid_gas", "sensor"),
    ("modbus", "modbus.hp_temp_pipe_out", "sensor"),
    ("modbus", "modbus.hp_temp_suction", "sensor"),
    ("modbus", "modbus.hp_temp_heatgas", "sensor"),
    ("modbus", "modbus.hp_temp_before_vaporiser", "sensor"),
    ("modbus", "modbus.hp_temp_after_vaporiser", "sensor"),
    ("modbus", "modbus.hp_high_pressure", "sensor"),
    ("modbus", "modbus.hp_low_pressure", "sensor"),
    ("modbus", "modbus.hp_compressor_rpm", "sensor"),
    ("modbus", "modbus.hp_ENERGY_INSTANTANEOUS_TOTAL_SYSTEM", "sensor"),
    ("modbus", "modbus.hp_ENERGY_INSTANTANEOUS_TOTAL", "sensor"),
    ("modbus", "modbus.hp_ENERGY_ACCUMULATIVE_TOTAL", "sensor"),
    ("modbus", "modbus.hp_ENERGY_ACCUMULATIVE_HEAT", "sensor"),
    ("modbus", "modbus.hp_ENERGY_ACCUMULATIVE_COOL", "sensor"),
    ("modbus", "modbus.hp_ENERGY_ACCUMULATIVE_DHW", "sensor"),
    ("modbus", "modbus.hp_DvS", "sensor"),
    ("modbus", "modbus.hp_ENERGY_INSTANTANEOUS_TOTAL_TH", "sensor"),
    ("modbus", "modbus.hp_ENERGY_ACCUMULATIVE_HEAT_TH", "sensor"),
    ("modbus", "modbus.hp_product_group", "sensor"),
    ("modbus", "modbus.hp_product_info", "sensor"),
    ("modbus", "modbus.hp_operation_mode", "sensor"),
    ("modbus", "modbus.hp_control_method", "sensor"),
    ("modbus", "modbus.hp_target_temp_circuit1", "sensor"),
    ("modbus", "modbus.hp_room_air_temp_circuit1", "sensor"),
    ("modbus", "modbus.hp_shift_value_in_auto_mode_circuit1", "sensor"),
    ("modbus", "modbus.hp_target_temp_circuit2", "sensor"),
    ("modbus", "modbus.hp_room_air_temp_circuit2", "sensor"),
    ("modbus", "modbus.hp_shift_value_in_auto_mode_circuit2", "sensor"),
    ("modbus", "modbus.hp_dhw_target_temp", "sensor"),
    ("modbus", "modbus.hp_energy_state_input_raw", "sensor"),
    ("modbus", "modbus.hp_compressor_modulation", "sensor"),
    ("modbus", "modbus.hp_power_limitation", "sensor"),
    ("modbus", "modbus.hp_hauptschalter", "switch"),
    ("modbus", "modbus.hp_dhw", "switch"),
    ("modbus", "modbus.hp_silent_mode", "switch"),
    ("modbus", "modbus.hp_dhw_desinfection_mode", "switch"),
    ("modbus", "modbus.hp_emergency_stop_switch_off", "switch"),
    ("modbus", "modbus.hp_emergency_stop_switch_on", "switch"),
    ("modbus", "modbus.hp_active_power_limit", "switch"),
    ("modbus", "modbus.hp_water_flow_status", "binary_sensor"),
    ("modbus", "modbus.hp_water_pump_status", "binary_sensor"),
    ("modbus", "modbus.hp_ext_water_pump_status", "binary_sensor"),
    ("modbus", "modbus.hp_compressor_status", "binary_sensor"),
    ("modbus", "modbus.hp_defrosting_status", "binary_sensor"),
    ("modbus", "modbus.hp_dhw_heating_status", "binary_sensor"),
    ("modbus", "modbus.hp_dhw_tank_desinfection_status", "binary_sensor"),
    ("modbus", "modbus.hp_silent_mode_status", "binary_sensor"),
    ("modbus", "modbus.hp_cooling_status", "binary_sensor"),
    ("modbus", "modbus.hp_solar_pump_status", "binary_sensor"),
    ("modbus", "modbus.hp_backup_heater_step1_status", "binary_sensor"),
    ("modbus", "modbus.hp_backup_heater_step2_status", "binary_sensor"),
    ("modbus", "modbus.hp_dhw_boost_heater_status", "binary_sensor"),
    ("modbus", "modbus.hp_error_status", "binary_sensor"),
    (
        "modbus",
        "modbus.hp_emergency_operation_available_space_heating_cooling",
        "binary_sensor",
    ),
    ("modbus", "modbus.hp_emergency_operation_available_dhw", "binary_sensor"),
    ("modbus", "modbus.hp_mix_pump_status", "binary_sensor"),
    ("template", "hp_energy_state_label", "sensor"),
    ("template", "hp_heating_cop_calculated", "sensor"),
)


def test_every_yaml_entity_is_handled_exactly_once() -> None:
    taken = [(t.platform, t.unique_id, t.domain) for t in yt.TAKEOVERS]
    left = [(x.platform, x.unique_id, x.domain) for x in yt.EXCLUDED]
    assert len(taken) == len(set(taken))
    assert not set(taken) & set(left)
    assert set(taken) | set(left) == set(YAML_ENTITIES)


def test_no_two_yaml_entities_continue_in_one() -> None:
    targets = [t.target_entity_id() for t in yt.TAKEOVERS]
    assert len(targets) == len(set(targets))


def test_targets_keep_the_domain() -> None:
    """The registry cannot move an entity id to another entity type."""
    for takeover in yt.TAKEOVERS:
        assert takeover.target_entity_id().split(".")[0] == takeover.domain


def _entries(*items):
    return [(p, u, d, f"{d}.{u.removeprefix('modbus.')}") for p, u, d in items]


def test_plan_finds_orphans_and_skips_live_and_taken() -> None:
    entries = _entries(
        ("modbus", "modbus.hp_inlet_temp", "sensor"),
        ("modbus", "modbus.hp_outlet_temp", "sensor"),
        ("modbus", "modbus.hp_outside_temp", "sensor"),
        ("modbus", "modbus.hp_temp_liquid_gas", "sensor"),
        ("modbus", "modbus.something_else", "sensor"),
    )
    found, left = yt.plan(
        entries,
        live_entity_ids={"sensor.hp_outlet_temp"},
        taken_entity_ids={"sensor.lg_thermav_r290_outdoor_temperature"},
    )
    assert [(f.old_entity_id, f.new_entity_id) for f in found] == [
        ("sensor.hp_inlet_temp", "sensor.lg_thermav_r290_inlet_temperature")
    ]
    assert sorted(left) == [
        ("sensor.hp_outlet_temp", "still_loaded"),
        ("sensor.hp_outside_temp", "target_taken"),
        ("sensor.hp_temp_liquid_gas", "scale"),
    ]


def test_plan_without_yaml_entities_finds_nothing() -> None:
    assert yt.plan([], set(), set()) == ([], [])
