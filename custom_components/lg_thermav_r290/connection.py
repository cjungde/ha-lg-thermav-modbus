"""Translate stored config-entry data into Modbus connection parameters.

Deliberately free of Home Assistant imports: the mapping from what the config
flow stored to what the bus needs is pure data, and keeping it here lets the
test suite cover all three connection types without a Home Assistant install.
"""

from __future__ import annotations

from typing import Any

from modbus_connection import ModbusSerialParams, ModbusTcpParams

from .const import (
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_PARITY,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    CONNECTION_TCP,
    CONNECTION_TCP_RTU,
    DEFAULT_BAUDRATE,
    DEFAULT_PARITY,
    DEFAULT_PORT,
    DEFAULT_STOPBITS,
)

# Line speed assumed for RTU frames tunnelled over TCP; see the tcp_rtu branch.
_SOCKET_BAUDRATE = 115200


def params_from_entry_data(
    data: dict[str, Any],
) -> ModbusTcpParams | ModbusSerialParams:
    """Build the connection parameters an entry's stored data describes.

    The three connection types the config flow offers map one to one:

    * ``tcp``     — Modbus TCP, MBAP framing
    * ``tcp_rtu`` — RTU frames tunnelled over TCP by a transparent
      serial-to-Ethernet gateway, which needs the same socket but RTU framing
    * ``rtu``     — a serial line

    Entries written before the integration moved to a shared connection are
    read as they stand; nothing about the stored shape had to change.

    The parameters are also the sharing key. Two entries that describe the same
    endpoint the same way — the heat pump and an energy meter behind one
    RS485 gateway, say — end up on one connection with their requests
    serialized; two that describe it differently are refused rather than
    silently reframed, because one socket cannot carry both framings.
    """
    connection_type = data.get(CONF_CONNECTION_TYPE, CONNECTION_TCP)

    if connection_type == CONNECTION_TCP_RTU:
        # An RTU frame over a socket is a serial link on a socket transport,
        # which is what the library asks for since modbus-connection 4.12.
        # The line speed is the one the library itself assumed for this case:
        # high enough to land on the 1.75 ms inter-frame floor. The socket
        # ignores the line settings, so nothing about the gateway is implied.
        host = data["host"]
        address = f"[{host}]" if ":" in host else host
        return ModbusSerialParams(
            device=f"socket://{address}:{data.get('port', DEFAULT_PORT)}",
            baudrate=_SOCKET_BAUDRATE,
            framer="rtu",
        )

    if connection_type == CONNECTION_TCP:
        return ModbusTcpParams(host=data["host"], port=data.get("port", DEFAULT_PORT))

    return ModbusSerialParams(
        device=data[CONF_SERIAL_PORT],
        baudrate=data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        parity=data.get(CONF_PARITY, DEFAULT_PARITY),
        stopbits=data.get(CONF_STOPBITS, DEFAULT_STOPBITS),
        bytesize=8,
        framer="rtu",
    )
