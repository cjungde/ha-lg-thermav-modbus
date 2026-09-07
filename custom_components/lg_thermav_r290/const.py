"""Constants for the LG ThermaV R290 integration."""

DOMAIN = "lg_thermav_r290"

CONF_CONNECTION_TYPE = "connection_type"
CONF_SLAVE_ID = "slave_id"
CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"
CONF_PARITY = "parity"
CONF_STOPBITS = "stopbits"
CONF_SCAN_INTERVAL = "scan_interval"

CONNECTION_TCP = "tcp"
CONNECTION_TCP_RTU = "tcp_rtu"
CONNECTION_RTU = "rtu"

DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_BAUDRATE = 9600
DEFAULT_PARITY = "N"
DEFAULT_STOPBITS = 1
DEFAULT_SCAN_INTERVAL = 30

# Operation mode register values
OPERATION_MODE_COOL = 0
OPERATION_MODE_AUTO = 3
OPERATION_MODE_HEAT = 4

OPERATION_MODE_OPTIONS = ["Cooling", "Heating", "Auto"]
OPERATION_MODE_TO_VALUE = {"Cooling": 0, "Heating": 4, "Auto": 3}
OPERATION_MODE_FROM_VALUE = {0: "Cooling", 4: "Heating", 3: "Auto"}

# Control method register values
CONTROL_METHOD_OPTIONS = [
    "Outlet Water Temp Control",
    "Inlet Water Temp Control",
    "Room Air Control",
]
CONTROL_METHOD_TO_VALUE = {
    "Outlet Water Temp Control": 0,
    "Inlet Water Temp Control": 1,
    "Room Air Control": 2,
}
CONTROL_METHOD_FROM_VALUE = {
    0: "Outlet Water Temp Control",
    1: "Inlet Water Temp Control",
    2: "Room Air Control",
}

# Energy state (holding reg 9) read-only label map
ENERGY_STATE_LABELS = {
    0: "Not Used",
    1: "Forced Off",
    2: "Normal Operation",
    3: "On Recommendation",
    4: "On Command",
    5: "On Command Step 2",
    6: "On Recommendation Step 1",
    7: "Energy Saving Mode",
    8: "Super Energy Saving Mode",
}
