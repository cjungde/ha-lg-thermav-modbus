"""COP and thermal power calculations.

Four COP sensors, created with the energy registers option:

- COP (Reported): the unit's thermal power (input 48) over the heat pump's
  electrical power (input 36), the COP of the moment
- COP System (Reported): the same over the total system's electrical power
  (input 34), which also counts e.g. a backup heater
- COP (Calculated): thermal power from flow rate × ΔT (thermal_power_w) over
  input 36, a cross-check of the unit's own thermal figure
- COP Heating (Cumulative): the unit's cumulative thermal over electrical
  energy for space heating (input 50 / 40), a long-term average

Note that the electrical values the unit reports tend to be too high, so these
COPs tend to come out too low (README, energy registers).

Deliberately free of Home Assistant imports so the calculations can be tested
without a Home Assistant install, like energy.py.
"""

from __future__ import annotations

# Entity keys (docs/naming.md).
KEY_COP_REPORTED = "cop_reported"
KEY_COP_SYSTEM_REPORTED = "cop_system_reported"
KEY_COP_CALCULATED = "cop_calculated"
KEY_COP_HEATING_CUMULATIVE = "cop_heating_cumulative"
COP_KEYS = (
    KEY_COP_REPORTED,
    KEY_COP_SYSTEM_REPORTED,
    KEY_COP_CALCULATED,
    KEY_COP_HEATING_CUMULATIVE,
)

# Below this electrical power the unit is idling (controller, pumps on
# standby): there is no meaningful COP, and dividing a little residual heat
# by a few watts would produce wild values. No value is reported then.
MIN_ELECTRICAL_POWER_W = 100

# Specific heat capacity of water [J/(kg·K)] × density [kg/l] = J/(l·K).
CP_WATER = 4186.0


def instantaneous_cop(thermal_w: int | None, electrical_w: int | None) -> float | None:
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


def cumulative_cop(thermal_wh: int | None, electrical_wh: int | None) -> float | None:
    """Cumulative COP: thermal energy over electrical energy.

    Both counters run since the unit's counters were last reset, so this is a
    long-term average (closer to a seasonal performance factor), not the COP
    of the moment. None while either counter is missing or no electrical
    energy has been counted yet, rather than a 0 that would read as a
    terrible COP and pull down long-term statistics.
    """
    if thermal_wh is None or electrical_wh is None or electrical_wh <= 0:
        return None
    return round(thermal_wh / electrical_wh, 2)


def thermal_power_w(
    flow_l_min: float | None, inlet_c: float | None, outlet_c: float | None
) -> int | None:
    """Thermal power from flow and ΔT: Q = flow/60 × (outlet − inlet) × 4186 W.

    None while any input is missing. Never negative: a reversed ΔT (defrost,
    cooling) gives 0, as the calculated thermal power sensors always have.
    """
    if flow_l_min is None or inlet_c is None or outlet_c is None:
        return None
    power = float(flow_l_min) / 60.0 * (float(outlet_c) - float(inlet_c)) * CP_WATER
    return max(0, int(round(power)))
