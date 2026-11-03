"""The flow rate as a number that means what it says.

The unit's flow sensor (a SIKA VVX20 vortex meter, 5-80 L/min) cannot
measure below the start of its range. With the circulation pump stopped it
does not report 0 but exactly 5.0 L/min. Measured on a 12 kW unit
(2026-08-18, see the discrete inputs in coordinator.py): 5.0 L/min with
*Water Flow* (discrete 10001) and *Water Pump* (10002) both off, 15.3 and
29.5 L/min with both on. cjungde measured the same on a 9 kW unit.

Taken at face value, those 5.0 L/min turn any ΔT between inlet and outlet
into thermal power that is not there: 0.5 K already reads as about 175 W,
and the calculated COP and the integrated thermal energy count it too. So
while the unit itself says there is no flow and the pump is off, and the
register sits at the bottom of the sensor's range, the flow rate is 0. The
register value stays available as the sensor's ``register_value`` attribute.

Deliberately free of Home Assistant imports, like cop.py.
"""

from __future__ import annotations

#: The bottom of the flow sensor's measuring range, in L/min.
SENSOR_FLOOR = 5.0


def flow_rate(
    register: float | None, water_flow: int | None, water_pump: int | None
) -> float | None:
    """The flow rate to report for the register value and the two inputs.

    0.0 only when all three agree that nothing flows: the register at (or
    below) the sensor's floor, and both discrete inputs off. Anything else,
    a missing input included, keeps the register value.
    """
    if register is None:
        return None
    if water_flow == 0 and water_pump == 0 and register <= SENSOR_FLOOR:
        return 0.0
    return register
