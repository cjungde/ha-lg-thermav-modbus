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
    ):
        assert entity_id in entities, entity_id
    assert len(entities) == 113


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
