"""Take over the history of the isarrider YAML setup at the first setup.

The YAML package (homeassistant_lg_therma_v_modbus, modbus_lg_heatpump.yaml)
gave its entities unique ids, so after the package is removed they stay in the
entity registry as orphans, and their history and long-term statistics stay
in the database. Home Assistant's recorder moves both along when an entity id
is renamed in the registry. So, before the integration creates its entities,
each orphaned YAML entity with a counterpart is

1. renamed to the integration's entity id (the recorder moves its history and
   statistics to that id), then
2. removed from the registry (its history stays),

and the integration's entity then registers under exactly that id and
continues the old history. Entity ids stay the integration's English ones.

Only entities whose value means the same thing are taken over. The others are
listed with the reason, and left alone.

Deliberately free of Home Assistant imports so the mapping can be tested
without a Home Assistant install, like migration.py.
"""

from __future__ import annotations

from dataclasses import dataclass

# Reasons an entity is not taken over (keys of the texts in strings.json).
SCALE = "scale"
NOT_A_TEMPERATURE = "not_a_temperature"
UNIT = "unit"
TEXT = "text"
OTHER_TYPE = "other_type"

# Unit notes: the history continues, but Home Assistant asks once under
# Developer tools -> Statistics to confirm the new unit (same values).
UNIT_SPELLING = "unit_spelling"


@dataclass(frozen=True)
class Takeover:
    """A YAML entity and the integration entity that continues its history."""

    platform: str  # registry platform of the YAML entity: modbus or template
    unique_id: str
    domain: str
    key: str  # the integration entity's key (docs/naming.md)
    note: str | None = None

    def target_entity_id(self, prefix: str) -> str:
        """The integration's entity id; prefix is the device name as an id."""
        return f"{self.domain}.{prefix}_{self.key}"


@dataclass(frozen=True)
class Excluded:
    """A YAML entity whose history is not taken over, and why."""

    platform: str
    unique_id: str
    domain: str
    reason: str


def _m(unique_id: str, domain: str, key: str, note: str | None = None) -> Takeover:
    return Takeover("modbus", f"modbus.{unique_id}", domain, key, note)


def _x(unique_id: str, domain: str, reason: str) -> Excluded:
    return Excluded("modbus", f"modbus.{unique_id}", domain, reason)


TAKEOVERS: tuple[Takeover, ...] = (
    # Input registers
    _m("hp_error_code", "sensor", "error_code"),
    _m("hp_odu_operation_cycle", "sensor", "operation_cycle_odu"),
    _m("hp_inlet_temp", "sensor", "inlet_temperature"),
    _m("hp_outlet_temp", "sensor", "outlet_temperature"),
    _m("hp_backup_heater_outlet_temp", "sensor", "backup_heater_outlet_temperature"),
    _m("hp_dhw_water_temp", "sensor", "dhw_temperature"),
    _m("hp_solar_collector_temp", "sensor", "solar_collector_temperature"),
    _m("hp_temp_technikraum", "sensor", "room_air_temperature_circuit_1"),
    _m("hp_flow_rate", "sensor", "flow_rate"),
    _m("hp_flow_temp_circle_2", "sensor", "flow_temperature_circuit_2"),
    _m("hp_room_air_temp_circuit2_input", "sensor", "room_air_temperature_circuit_2"),
    _m("hp_energy_state_input", "sensor", "energy_control_signal"),
    _m("hp_outside_temp", "sensor", "outdoor_temperature"),
    _m("hp_water_pressure", "sensor", "water_pressure"),
    _m("hp_temp_suction", "sensor", "suction_temperature"),
    _m("hp_temp_heatgas", "sensor", "hot_gas_temperature"),
    _m("hp_temp_before_vaporiser", "sensor", "temperature_before_evaporator"),
    _m("hp_temp_after_vaporiser", "sensor", "temperature_after_evaporator"),
    _m("hp_high_pressure", "sensor", "high_pressure_condenser"),
    _m("hp_low_pressure", "sensor", "low_pressure_evaporator"),
    _m("hp_compressor_rpm", "sensor", "compressor_speed", UNIT_SPELLING),
    _m("hp_product_group", "sensor", "device_group"),
    _m("hp_product_info", "sensor", "product_information"),
    # Energy registers (shown with the Energy registers option). The counters
    # were in Wh, the integration shows kWh: the recorder converts, since
    # both are energy units.
    _m(
        "hp_ENERGY_INSTANTANEOUS_TOTAL_SYSTEM",
        "sensor",
        "electrical_power_total_system",
    ),
    _m("hp_ENERGY_INSTANTANEOUS_TOTAL", "sensor", "electrical_power_heat_pump"),
    _m("hp_ENERGY_ACCUMULATIVE_TOTAL", "sensor", "electrical_energy_total"),
    _m("hp_ENERGY_ACCUMULATIVE_HEAT", "sensor", "electrical_energy_space_heating"),
    _m("hp_ENERGY_ACCUMULATIVE_COOL", "sensor", "electrical_energy_space_cooling"),
    _m("hp_ENERGY_ACCUMULATIVE_DHW", "sensor", "electrical_energy_dhw"),
    _m("hp_ENERGY_INSTANTANEOUS_TOTAL_TH", "sensor", "thermal_power_reported"),
    _m("hp_ENERGY_ACCUMULATIVE_HEAT_TH", "sensor", "thermal_energy_space_heating"),
    # Holding registers read as sensors in both
    _m("hp_room_air_temp_circuit1", "sensor", "target_room_air_temperature_circuit_1"),
    _m("hp_room_air_temp_circuit2", "sensor", "target_room_air_temperature_circuit_2"),
    # Coils holding a state
    _m("hp_hauptschalter", "switch", "heating_cooling"),
    _m("hp_dhw", "switch", "dhw"),
    _m("hp_silent_mode", "switch", "silent_mode"),
    _m("hp_emergency_stop_switch_off", "switch", "emergency_stop"),
    _m("hp_active_power_limit", "switch", "power_limit"),
    # Discrete inputs (the same raw bits in both)
    _m("hp_water_flow_status", "binary_sensor", "water_flow"),
    _m("hp_water_pump_status", "binary_sensor", "water_pump"),
    _m("hp_ext_water_pump_status", "binary_sensor", "external_water_pump"),
    _m("hp_compressor_status", "binary_sensor", "compressor"),
    _m("hp_defrosting_status", "binary_sensor", "defrost"),
    _m("hp_dhw_heating_status", "binary_sensor", "dhw_heating"),
    _m("hp_dhw_tank_desinfection_status", "binary_sensor", "dhw_disinfection"),
    _m("hp_silent_mode_status", "binary_sensor", "silent_mode"),
    _m("hp_cooling_status", "binary_sensor", "cooling_active"),
    _m("hp_solar_pump_status", "binary_sensor", "solar_pump"),
    _m("hp_backup_heater_step1_status", "binary_sensor", "backup_heater_step_1"),
    _m("hp_backup_heater_step2_status", "binary_sensor", "backup_heater_step_2"),
    _m("hp_dhw_boost_heater_status", "binary_sensor", "dhw_boost_heater"),
    _m("hp_error_status", "binary_sensor", "fault"),
    _m(
        "hp_emergency_operation_available_space_heating_cooling",
        "binary_sensor",
        "emergency_heating_cooling_available",
    ),
    _m(
        "hp_emergency_operation_available_dhw",
        "binary_sensor",
        "emergency_dhw_available",
    ),
    _m("hp_mix_pump_status", "binary_sensor", "mixing_pump"),
    # Template sensor: the same formula (input 50 / input 40)
    Takeover(
        "template",
        "hp_heating_cop_calculated",
        "sensor",
        "cop_heating_cumulative",
        UNIT_SPELLING,
    ),
)

