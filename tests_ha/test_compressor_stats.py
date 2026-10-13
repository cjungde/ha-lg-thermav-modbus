"""Compressor statistics inside Home Assistant."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from .test_config_flow import DOMAIN, RTU

STARTS = "sensor.lg_thermav_r290_compressor_starts"
RUN_TIME = "sensor.lg_thermav_r290_compressor_run_time"
SPEED = "sensor.lg_thermav_r290_compressor_average_speed"


class Compressor:
    """Discrete input 3 (compressor) and input 24 (speed / 60) per poll."""

    def __init__(self, unit) -> None:
        self.on = False
        self.rpm = 0
        read_di, read_in = unit.read_discrete_inputs, unit.read_input_registers

        async def discrete(address, count):
            values = await read_di(address, count)
            if address == 0:
                values[3] = self.on
            return values

        async def inputs(address, count):
            values = await read_in(address, count)
            if address == 16:
                values[8] = self.rpm // 60
            return values

        unit.read_discrete_inputs = discrete
        unit.read_input_registers = inputs


async def _set_up(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options={"compressor_statistics": True},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_counts_from_polls(hass, unit) -> None:
    compressor = Compressor(unit)
    clock = iter(float(t) for t in range(0, 10_000, 60))
    with patch(
        "custom_components.lg_thermav_r290.coordinator._monotonic",
        side_effect=lambda: next(clock),
    ):
        entry = await _set_up(hass)  # poll at t=0: off
        coordinator = hass.data[DOMAIN][entry.entry_id]
        for on, rpm in (
            (True, 1800),
            (True, 2400),
            (False, 0),
            (True, 3000),
            (False, 0),
        ):
            compressor.on, compressor.rpm = on, rpm
            await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(STARTS).state == "2"
    assert hass.states.get(STARTS).attributes["last_run_minutes"] == 1.0
    assert float(hass.states.get(RUN_TIME).state) == round(180 / 3600, 3)
    assert hass.states.get(RUN_TIME).attributes["unit_of_measurement"] == "h"
    # (60 × 1800 + 60 × 2400 + 60 × 3000) / 180 = 2400
    assert hass.states.get(SPEED).state == "2400"


async def test_restart_continues(hass, unit) -> None:
    Compressor(unit)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(STARTS, "41"),
                {
                    "starts": 41,
                    "run_s": 36000.0,
                    "day": None,
                    "day_run_s": 0.0,
                    "day_rpm_s": 0.0,
                    "last_run_s": 900.0,
                },
            )
        ],
    )
    await _set_up(hass)
    assert hass.states.get(STARTS).state == "41"
    assert float(hass.states.get(RUN_TIME).state) == 10.0
    assert hass.states.get(STARTS).attributes["last_run_minutes"] == 15.0


async def test_not_created_without_the_option(hass, unit) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(STARTS) is None
    assert hass.data[DOMAIN][entry.entry_id].compressor_stats is None
