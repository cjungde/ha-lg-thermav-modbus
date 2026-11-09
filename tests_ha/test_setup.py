"""Setting up an entry: entities, option-gated entities, writes, migration."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_config_flow import DOMAIN, RTU


async def _set_up(hass, options=None, minor_version=4) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options=options or {},
        version=1,
        minor_version=minor_version,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entities(hass, entry) -> dict[str, er.RegistryEntry]:
    registry = er.async_get(hass)
    return {
        e.entity_id: e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


async def test_entities_without_options(hass, unit) -> None:
    entry = await _set_up(hass)
    entities = _entities(hass, entry)
    assert "sensor.lg_therma_v_r290_outdoor_temperature" in entities
    assert "switch.lg_therma_v_r290_heating_cooling" in entities
    assert "button.lg_therma_v_r290_start_disinfection" in entities
    # Option-gated entities are not created.
    for entity_id in (
        "sensor.lg_therma_v_r290_electrical_power_heat_pump",
        "number.lg_therma_v_r290_max_compressor_modulation",
        "number.lg_therma_v_r290_max_electrical_power",
        "switch.lg_therma_v_r290_power_limit",
        "button.lg_therma_v_r290_start_emergency_operation",
        "sensor.lg_therma_v_r290_experimental_input_30015",
        "sensor.lg_therma_v_r290_poll_duration",
        "sensor.lg_therma_v_r290_bus_load",
        "sensor.lg_therma_v_r290_modbus_errors",
        "sensor.lg_therma_v_r290_last_modbus_error",
    ):
        assert entity_id not in entities, entity_id
    # Every unique id is <entry id>_<key>.
    for entity in entities.values():
        assert entity.unique_id.startswith(f"{entry.entry_id}_")
    state = hass.states.get("sensor.lg_therma_v_r290_outdoor_temperature")
    assert state.state == "0.0"


async def test_asks_the_shared_link_for_a_timeout_floor(hass, unit) -> None:
    """20 s rather than the library's 10, through the poll-counting wrapper."""
    await _set_up(hass)
    assert unit.required_timeout == 20.0


async def test_all_options_create_their_entities(hass, unit) -> None:
    options = {
        "energy_registers": True,
        "compressor_modulation_limit": True,
        "power_limit": True,
        "emergency_operation_button": True,
        "experimental_registers": True,
        "poll_statistics": True,
        "compressor_statistics": True,
    }
    entry = await _set_up(hass, options)
    entities = _entities(hass, entry)
    for entity_id in (
        "sensor.lg_therma_v_r290_electrical_power_heat_pump",
        "sensor.lg_therma_v_r290_cop_reported",
        "number.lg_therma_v_r290_max_compressor_modulation",
        "number.lg_therma_v_r290_max_electrical_power",
        "switch.lg_therma_v_r290_power_limit",
        "button.lg_therma_v_r290_start_emergency_operation",
        "sensor.lg_therma_v_r290_experimental_input_30015",
        "sensor.lg_therma_v_r290_poll_duration",
        "sensor.lg_therma_v_r290_bus_load",
        "sensor.lg_therma_v_r290_modbus_errors",
        "sensor.lg_therma_v_r290_last_modbus_error",
    ):
        assert entity_id in entities, entity_id
    assert len(entities) == 115


async def test_writes_reach_the_unit(hass, unit) -> None:
    await _set_up(hass, {"power_limit": True})
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.lg_therma_v_r290_heating_cooling"},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.lg_therma_v_r290_max_electrical_power", "value": 2.0},
        blocking=True,
    )
    assert ("coil", 0, True) in unit.writes
    assert ("holding", 24, 20) in unit.writes  # tenths of a kW


