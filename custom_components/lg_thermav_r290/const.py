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

# The only addresses the integration ever writes. A write to anything else is
# refused before it reaches the bus, whoever asks: the undocumented registers
# found by scanning (see experimental.py) must stay read-only, and coil 5 is a
# trigger for emergency operation that no entity should reach. That exclusion
# is deliberate and stays: the manual's "start emergency operation" runs the
# machine outside its normal control, and nothing in this integration has a
# reason to reach for it. It is left here as a documented omission so the next
# reader does not take it for an oversight.
#
# 23, 24 and coil 6 are the optional limits from capabilities.py. They are
# listed here because they are documented device functions rather than scan
# finds; whether they are reachable is decided per device at setup, and an
# entity for them only exists where the device answered.
WRITABLE_HOLDING_REGISTERS = frozenset({0, 1, 2, 4, 5, 7, 8, 23, 24})
WRITABLE_COILS = frozenset({0, 1, 2, 3, 4, 6})

# --- flush pulse ---------------------------------------------------------
# How early `flush_pulse_imminent` fires, in seconds. The ramp alone is about
# 50 s, which is too late for an automation that has to write to the machine
# before the pulse: a Modbus write plus the unit's reaction does not fit in it.
CONF_FLUSH_PULSE_LEAD = "flush_pulse_lead_seconds"
DEFAULT_FLUSH_PULSE_LEAD = 180

# One event type, distinguished by its `type` field -- the shape Home
# Assistant's device triggers are built on.
EVENT_FLUSH_PULSE = "lg_thermav_r290_event"
