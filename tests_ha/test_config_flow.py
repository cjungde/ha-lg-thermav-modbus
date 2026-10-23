"""The setup flow: connection, register check, options step."""

from __future__ import annotations

import logging

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, section

DOMAIN = "lg_therma_v_r290"
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
    """The form's defaults, flat: the toggles in sections included."""
    values = {}
    for key, value in result["data_schema"].schema.items():
        if isinstance(value, section):
            if str(key) == "external_meter":
                values[str(key)] = None  # sensor pickers, no defaults
                continue
            for field in value.schema.schema:
                values[str(field)] = field.default()
        else:
            values[str(key)] = key.default()
    return values


def form_input(result, values: dict) -> dict:
    """Flat values as the form submits them: nested per section."""
    submitted = {}
    for key, value in result["data_schema"].schema.items():
        name = str(key)
        if isinstance(value, section):
            if name == "external_meter":
                submitted[name] = values[name] or {}
                continue
            submitted[name] = {
                str(field): values[str(field)] for field in value.schema.schema
            }
        else:
            submitted[name] = values[name]
    return submitted


def options_are_sections(result) -> bool:
    """Each option is a section holding its own toggle, expanded when on."""
    for name in (
        "energy_registers",
        "compressor_modulation_limit",
        "power_limit",
        "emergency_operation_button",
        "experimental_registers",
        "compressor_statistics",
        "poll_statistics",
    ):
        value = result["data_schema"].schema[name]
        if not isinstance(value, section):
            return False
        fields = list(value.schema.schema)
        if [str(f) for f in fields] != [name]:
            return False
        if value.options["collapsed"] is fields[0].default():
            return False
    return True


async def _to_features_step(hass):
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(result["flow_id"], {"connection_type": "rtu"})
    assert result["step_id"] == "rtu"
    result = await flow.async_configure(result["flow_id"], RTU)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "check"
    assert result["menu_options"] == ["detect", "features"]
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "detect"})
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
    assert options_are_sections(result)
    assert defaults(result) == {
        "energy_registers": True,
        "compressor_modulation_limit": True,
        "power_limit": False,
        "emergency_operation_button": False,
        "experimental_registers": False,
        "compressor_statistics": False,
        "poll_statistics": False,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], form_input(result, defaults(result))
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
    assert hass.states.get("sensor.lg_therma_v_r290_electrical_power_heat_pump")
    assert hass.states.get("number.lg_therma_v_r290_max_compressor_modulation")
    assert hass.states.get("number.lg_therma_v_r290_max_electrical_power") is None


async def test_a_unit_like_the_scanned_9_kw(hass, unit) -> None:
    unit.silent = set(LIKE_9_KW)
    result = await _to_features_step(hass)
    assert set(result["description_placeholders"].values()) == {"✗"}
    assert not any(defaults(result).values())
    # The power limit register is not asked once its coil stayed silent.
    assert ("holding", 24) not in unit.requests


async def test_a_probe_that_waits_too_long_cannot_connect(
    hass, unit, monkeypatch
) -> None:
    """On a link whose timeout has been raised, the form still answers."""
    monkeypatch.setattr(
        "custom_components.lg_therma_v_r290.config_flow._PROBE_TIMEOUT", 0.05
    )
    unit.hanging = {("input", 0)}
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(result["flow_id"], {"connection_type": "rtu"})
    result = await flow.async_configure(result["flow_id"], RTU)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def _submit_rtu(hass):
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(result["flow_id"], {"connection_type": "rtu"})
    return await flow.async_configure(result["flow_id"], RTU)


async def test_a_unit_not_ready_yet_gets_a_second_try(hass, unit, caplog) -> None:
    """Right after a restart the first request may go unanswered."""
    caplog.set_level(logging.INFO, logger="custom_components.lg_therma_v_r290")
    real_read = unit.read_input_registers
    calls = []

    async def read_input_registers(address, count):
        calls.append(address)
        if len(calls) == 1:
            unit.silent.add(("input", 0))
        else:
            unit.silent.discard(("input", 0))
        return await real_read(address, count)

    unit.read_input_registers = read_input_registers
    result = await _submit_rtu(hass)
    assert result["step_id"] == "check"
    assert calls == [0, 0]
    assert "Connection test to /dev/ttyUSB0, slave 1 failed" in caplog.text
    assert "trying again" in caplog.text


async def test_a_failed_test_logs_why(hass, unit, caplog) -> None:
    """The form can only say "Connection failed"; the log says why."""
    unit.silent = {("input", 0)}
    result = await _submit_rtu(hass)
    assert result["errors"] == {"base": "cannot_connect"}
    assert unit.requests == [("input", 0), ("input", 0)]  # two attempts
    assert "failed after 2 attempts" in caplog.text
    assert "input 0: no answer" in caplog.text  # the reason from the unit


async def test_a_refusal_is_not_retried(hass, unit, caplog) -> None:
    unit.refused = {("input", 0)}
    result = await _submit_rtu(hass)
    assert result["errors"] == {"base": "invalid_slave_id"}
    assert unit.requests == [("input", 0)]
    assert "refused" in caplog.text


async def test_the_check_can_be_skipped(hass, unit) -> None:
    """Skipped, nothing is asked beyond the connection test, nothing is
    ticked, and the entry records the check as never run."""
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(result["flow_id"], {"connection_type": "rtu"})
    result = await flow.async_configure(result["flow_id"], RTU)
    assert result["step_id"] == "check"
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "features"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "features"
    assert set(result["description_placeholders"].values()) == {"–"}
    assert not any(defaults(result).values())
    # Only the connection test reached the unit.
    assert unit.requests == [("input", 0)]

    result = await flow.async_configure(
        result["flow_id"], form_input(result, defaults(result))
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    options = result["result"].options
    assert options["detected"] is None
    assert options["detected_at"] is None


async def test_a_check_that_proves_nothing_records_nothing(hass, unit) -> None:
    """The link dropped during the check (detect.py returns None): the form
    says so, nothing is ticked, and the entry records no check."""
    unit.silent = {("input", 34), ("holding", 23), ("coil", 6)}
    real_read = unit.read_input_registers
    witnessed = []

    async def read_input_registers(address, count):
        # Answer the connection test and the first witness, then go silent.
        if address == 0:
            witnessed.append(address)
            if len(witnessed) > 2:
                unit.silent.add(("input", 0))
        return await real_read(address, count)

    unit.read_input_registers = read_input_registers
    result = await _to_features_step(hass)
    assert result["errors"] == {"base": "check_inconclusive"}
    assert set(result["description_placeholders"].values()) == {"–"}
    assert not any(defaults(result).values())

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], form_input(result, defaults(result))
    )
    await hass.async_block_till_done()
    assert result["result"].options["detected"] is None
    assert result["result"].options["detected_at"] is None


async def test_the_same_unit_cannot_be_added_twice(hass, unit) -> None:
    result = await _to_features_step(hass)
    await hass.config_entries.flow.async_configure(
        result["flow_id"], form_input(result, defaults(result))
    )
    await hass.async_block_till_done()

    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await flow.async_configure(result["flow_id"], {"connection_type": "rtu"})
    result = await flow.async_configure(result["flow_id"], RTU)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
