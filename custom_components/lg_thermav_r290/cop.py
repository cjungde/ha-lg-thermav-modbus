"""COP of the moment from the unit's own power registers.

Thermal power (input 48) divided by an electrical power, both read with the
energy registers option. Unlike the cumulative heating COP this is the COP of
the moment, and it covers whatever the unit is doing right now, space heating
or DHW. Two variants:

- current: over the heat pump's electrical power (input 36)
- system: over the total system's electrical power (input 34), which also
  counts what the heat pump alone does not, e.g. a backup heater

Deliberately free of Home Assistant imports so the calculation can be tested
without a Home Assistant install, like energy.py.
"""

from __future__ import annotations

# Unique ids of the two sensors. They carry the energy prefix, so they are
# removed with the energy sensors when the option is switched off.
COP_CURRENT_KEY = "energy_reg_cop_current"
COP_SYSTEM_KEY = "energy_reg_cop_system"
THERMAL_POWER_KEY = "energy_reg_thermal_power"  # input 48-49, W
ELECTRICAL_POWER_KEY = "energy_reg_power_heat_pump"  # input 36-37, W
ELECTRICAL_POWER_SYSTEM_KEY = "energy_reg_power_total_system"  # input 34-35, W

# Below this electrical power the unit is idling (controller, pumps on
# standby): there is no meaningful COP, and dividing a little residual heat
# by a few watts would produce wild values. No value is reported then.
MIN_ELECTRICAL_POWER_W = 100


def current_cop(thermal_w: int | None, electrical_w: int | None) -> float | None:
    """COP of the moment, or None while the unit is not really running.

    None, not 0, while either value is missing or the electrical power is
    below MIN_ELECTRICAL_POWER_W, so idle periods do not drag down the
    long-term statistics.
    """
    if thermal_w is None or electrical_w is None:
        return None
    if electrical_w < MIN_ELECTRICAL_POWER_W:
        return None
    return round(thermal_w / electrical_w, 2)
