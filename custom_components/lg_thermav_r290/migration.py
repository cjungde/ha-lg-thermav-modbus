"""Unique id renames, applied once to existing installations.

Up to 1.2.0 the unique ids grew one by one: abbreviations (``inlet_temp``),
German (``hauptschalter``), typos (``dhw_desinfection_start``,
``flow_temp_circle_2``, ``temp_before_vaporiser``) and prefixes that no
longer said anything (``energy_reg_``, ``exp_``, ``di_``). From 1.3.0 every
unique id is ``<config entry id>_<key>``, and every key is the entity's name
as Home Assistant slugifies it into an entity id (see docs/naming.md).

Renaming a unique id on its own would orphan the old entity and create a new
one, losing history and breaking automations. The config entry migration in
__init__.py therefore rewrites the registry entries in place, using the table
below: the entity id, history, statistics and every automation stay as they
are, only the unique id behind them changes.

Deliberately free of Home Assistant imports so the table can be tested
without a Home Assistant install, like energy.py.
"""

from __future__ import annotations

from .experimental import EXPERIMENTAL_REGISTERS

_ENERGY_STATE_NAMES = (
    "not_used",
    "forced_off",
    "normal_operation",
    "on_recommendation",
    "on_command",
    "on_command_step_2",
    "on_recommendation_step_1",
    "energy_saving_mode",
    "super_energy_saving_mode",
)

# Old key -> new key, per entity platform. Keys that did not change are not
# listed (flow_rate, water_pressure, error_code, device_group, operation_mode
# and control_method selects, the dhw / silent_mode / emergency_stop switches).
UNIQUE_KEY_RENAMES: dict[str, dict[str, str]] = {
    "sensor": {
        # Input registers
        "inlet_temp": "inlet_temperature",
        "outlet_temp": "outlet_temperature",
        "backup_heater_outlet_temp": "backup_heater_outlet_temperature",
        "dhw_water_temp": "dhw_temperature",
        "solar_collector_temp": "solar_collector_temperature",
        "room_air_temp_circuit1": "room_air_temperature_circuit_1",
        "flow_temp_circle_2": "flow_temperature_circuit_2",
        "room_air_temp_circuit2_in": "room_air_temperature_circuit_2",
        "energy_state_input": "energy_control_signal",
        "outside_temp": "outdoor_temperature",
        "temp_liquid_gas": "liquid_gas_temperature",
        "temp_suction": "suction_temperature",
        "temp_heatgas": "hot_gas_temperature",
        "temp_before_vaporiser": "temperature_before_evaporator",
        "temp_after_vaporiser": "temperature_after_evaporator",
        "high_pressure": "high_pressure_condenser",
        "low_pressure": "low_pressure_evaporator",
        "compressor_rpm": "compressor_speed",
        "odu_operation_cycle": "operation_cycle_odu",
        "product_info": "product_information",
        # Holding register read-backs
        "room_air_temp_circuit1_hold": "room_air_temperature_circuit_1_holding",
        "room_air_temp_circuit2_hold": "room_air_temperature_circuit_2_holding",
        # Labels
        "operation_mode_label": "operation_mode",
        "control_method_label": "control_method",
        "energy_state_label": "energy_state",
        "energy_state_reported_label": "energy_state_reported",
        # Calculated thermal power
        "thermal_power_total": "thermal_power_calculated",
        "thermal_power_heating_circuit": "thermal_power_heating_circuit_calculated",
        "thermal_power_dhw": "thermal_power_dhw_calculated",
        # Energy registers (option)
        "energy_reg_power_total_system": "electrical_power_total_system",
        "energy_reg_power_heat_pump": "electrical_power_heat_pump",
        "energy_reg_energy_total": "electrical_energy_total",
        "energy_reg_energy_heating": "electrical_energy_space_heating",
        "energy_reg_energy_cooling": "electrical_energy_space_cooling",
        "energy_reg_energy_dhw": "electrical_energy_dhw",
        "energy_reg_demand_vs_supply": "demand_vs_supply",
        "energy_reg_thermal_power": "thermal_power_reported",
        "energy_reg_thermal_energy_heating": "thermal_energy_space_heating",
        # COP sensors (option)
        "energy_reg_heating_cop": "cop_heating_cumulative",
        "energy_reg_cop_current": "cop_reported",
        "energy_reg_cop_system": "cop_system_reported",
        "energy_reg_cop_calculated": "cop_calculated",
        # Experimental registers (option): exp_<kind>_<address> -> name slug
        **{
            f"exp_{register.kind}_{register.address}": register.key
            for register in EXPERIMENTAL_REGISTERS
        },
    },
    "binary_sensor": {
        "di_water_flow": "water_flow",
        "di_water_pump": "water_pump",
        "di_ext_water_pump": "external_water_pump",
        "di_compressor": "compressor",
        "di_defrosting": "defrost",
        "di_dhw_heating": "dhw_heating",
        "di_dhw_tank_desinfection": "dhw_disinfection",
        "di_silent_mode": "silent_mode",
        "di_cooling": "cooling_active",
        "di_solar_pump": "solar_pump",
        "di_backup_heater_step1": "backup_heater_step_1",
        "di_backup_heater_step2": "backup_heater_step_2",
        "di_dhw_boost_heater": "dhw_boost_heater",
        "di_error": "fault",
        "di_emergency_heating_cooling": "emergency_heating_cooling_available",
        "di_emergency_dhw": "emergency_dhw_available",
        "di_mix_pump": "mixing_pump",
        **{
            f"energy_state_{value}": f"energy_state_{name}"
            for value, name in enumerate(_ENERGY_STATE_NAMES)
        },
    },
    "switch": {
        "hauptschalter": "heat_pump",
    },
    "button": {
        "dhw_desinfection_start": "start_disinfection",
    },
    "number": {
        "target_temp_circuit1": "target_temperature_circuit_1_radiators",
        "target_temp_circuit2": "target_temperature_circuit_2_underfloor",
        "dhw_target_temp": "dhw_target_temperature",
        "shift_value_circuit1": "setpoint_shift_circuit_1",
        "shift_value_circuit2": "setpoint_shift_circuit_2",
        "compressor_modulation_limit": "max_compressor_modulation",
    },
}


