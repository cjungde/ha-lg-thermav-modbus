"""The setup flow: connection, register check, options step."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

DOMAIN = "lg_thermav_r290"
RTU = {
    "serial_port": "/dev/ttyUSB0",
    "baudrate": 9600,
    "parity": "N",
    "stopbits": 1,
    "slave_id": 1,
    "scan_interval": 10,
}
LIKE_9_KW = {("input", 34), ("holding", 23), ("coil", 6)}


def defaults(result) -> dict:
    return {str(key): key.default() for key in result["data_schema"].schema}


async def _to_features_step(hass):
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(result["flow_id"], {"connection_type": "rtu"})
    assert result["step_id"] == "rtu"
    result = await flow.async_configure(result["flow_id"], RTU)
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "detect"
    await hass.async_block_till_done()
    result = await flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "features"
    return result


async def test_a_unit_that_answers_everywhere(hass, unit) -> None:
    result = await _to_features_step(hass)
    assert result["description_placeholders"] == {
        "energy_registers": "✓",
        "compressor_modulation_limit": "✓",
        "power_limit": "✓",
    }
    # Only the safe groups are ticked, never the power limit.
    assert defaults(result) == {
        "energy_registers": True,
        "compressor_modulation_limit": True,
        "power_limit": False,
        "emergency_operation_button": False,
        "experimental_registers": False,
        "poll_statistics": False,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], defaults(result)
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data["serial_port"] == "/dev/ttyUSB0"
    assert "detected" not in entry.data
    assert entry.options["energy_registers"] is True
    assert entry.options["detected"] == {
        "energy_registers": True,
        "compressor_modulation_limit": True,
        "power_limit": True,
    }
    assert entry.options["detected_at"]
    # The entry is set up with the options ticked.
    assert hass.states.get("sensor.lg_thermav_r290_electrical_power_heat_pump")
    assert hass.states.get("number.lg_thermav_r290_max_compressor_modulation")
    assert hass.states.get("number.lg_thermav_r290_max_electrical_power") is None


async def test_a_unit_like_the_scanned_9_kw(hass, unit) -> None:
    unit.silent = set(LIKE_9_KW)
    result = await _to_features_step(hass)
    assert set(result["description_placeholders"].values()) == {"✗"}
    assert not any(defaults(result).values())
    # The power limit register is not asked once its coil stayed silent.
    assert ("holding", 24) not in unit.requests


async def test_the_same_unit_cannot_be_added_twice(hass, unit) -> None:
    result = await _to_features_step(hass)
    await hass.config_entries.flow.async_configure(result["flow_id"], defaults(result))
    await hass.async_block_till_done()

    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(result["flow_id"], {"connection_type": "rtu"})
    result = await flow.async_configure(result["flow_id"], RTU)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
