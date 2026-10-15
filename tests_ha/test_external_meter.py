"""COP against the user's own meter, inside Home Assistant."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import State
from homeassistant.data_entry_flow import FlowResultType, section
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from .test_config_flow import DOMAIN, RTU, defaults, form_input

POWER = "sensor.heat_pump_meter_power"
ENERGY = "sensor.heat_pump_meter_energy"
COP = "sensor.lg_therma_v_r290_cop_external_meter"
THERMAL = "sensor.lg_therma_v_r290_thermal_energy_calculated"
CUMULATIVE = "sensor.lg_therma_v_r290_cop_cumulative_external_meter"
# 20 L/min at 30 -> 35 °C: 20/60 × 5 × 4186 = 6977 W thermal.
THERMAL_W = 6977


@pytest.fixture
def running(unit):
    """The unit heats: inlet 30.0 °C, outlet 35.0 °C, flow 20.0 L/min."""
    read = unit.read_input_registers

    async def read_input_registers(address, count):
        values = await read(address, count)
        if address == 0:
            values[2], values[3], values[8] = 300, 350, 200
        return values

    unit.read_input_registers = read_input_registers
    return unit


def _meter(hass, power_kw: float, energy_kwh: float) -> None:
    hass.states.async_set(POWER, str(power_kw), {"unit_of_measurement": "kW"})
    hass.states.async_set(ENERGY, str(energy_kwh), {"unit_of_measurement": "kWh"})


async def _set_up(hass, options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options=options,
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_cop_and_jaz_from_the_meter(hass, running) -> None:
    _meter(hass, 1.5, 100.0)
    clock = iter([1000.0, 1000.0, 1300.0, 1300.0, 1600.0, 1600.0] + [1600.0] * 20)
    with patch(
        "custom_components.lg_therma_v_r290.sensor._monotonic",
        side_effect=lambda: next(clock),
    ):
        entry = await _set_up(
            hass,
            {"external_power_sensor": POWER, "external_energy_sensor": ENERGY},
        )
        assert float(hass.states.get(COP).state) == pytest.approx(
            THERMAL_W / 1500, abs=0.01
        )
        coordinator = hass.data[DOMAIN][entry.entry_id]
        # Five minutes at 1.5 kW: the meter grows by 0.125 kWh per poll.
        _meter(hass, 1.5, 100.125)
        await coordinator.async_refresh()
        _meter(hass, 1.5, 100.25)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    thermal_kwh = 2 * THERMAL_W * 300 / 3_600_000
    assert float(hass.states.get(THERMAL).state) == pytest.approx(thermal_kwh, abs=1e-3)
    cumulative = hass.states.get(CUMULATIVE)
    assert float(cumulative.state) == pytest.approx(thermal_kwh / 0.25, abs=0.01)
    assert cumulative.attributes["electrical_energy_kwh"] == pytest.approx(0.25)
    assert cumulative.attributes["energy_sensor"] == ENERGY


async def test_no_value_in_standby_or_without_a_usable_meter(hass, running) -> None:
    _meter(hass, 0.05, 100.0)  # 50 W: standby
    entry = await _set_up(hass, {"external_power_sensor": POWER})
    assert hass.states.get(COP).state == "unknown"
    coordinator = hass.data[DOMAIN][entry.entry_id]
    for state, attributes in (
        ("1500", {}),  # no unit: W or kW cannot be told apart
        ("unavailable", {"unit_of_measurement": "W"}),
        ("1.5", {"unit_of_measurement": "kW"}),  # usable again
    ):
        hass.states.async_set(POWER, state, attributes)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert float(hass.states.get(COP).state) == pytest.approx(
        THERMAL_W / 1500, abs=0.01
    )
    hass.states.async_set(POWER, "1500", {})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(COP).state == "unknown"
    assert hass.states.get(THERMAL) is None  # only with an energy sensor


async def test_restart_continues_the_period(hass, running) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(CUMULATIVE, "3.5"),
                {
                    "thermal_kwh": 35.0,
                    "electrical_kwh": 10.0,
                    "electrical_last": 100.0,
                    "since": "2026-10-01T00:00:00+00:00",
                    "energy_sensor": ENERGY,
                },
            ),
            (State(THERMAL, "35.0"), {}),
        ],
    )
    _meter(hass, 1.5, 102.0)  # 2 kWh more since the last reading
    await _set_up(hass, {"external_energy_sensor": ENERGY})
    cumulative = hass.states.get(CUMULATIVE)
    assert cumulative.attributes["since"] == "2026-10-01T00:00:00+00:00"
    assert cumulative.attributes["electrical_energy_kwh"] == pytest.approx(12.0)
    assert float(cumulative.state) == pytest.approx(35.0 / 12.0, abs=0.01)
    assert float(hass.states.get(THERMAL).state) == pytest.approx(35.0)


async def test_another_meter_starts_a_new_period(hass, running) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(CUMULATIVE, "3.5"),
                {
                    "thermal_kwh": 35.0,
                    "electrical_kwh": 10.0,
                    "electrical_last": 100.0,
                    "since": "2026-10-01T00:00:00+00:00",
                    "energy_sensor": "sensor.some_other_meter",
                },
            )
        ],
    )
    _meter(hass, 1.5, 102.0)
    await _set_up(hass, {"external_energy_sensor": ENERGY})
    cumulative = hass.states.get(CUMULATIVE)
    assert cumulative.attributes["since"] != "2026-10-01T00:00:00+00:00"
    assert cumulative.attributes["electrical_energy_kwh"] == 0


async def test_options_pick_and_clear_the_meter(hass, unit) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    _meter(hass, 1.5, 100.0)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    options = hass.config_entries.options

    result = await options.async_init(entry.entry_id)
    result = await options.async_configure(
        result["flow_id"], {"next_step_id": "options"}
    )
    meter = result["data_schema"].schema["external_meter"]
    assert isinstance(meter, section) and meter.options["collapsed"] is True
    submitted = form_input(result, {**defaults(result), "external_meter": None})
    submitted["external_meter"] = {
        "external_power_sensor": POWER,
        "external_energy_sensor": ENERGY,
    }
    result = await options.async_configure(result["flow_id"], submitted)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["external_power_sensor"] == POWER
    assert entry.options["external_energy_sensor"] == ENERGY
    assert "external_meter" not in entry.options
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get(COP) is not None

    # Clearing the power sensor removes it from the options and its COP.
    result = await options.async_init(entry.entry_id)
    result = await options.async_configure(
        result["flow_id"], {"next_step_id": "options"}
    )
    assert result["data_schema"].schema["external_meter"].options["collapsed"] is False
    submitted = form_input(result, {**defaults(result), "external_meter": None})
    submitted["external_meter"] = {"external_energy_sensor": ENERGY}
    await options.async_configure(result["flow_id"], submitted)
    await hass.async_block_till_done()
    assert "external_power_sensor" not in entry.options
    assert registry.async_get(COP) is None
    assert registry.async_get(CUMULATIVE) is not None
