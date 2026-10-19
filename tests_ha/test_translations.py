"""Entity names come from the translations; entity ids stay English.\n\nAlso when the language changes after setup: entity ids are kept, only the\nnames follow the new language.\n"""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_config_flow import DOMAIN, RTU

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / DOMAIN
ALL_OPTIONS = {
    "energy_registers": True,
    "compressor_modulation_limit": True,
    "power_limit": True,
    "emergency_operation_button": True,
    "experimental_registers": True,
    "poll_statistics": True,
    "compressor_statistics": True,
    "external_power_sensor": "sensor.meter_power",
    "external_energy_sensor": "sensor.meter_energy",
}


def _names(language: str) -> dict:
    path = "strings.json" if language == "strings" else f"translations/{language}.json"
    return json.loads((COMPONENT / path).read_text())["entity"]


def test_every_language_names_the_same_entities() -> None:
    keys = {
        lang: {(p, k) for p, names in _names(lang).items() for k in names}
        for lang in ("strings", "en", "de")
    }
    assert keys["strings"] == keys["en"] == keys["de"]
    assert _names("strings") == _names("en")


async def _set_up(hass) -> MockConfigEntry:
    hass.states.async_set("sensor.meter_power", "1", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.meter_energy", "1", {"unit_of_measurement": "kWh"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options=ALL_OPTIONS,
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("language", ["en", "de"])
async def test_names_and_entity_ids(hass, unit, language) -> None:
    hass.config.language = language
    entry = await _set_up(hass)
    names = _names(language)
    english = _names("en")
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entities) == 116
    for entity in entities:
        assert entity.translation_key, entity.entity_id
        key = entity.unique_id.removeprefix(f"{entry.entry_id}_")
        template = english[entity.domain][entity.translation_key]["name"]
        register = key.rsplit("_", 1)[-1]
        english_name = template.replace("{register}", register)
        # The key is the English name as an id; so is the entity id, in
        # every language.
        assert key == slugify(english_name), entity.entity_id
        assert entity.entity_id == f"{entity.domain}.lg_therma_v_r290_{key}"
        state = hass.states.get(entity.entity_id)
        if state is None:  # disabled by default
            continue
        local = names[entity.domain][entity.translation_key]["name"]
        expected = "LG Therma V R290 " + local.replace("{register}", register)
        assert state.attributes["friendly_name"] == expected, entity.entity_id


async def test_german_examples(hass, unit) -> None:
    hass.config.language = "de"
    await _set_up(hass)
    for entity_id, name in (
        ("sensor.lg_therma_v_r290_outdoor_temperature", "Außentemperatur"),
        ("switch.lg_therma_v_r290_heating_cooling", "Heizen/Kühlen"),
        (
            "sensor.lg_therma_v_r290_experimental_input_30015",
            "Experimentelles Input-Register 30015",
        ),
        (
            "binary_sensor.lg_therma_v_r290_energy_state_normal_operation",
            "Energiezustand: Normalbetrieb",
        ),
        ("sensor.lg_therma_v_r290_compressor_starts", "Verdichterstarts"),
        ("sensor.lg_therma_v_r290_cop_external_meter", "COP (externer Zähler)"),
    ):
        state = hass.states.get(entity_id)
        assert state.attributes["friendly_name"] == f"LG Therma V R290 {name}"


async def test_changing_the_language_keeps_entity_ids(hass, unit) -> None:
    """Set up in English, switch to German, restart: same ids, German names."""
    entry = await _set_up(hass)
    registry = er.async_get(hass)
    before = {
        (e.domain, e.unique_id): e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    await hass.config.async_update(language="de")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    after = {
        (e.domain, e.unique_id): e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert after == before
    state = hass.states.get("sensor.lg_therma_v_r290_outdoor_temperature")
    assert state.attributes["friendly_name"] == "LG Therma V R290 Außentemperatur"
