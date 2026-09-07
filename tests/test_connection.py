"""The mapping from stored entry data to Modbus connection parameters.

These are the settings the shared connection is keyed on: two entries that
produce equal parameters share one connection and serialize their requests,
two that do not are refused. Getting the mapping wrong is therefore not a
cosmetic error -- it either opens a second socket onto a bus that can only
serve one conversation at a time, or it refuses a setup that should work.

No Home Assistant install is needed: connection.py imports nothing from it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

from modbus_connection import ModbusSerialParams, ModbusTcpParams
import pytest

COMPONENT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "lg_thermav_r290"
)


def _load(module_name: str):
    """Import one module out of the component without importing the package.

    The package's ``__init__`` pulls in Home Assistant, which is not a test
    dependency and would make these tests need a full core checkout to say
    something about sixty lines of pure data mapping. A stub package stands in
    so that the relative ``from .const import ...`` still resolves.
    """
    package = "lg_thermav_r290_under_test"
    if package not in sys.modules:
        stub = types.ModuleType(package)
        stub.__path__ = [str(COMPONENT)]
        sys.modules[package] = stub

    qualified = f"{package}.{module_name}"
    if qualified not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            qualified, COMPONENT / f"{module_name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
    return sys.modules[qualified]


params_from_entry_data = _load("connection").params_from_entry_data

TCP_ENTRY = {
    "connection_type": "tcp",
    "host": "192.168.25.10",
    "port": 502,
    "slave_id": 33.0,
}


def test_tcp_uses_socket_framing() -> None:
    params = params_from_entry_data(TCP_ENTRY)
    assert params == ModbusTcpParams(host="192.168.25.10", port=502, framer="socket")


def test_tcp_rtu_keeps_the_socket_but_reframes() -> None:
    """A transparent gateway needs RTU frames over the same TCP endpoint."""
    params = params_from_entry_data({**TCP_ENTRY, "connection_type": "tcp_rtu"})
    assert params == ModbusTcpParams(host="192.168.25.10", port=502, framer="rtu")


def test_the_two_tcp_framings_do_not_compare_equal() -> None:
    """They share an endpoint, so only inequality keeps them off one socket."""
    plain = params_from_entry_data(TCP_ENTRY)
    tunnelled = params_from_entry_data({**TCP_ENTRY, "connection_type": "tcp_rtu"})
    assert plain.endpoint == tunnelled.endpoint
    assert plain != tunnelled


def test_entries_for_different_units_on_one_gateway_share_parameters() -> None:
    """The heat pump and a meter behind one gateway must land on one connection."""
    heat_pump = params_from_entry_data(TCP_ENTRY)
    meter = params_from_entry_data({**TCP_ENTRY, "slave_id": 1.0})
    assert heat_pump == meter


def test_missing_port_falls_back_to_the_default() -> None:
    params = params_from_entry_data({"connection_type": "tcp", "host": "10.0.0.5"})
    assert params.port == 502


def test_absent_connection_type_is_read_as_tcp() -> None:
    """Entries predating the three-way choice stored no type at all."""
    params = params_from_entry_data({"host": "10.0.0.5", "port": 502})
    assert params == ModbusTcpParams(host="10.0.0.5", port=502, framer="socket")


def test_serial_carries_every_line_setting() -> None:
    params = params_from_entry_data(
        {
            "connection_type": "rtu",
            "serial_port": "/dev/ttyUSB0",
            "baudrate": 19200,
            "parity": "E",
            "stopbits": 2,
        }
    )
    assert params == ModbusSerialParams(
        device="/dev/ttyUSB0",
        baudrate=19200,
        parity="E",
        stopbits=2,
        bytesize=8,
        framer="rtu",
    )


def test_serial_defaults_match_the_config_flow() -> None:
    params = params_from_entry_data(
        {"connection_type": "rtu", "serial_port": "/dev/ttyUSB0"}
    )
    assert (params.baudrate, params.parity, params.stopbits) == (9600, "N", 1)


def test_serial_without_a_port_is_an_error_rather_than_a_guess() -> None:
    with pytest.raises(KeyError):
        params_from_entry_data({"connection_type": "rtu"})
