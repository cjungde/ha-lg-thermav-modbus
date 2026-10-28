# Example automations: a heating day with AutoTemp

Three automations that run circuit 1 (radiators) through the day so the compressor starts once in the morning and then keeps running at low speed instead of switching on and off:

| Time | Automation | What happens |
|---|---|---|
| 08:00 | [Start](#start-0800) | Heating on, outlet control, 60 °C: the compressor starts reliably |
| ~08:05 | [AutoTemp](#autotemp) (kick-in) | Inlet control, setpoint just below the inlet temperature |
| 08:05–17:00 | [AutoTemp](#autotemp) | The setpoint follows the inlet temperature, a morning ramp pulls it to 33–38 °C by 13:00, frost protection and oil boost as needed |
| 17:00 | – | AutoTemp stops; the setpoint stays where it is |
| 18:00 | [Stop](#stop-1800) | Setpoint 20 °C, max compressor modulation 40 %: the unit reaches thermo off |

They were written for a 12 kW unit. Entity ids are the defaults (`…lg_therma_v_r290_…`); if you renamed yours, adjust them. The stop automation needs the *Max compressor modulation* option; leave its second action out without it.

**To use them:** *Settings → Automations & scenes → Create automation → Create new automation → ⋮ → Edit in YAML*, paste, *Save*.

## Before you start: the thermo on/off hysteresis

The unit switches the compressor off when the water it regulates on (here the inlet) is the hysteresis above the setpoint, and on again when it is the hysteresis below it. The hysteresis is set in the installer menu of the wired remote, *Th On/Off Variable, Heating Water*, in steps of 1–4 °C; it is not available over Modbus.

AutoTemp keeps the setpoint so close to the inlet temperature that the unit never reaches thermo off. It is tuned for **±4 °C**: it raises the setpoint at +2.5 °C and always at +3 °C, a margin of 1 °C. With a smaller hysteresis, lower `up_gap`, `emergency_gap` and `frost_max_gap` so they stay below it.

## Start (08:00)

```yaml
alias: Therma V start (warm-up)
description: >-
  Daily start of the heat pump at 08:00. Switches heating on, sets the control
  method to Outlet Water Temp Control and the circuit 1 setpoint to 60 °C, so
  the compressor starts reliably and the water warms up quickly. After the
  compressor has run for 5 minutes, AutoTemp_Heat_Circuit_1 takes over: it
  switches to Inlet Water Temp Control and regulates the setpoint for the rest
  of the day (08:00–17:00). The max compressor modulation is not changed here;
  it stays at the 40 % set by the stop automation unless raised by hand.
triggers:
  - trigger: time
    at: '08:00:00'
conditions: []
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.lg_therma_v_r290_heating_cooling
  - action: select.select_option
    target:
      entity_id: select.lg_therma_v_r290_control_method
    data:
      option: Outlet Water Temp Control
  - action: number.set_value
    target:
      entity_id: number.lg_therma_v_r290_target_temperature_circuit_1_radiators
    data:
      value: 60
mode: single
```

## AutoTemp

The YAML is its own file: [autotemp-heat-circuit-1.yaml](autotemp-heat-circuit-1.yaml). Everything worth tuning is at the top (`trigger_variables`) or the bottom (`variables`) of it.

What it does, between 08:00 and 17:00 while the compressor runs:

- **Kick-in.** Once the compressor has run 5 minutes on outlet control (the warm-up of the start automation), it switches to inlet control and sets the setpoint just below the inlet temperature (inlet − 1, at least `floor`). Inlet control first, then the setpoint: the other way round the unit would briefly be on outlet control with a low setpoint, which is thermo off.
- **Follow the inlet.** The setpoint goes up 1 °C when the inlet has been `up_gap` (2.5 °C) above it for 20 seconds, and down 1 °C when the inlet has been `down_gap` (1 °C) below it for 5 minutes. The two thresholds are far enough apart that it does not bounce. From `emergency_gap` (3 °C) above, it raises in any case.
- **Morning ramp.** A minimum setpoint rises from `floor` at 08:30 to a target at 13:00 and is then held: 38 °C at 0 °C outside, 33 °C at 15 °C outside, linear in between (outdoor temperature of the unit). The setpoint never goes below it, so the house is warm by the afternoon even if it takes up a lot of heat.
- **Frost protection.** While the air after the evaporator (`temperature_after_evaporator`) is below `frost_limit` (1 °C), it does not raise but lowers the setpoint every 2 minutes, so the unit throttles and takes less heat from the air. It stops lowering once the inlet would be more than `frost_max_gap` above the setpoint, keeping the margin to thermo off.
- **Defrost.** During a defrost and for 5 minutes after it, nothing happens: the defrost cools the water, and the dip would otherwise lower the setpoint.
- **Oil boost.** After about 60 minutes below roughly 1500 rpm the unit spins the compressor up to about 3600 rpm for a moment to bring the compressor oil back (oil return). After 55 minutes below `low_rpm`, AutoTemp raises the setpoint to inlet + 3 °C (up to `boost_ceiling`, 45 °C), waits until the compressor has been at or above `low_rpm` for 60 seconds, then sets it to 2 °C below the inlet so the compressor slows down again. Running above 1500 rpm appears to reset the unit's count, so the hard spike is replaced by a few minutes at about 1700 rpm.
- **Off.** At or below `off_setpoint` (20 °C) it does nothing at all. Setting the slider to 20 °C by hand switches the unit off for the rest of the day without AutoTemp working against it; this also ends a running oil boost.

It re-checks every 5 minutes, so it catches up after a restart of Home Assistant or after being switched on again.

### What to know

- **The oil boost is a finding from one unit, not documented by LG.** On the 12 kW unit it was written on, it avoids most hourly spikes but not all: when the speed sits right at 1500 rpm the unit still counts it as low, and 55 minutes leaves little margin. If the spikes still come, try a higher `low_rpm` (e.g. 1600) and a shorter wait in the `oil_boost` trigger (e.g. 50 minutes). *Settings → Automations → AutoTemp → ⋮ → Traces* shows each run with the trigger, the branch taken and the values it saw.
- **Switching to outlet control by hand during the day** is undone after 5 minutes (kick-in). Set the slider to 20 °C or switch the automation off first.
- **Outside 08:00–17:00 it does nothing.** Started earlier, the unit stays on outlet control at 60 °C until 08:00; between 17:00 and 18:00 nothing adjusts the setpoint and the unit may reach thermo off on its own.
- **Error log entries while the editor is open.** With the automation open in the editor, Home Assistant may log `'speed_entity' is undefined` for the two templates of the oil boost's `wait_for_trigger`: the editor subscribes to them without the automation's variables. When the automation runs, they have them.

## Stop (18:00)

```yaml
alias: Therma V stop (setpoint 20 °C, modulation 40 %)
description: >-
  Daily shutdown of the heat pump at 18:00. Sets the circuit 1 setpoint to
  20 °C: with Inlet Water Temp Control and a thermo on/off hysteresis of ±4 °C,
  the unit switches off once the inlet is at 24 °C, which after a day of
  heating it always is, so the compressor stops right away. Heating stays
  switched on, so on a very cold night the unit restarts when the inlet drops
  below 16 °C and heats until it is back at 24 °C (safety net against the
  house cooling down too far). Also resets the max compressor modulation to
  40 %, in case it was raised by hand on a cold day, so the next day starts at
  40 % again. AutoTemp_Heat_Circuit_1 is not active after 17:00 and does not
  interfere.
triggers:
  - trigger: time
    at: '18:00:00'
conditions: []
actions:
  - action: number.set_value
    target:
      entity_id: number.lg_therma_v_r290_target_temperature_circuit_1_radiators
    data:
      value: 20
  - action: number.set_value
    target:
      entity_id: number.lg_therma_v_r290_max_compressor_modulation
    data:
      value: 40
mode: single
```