async def test_migration_keeps_entity_ids(hass, unit) -> None:
    """An entry from before 1.3.0 (minor version 1) gets every rename step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = {
        ("switch", "hauptschalter"): "switch.lg_therma_v_r290_heat_pump",
        ("sensor", "outside_temp"): "sensor.lg_therma_v_r290_outdoor_temperature",
        ("sensor", "room_air_temp_circuit1_hold"): (
            "sensor.lg_therma_v_r290_room_air_temperature_circuit_1_holding"
        ),
    }
    for (domain, key), entity_id in old.items():
        registry.async_get_or_create(
            domain,
            DOMAIN,
            f"{entry.entry_id}_{key}",
            config_entry=entry,
            suggested_object_id=entity_id.split(".", 1)[1],
        )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 4
    expected = {
        "switch.lg_therma_v_r290_heat_pump": "heating_cooling",
        "sensor.lg_therma_v_r290_outdoor_temperature": "outdoor_temperature",
        "sensor.lg_therma_v_r290_room_air_temperature_circuit_1_holding": (
            "target_room_air_temperature_circuit_1"
        ),
    }
    for entity_id, key in expected.items():
        entity = registry.async_get(entity_id)
        assert entity is not None, entity_id
        assert entity.unique_id == f"{entry.entry_id}_{key}"
    # The kept entity id still has a state.
    assert hass.states.get("switch.lg_therma_v_r290_heat_pump") is not None


async def test_no_flow_while_the_pump_is_off(hass, unit) -> None:
    """5.0 L/min with the pump stopped means 0; the register stays visible."""
    unit.values = {("input", 8): 50, ("input", 2): 300, ("input", 3): 305}
    await _set_up(hass)
    state = hass.states.get("sensor.lg_therma_v_r290_flow_rate")
    assert float(state.state) == 0.0
    assert state.attributes["register_value"] == 5.0
    # No phantom heat from the 0.5 K between inlet and outlet.
    power = hass.states.get("sensor.lg_therma_v_r290_thermal_power_calculated")
    assert float(power.state) == 0


async def test_flow_with_the_pump_running_is_kept(hass, unit) -> None:
    unit.values = {
        ("input", 8): 153,
        ("input", 2): 300,
        ("input", 3): 350,
        ("discrete", 0): 1,
        ("discrete", 1): 1,
    }
    await _set_up(hass)
    state = hass.states.get("sensor.lg_therma_v_r290_flow_rate")
    assert float(state.state) == 15.3
    assert state.attributes["register_value"] == 15.3
    power = hass.states.get("sensor.lg_therma_v_r290_thermal_power_calculated")
    assert float(power.state) > 5000


async def test_circuit_1_target_spans_20_to_60(hass, unit) -> None:
    """Below 20 °C the unit does not accept a heating setpoint."""
    await _set_up(hass)
    entity_id = "number.lg_therma_v_r290_target_temperature_circuit_1_radiators"
    state = hass.states.get(entity_id)
    assert state.attributes["min"] == 20
    assert state.attributes["max"] == 60
    for value, raw in ((20, 200), (60, 600)):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )
        assert ("holding", 2, raw) in unit.writes


async def test_temperatures_below_zero(hass, unit) -> None:
    """-0.2 °C outdoors and -8.5 °C at the evaporator, not 6553.4 °C."""
    unit.values = {("input", 12): 65534, ("input", 20): 65451}
    await _set_up(hass)
    outdoor = hass.states.get("sensor.lg_therma_v_r290_outdoor_temperature")
    assert float(outdoor.state) == -0.2
    evaporator = hass.states.get(
        "sensor.lg_therma_v_r290_temperature_before_evaporator"
    )
    assert float(evaporator.state) == -8.5


async def test_a_temperature_input_without_a_sensor_is_unknown(hass, unit) -> None:
    """Flow Temperature Circuit 2 without a second circuit: 64887, not -64.9 °C."""
    unit.values = {("input", 9): 64887, ("input", 12): 65534}
    await _set_up(hass)
    state = hass.states.get("sensor.lg_therma_v_r290_flow_temperature_circuit_2")
    assert state.state == "unknown"
    # The other temperatures are not affected.
    outdoor = hass.states.get("sensor.lg_therma_v_r290_outdoor_temperature")
    assert float(outdoor.state) == -0.2


async def test_negative_thermal_power_during_a_defrost(hass, unit) -> None:
    """-1.2 kW, not 4 294 966 096 W; the COP shows what the defrost costs."""
    unit.values = {("input", 48): 0xFFFF, ("input", 49): 0xFB50, ("input", 37): 1500}
    await _set_up(hass, {"energy_registers": True})
    thermal = hass.states.get("sensor.lg_therma_v_r290_thermal_power_reported")
    assert float(thermal.state) == -1200
    cop = hass.states.get("sensor.lg_therma_v_r290_cop_reported")
    assert float(cop.state) == -0.8


async def test_a_defrost_shows_on_the_calculated_side(hass, unit) -> None:
    """Pump running, outlet 2 K below inlet: heat leaves the water."""
    unit.values = {
        ("input", 2): 350,  # inlet 35.0 °C
        ("input", 3): 330,  # outlet 33.0 °C
        ("input", 8): 200,  # 20.0 L/min
        ("discrete", 0): 1,
        ("discrete", 1): 1,
        ("input", 37): 1500,  # electrical 1500 W
    }
    await _set_up(hass, {"energy_registers": True})
    power = hass.states.get("sensor.lg_therma_v_r290_thermal_power_calculated")
    assert float(power.state) == -2791  # 20/60 × -2 × 4186
    cop = hass.states.get("sensor.lg_therma_v_r290_cop_calculated")
    assert float(cop.state) == -1.86
