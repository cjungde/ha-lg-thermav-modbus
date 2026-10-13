"""Constants for the LG ThermaV R290 integration."""

DOMAIN = "lg_thermav_r290"

CONF_CONNECTION_TYPE = "connection_type"
CONF_SLAVE_ID = "slave_id"
CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"
CONF_PARITY = "parity"
CONF_STOPBITS = "stopbits"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_EXPERIMENTAL = "experimental_registers"
CONF_ENERGY_REGISTERS = "energy_registers"
CONF_MODULATION_LIMIT = "compressor_modulation_limit"
CONF_EMERGENCY_OPERATION = "emergency_operation_button"
CONF_POLL_STATISTICS = "poll_statistics"
# Sensors of the user's own electricity meter (entity ids), see external_meter.py.
CONF_EXTERNAL_POWER = "external_power_sensor"
CONF_EXTERNAL_ENERGY = "external_energy_sensor"
CONF_POWER_LIMIT = "power_limit"

CONNECTION_TCP = "tcp"
CONNECTION_TCP_RTU = "tcp_rtu"
CONNECTION_RTU = "rtu"

DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_BAUDRATE = 9600
DEFAULT_PARITY = "N"
DEFAULT_STOPBITS = 1
DEFAULT_SCAN_INTERVAL = 10

# Operation mode register values
OPERATION_MODE_COOL = 0
OPERATION_MODE_AUTO = 3
OPERATION_MODE_HEAT = 4

OPERATION_MODE_OPTIONS = ["Cooling", "Heating", "Auto"]
OPERATION_MODE_TO_VALUE = {"Cooling": 0, "Heating": 4, "Auto": 3}
OPERATION_MODE_FROM_VALUE = {0: "Cooling", 4: "Heating", 3: "Auto"}

# ODU operation cycle (input 30002). The manual: "0: Standby (AUS) /
# 1: Kühlung / 2: Heizung". A value outside the table shows as the number.
ODU_OPERATION_CYCLE_LABELS = {0: "Standby/Off", 1: "Cooling", 2: "Heating"}

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

# What the energy state sensors show: the raw value in front of the name,
# e.g. "2 – Normal Operation", so the number the unit sends is always visible.
# A value outside 0-8 is shown as the bare number (see LGMappedSensor).
ENERGY_STATE_DISPLAY = {
    value: f"{value} – {name}" for value, name in ENERGY_STATE_LABELS.items()
}

# The only addresses the integration ever writes. A write to anything else is
# refused before it reaches the bus, whoever asks: the undocumented registers
# found by scanning (see experimental.py) must stay read-only.
WRITABLE_HOLDING_REGISTERS = frozenset({0, 1, 2, 4, 5, 7, 8})
# Writable only while the option that creates its entity is on: holding 23 is
# the compressor modulation limit (see limits.py), which not every unit serves.
MODULATION_LIMIT_WRITABLE_HOLDING_REGISTERS = frozenset({23})
WRITABLE_COILS = frozenset({0, 1, 2, 3, 4})
# Coil 5 (00006, "Auslöser Notaus-Betrieb") starts emergency operation, which
# typically means heating with the backup heater. It is writable only while
# the option that creates its button is on; otherwise no entity reaches it.
EMERGENCY_OPERATION_WRITABLE_COILS = frozenset({5})
# Coil 6 (00007) switches the power limit, holding 24 (40025) holds it (see
# power_limit.py). Writable only while the power limit option is on.
POWER_LIMIT_WRITABLE_COILS = frozenset({6})
POWER_LIMIT_WRITABLE_HOLDING_REGISTERS = frozenset({24})
