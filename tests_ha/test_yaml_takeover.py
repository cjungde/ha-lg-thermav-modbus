"""Taking over the history of the isarrider YAML setup, with the real recorder."""

from __future__ import annotations

from datetime import timedelta

from homeassistant import config_entries
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    statistics_during_period,
)
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.lg_therma_v_r290 import yaml_takeover

from .test_config_flow import DOMAIN, RTU, defaults, form_input


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """The recorder has to start before Home Assistant (see conftest.py)."""
    yield


OLD_INLET = "sensor.hp_inlet_temp"
NEW_INLET = "sensor.lg_therma_v_r290_inlet_temperature"
OLD_SWITCH = "switch.hp_hauptschalter"
NEW_SWITCH = "switch.lg_therma_v_r290_heating_cooling"
OLD_LIQUID_GAS = "sensor.hp_temp_liquid_gas"


def _yaml_entity(hass, domain, unique_id, entity_id) -> None:
    er.async_get(hass).async_get_or_create(
        domain,
        "modbus",
        unique_id,
        suggested_object_id=entity_id.split(".", 1)[1],
    )


def _import_old_statistics(hass) -> None:
    """Two hours of long-term statistics under the YAML id."""
    hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    async_import_statistics(
        hass,
        {
            "mean_type": StatisticMeanType.ARITHMETIC,
            "has_sum": False,
            "name": None,
            "source": "recorder",
            "statistic_id": OLD_INLET,
            "unit_class": "temperature",
            "unit_of_measurement": "°C",
        },
        [
            {
                "start": hour - timedelta(hours=3),
                "mean": 28.0,
                "min": 27.0,
                "max": 29.0,
            },
            {
                "start": hour - timedelta(hours=2),
                "mean": 29.0,
                "min": 28.0,
                "max": 30.0,
            },
        ],
    )


def _statistics(hass, statistic_id):
    start = dt_util.utcnow() - timedelta(hours=6)
    result = statistics_during_period(
        hass, start, None, {statistic_id}, "hour", None, {"mean"}
    )
    return [row["mean"] for row in result.get(statistic_id, [])]


async def _record_yaml_history(hass) -> None:
    """Some history under the YAML ids, then the state after removing the YAML."""
    _yaml_entity(hass, "sensor", "modbus.hp_inlet_temp", OLD_INLET)
    _import_old_statistics(hass)
    _yaml_entity(hass, "switch", "modbus.hp_hauptschalter", OLD_SWITCH)
    _yaml_entity(hass, "sensor", "modbus.hp_temp_liquid_gas", OLD_LIQUID_GAS)
    for value in ("29.5", "30.1"):
        hass.states.async_set(OLD_INLET, value, {"unit_of_measurement": "°C"})
        await async_wait_recording_done(hass)
    hass.states.async_set(OLD_SWITCH, "on")
    await async_wait_recording_done(hass)
    # After the package is removed and Home Assistant restarted:
    for entity_id in (OLD_INLET, OLD_SWITCH, OLD_LIQUID_GAS):
        hass.states.async_set(entity_id, "unavailable", {"restored": True})
    await async_wait_recording_done(hass)


async def _to_takeover_step(hass):
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(result["flow_id"], {"connection_type": "rtu"})
    result = await flow.async_configure(result["flow_id"], RTU)
    assert result["step_id"] == "check"
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "features"})
    assert result["step_id"] == "features"
    return await flow.async_configure(
        result["flow_id"], form_input(result, defaults(result))
    )


def _history(hass, entity_id, start):
    states = get_significant_states(hass, start, entity_ids=[entity_id])
    return [s.state for s in states.get(entity_id, [])]


async def test_history_continues_under_the_integration_id(
    recorder_mock, hass, unit
) -> None:
    start = dt_util.utcnow()
    await _record_yaml_history(hass)

    result = await _to_takeover_step(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "yaml_takeover"
    placeholders = result["description_placeholders"]
    assert placeholders["count"] == "2"
    assert f"`{OLD_INLET}` | → | `{NEW_INLET}`" in placeholders["takeover_table"]
    assert f"`{OLD_LIQUID_GAS}` ①" in placeholders["left_table"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"take_over": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    registry = er.async_get(hass)
    # The YAML entities are gone, the integration's are under the new ids.
    assert (
        registry.async_get_entity_id("sensor", "modbus", "modbus.hp_inlet_temp") is None
    )
    assert (
        registry.async_get(NEW_INLET).unique_id == f"{entry.entry_id}_inlet_temperature"
    )
    assert (
        registry.async_get(NEW_SWITCH).unique_id == f"{entry.entry_id}_heating_cooling"
    )
    # Excluded ones are left alone.
    assert registry.async_get(OLD_LIQUID_GAS) is not None

    # The old history is now under the new id, followed by the integration's.
    history = await recorder_mock.async_add_executor_job(
        _history, hass, NEW_INLET, start
    )
    assert history[:2] == ["29.5", "30.1"]
    assert history[-1] == "0.0"  # the fake unit's first poll
    old = await recorder_mock.async_add_executor_job(_history, hass, OLD_INLET, start)
    assert old == []
    # So are the long-term statistics.
    statistics = await recorder_mock.async_add_executor_job(
        _statistics, hass, NEW_INLET
    )
    assert statistics == [28.0, 29.0]
    assert (
        await recorder_mock.async_add_executor_job(_statistics, hass, OLD_INLET) == []
    )


async def test_declined_leaves_everything(recorder_mock, hass, unit) -> None:
    await _record_yaml_history(hass)
    result = await _to_takeover_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"take_over": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get(OLD_INLET).platform == "modbus"
    assert registry.async_get(NEW_INLET).platform == DOMAIN


async def test_no_step_without_yaml_entities(hass, unit) -> None:
    result = await _to_takeover_step(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_yaml_still_loaded_is_not_taken_over(hass, unit) -> None:
    _yaml_entity(hass, "sensor", "modbus.hp_inlet_temp", OLD_INLET)
    _yaml_entity(hass, "sensor", "modbus.hp_outlet_temp", "sensor.hp_outlet_temp")
    hass.states.async_set(OLD_INLET, "30.1")  # live: the YAML is still loaded
    hass.states.async_set("sensor.hp_outlet_temp", "unavailable", {"restored": True})
    result = await _to_takeover_step(hass)
    assert result["description_placeholders"]["count"] == "1"
    assert f"`{OLD_INLET}` ⑥" in result["description_placeholders"]["left_table"]


async def test_every_target_is_an_integration_entity(hass, unit) -> None:
    hass.states.async_set("sensor.m_p", "1", {"unit_of_measurement": "kW"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options={
            "energy_registers": True,
            "power_limit": True,
        },
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    missing = [
        t.target_entity_id("lg_therma_v_r290")
        for t in yaml_takeover.TAKEOVERS
        if registry.async_get(t.target_entity_id("lg_therma_v_r290")) is None
    ]
    assert missing == []