EXCLUDED: tuple[Excluded, ...] = (
    _x("hp_temp_liquid_gas", "sensor", SCALE),
    _x("hp_temp_pipe_out", "sensor", NOT_A_TEMPERATURE),
    _x("hp_DvS", "sensor", UNIT),
    _x("hp_operation_mode", "sensor", TEXT),
    _x("hp_control_method", "sensor", TEXT),
    _x("hp_energy_state_input_raw", "sensor", TEXT),
    Excluded("template", "hp_energy_state_label", "sensor", TEXT),
    _x("hp_target_temp_circuit1", "sensor", OTHER_TYPE),
    _x("hp_target_temp_circuit2", "sensor", OTHER_TYPE),
    _x("hp_dhw_target_temp", "sensor", OTHER_TYPE),
    _x("hp_shift_value_in_auto_mode_circuit1", "sensor", OTHER_TYPE),
    _x("hp_shift_value_in_auto_mode_circuit2", "sensor", OTHER_TYPE),
    _x("hp_compressor_modulation", "sensor", OTHER_TYPE),
    _x("hp_power_limitation", "sensor", OTHER_TYPE),
    _x("hp_dhw_desinfection_mode", "switch", OTHER_TYPE),
    _x("hp_emergency_stop_switch_on", "switch", OTHER_TYPE),
)


@dataclass(frozen=True)
class Found:
    """A takeover that applies: the YAML entity is orphaned in the registry."""

    takeover: Takeover
    old_entity_id: str
    new_entity_id: str


def plan(
    registry_entries: list[tuple[str, str, str, str]],
    live_entity_ids: set[str],
    taken_entity_ids: set[str],
    prefix: str,
) -> tuple[list[Found], list[tuple[str, str]]]:
    """Which takeovers apply, and which YAML entities are left alone, and why.

    registry_entries: (platform, unique_id, domain, entity_id) of every
    registry entry without a config entry (YAML entities have none).
    live_entity_ids: entity ids that currently have a live state, i.e. the
    YAML is still loaded; those are skipped. taken_entity_ids: entity ids
    already in the registry, so a target that is taken is skipped. prefix:
    the device name as Home Assistant turns it into entity ids.
    """
    by_key = {(p, u, d): e for p, u, d, e in registry_entries}
    found: list[Found] = []
    left: list[tuple[str, str]] = []
    for takeover in TAKEOVERS:
        old = by_key.get((takeover.platform, takeover.unique_id, takeover.domain))
        if old is None:
            continue
        new = takeover.target_entity_id(prefix)
        if old in live_entity_ids:
            left.append((old, "still_loaded"))
        elif new in taken_entity_ids and new != old:
            left.append((old, "target_taken"))
        else:
            found.append(Found(takeover, old, new))
    for excluded in EXCLUDED:
        old = by_key.get((excluded.platform, excluded.unique_id, excluded.domain))
        if old is not None:
            left.append((old, excluded.reason))
    return found, left