# Coil 0 (00001) is "Aktivieren / Deaktivieren (Heizung / Kühlung)" in the
# manual: it switches space heating/cooling, not the whole heat pump (DHW has
# its own coil 1). Its switch is renamed from "Heat Pump" to "Heating/Cooling".
HEATING_COOLING_RENAMES: dict[str, dict[str, str]] = {
    "switch": {"heat_pump": "heating_cooling"},
}

# The steps, in order: (config entry minor version reached, renames). An entry
# runs every step above its minor version, one after the other, so one set up
# before 1.3.0 goes hauptschalter -> heat_pump -> heating_cooling.
MIGRATION_STEPS: tuple[tuple[int, dict[str, dict[str, str]]], ...] = (
    (2, UNIQUE_KEY_RENAMES),
    (3, HEATING_COOLING_RENAMES),
)

# Config entry minor version that carries the current unique ids. Entries below
# it are migrated on setup, then bumped to it; new entries start at it.
UNIQUE_ID_MINOR_VERSION = MIGRATION_STEPS[-1][0]


def renamed_unique_id(
    domain: str,
    unique_id: str,
    entry_id: str,
    renames: dict[str, dict[str, str]] = UNIQUE_KEY_RENAMES,
) -> str | None:
    """New unique id for an old one in one step, or None if it keeps its id.

    Only ids of this config entry (``<entry_id>_<key>``) are touched.
    """
    prefix = f"{entry_id}_"
    if not unique_id.startswith(prefix):
        return None
    new_key = renames.get(domain, {}).get(unique_id[len(prefix) :])
    if new_key is None:
        return None
    return f"{prefix}{new_key}"


def migrated_unique_id(
    domain: str, unique_id: str, entry_id: str, from_minor_version: int
) -> str:
    """The unique id after every step an entry at this minor version runs."""
    for minor_version, renames in MIGRATION_STEPS:
        if from_minor_version < minor_version:
            unique_id = (
                renamed_unique_id(domain, unique_id, entry_id, renames) or unique_id
            )
    return unique_id
