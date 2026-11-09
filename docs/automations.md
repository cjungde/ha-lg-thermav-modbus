# Example automations: a heating day with AutoTemp

Three automations, each in its own file, that run circuit 1 (radiators) through the day so the compressor starts once in the morning and then keeps running at low speed instead of switching on and off:

| Time | Automation | What happens |
|---|---|---|
| 08:00 | [Start](#start-0800) | Heating on, outlet control, 60 °C: the compressor starts reliably |
| ~08:01 | [AutoTemp](#autotemp) (cold start) | While the inlet is below 22 °C: stays on outlet control, setpoint just below the outlet temperature, the compressor throttles to minimum |
| inlet ≥ 22 °C | [AutoTemp](#autotemp) (kick-in) | Inlet control, setpoint just below the inlet temperature |
| until 17:00 | [AutoTemp](#autotemp) | The setpoint follows the inlet temperature, a morning ramp pulls it to 33–38 °C by 13:00, frost protection and oil boost as needed |
| 17:00 | – | AutoTemp stops; the setpoint stays where it is |
| 18:00 | [Stop](#stop-1800) | Setpoint 20 °C, max compressor modulation 40 %: the unit reaches thermo off and AutoTemp treats it as off |

They were written for a 12 kW unit. Entity ids are the defaults (`…lg_therma_v_r290_…`); if you renamed yours, adjust them. The stop automation needs the *Max compressor modulation* option; leave its second action out without it. The start and stop times can be changed freely: AutoTemp takes over 1 minute after the compressor starts, whenever that is (before 17:00), and stops as soon as the setpoint is at 20 °C.

**To use them:** open the file, copy its content, then *Settings → Automations & scenes → Create automation → Create new automation → ⋮ → Edit in YAML*, paste, *Save*.

## Before you start: the thermo on/off hysteresis and the lowest setpoint

The unit switches the compressor off when the water it regulates on (the inlet or the outlet, depending on the control method) is the hysteresis above the setpoint, and on again when it is the hysteresis below it. The hysteresis is set in the installer menu of the wired remote, *Th On/Off Variable, Heating Water*, in steps of 1–4 °C; it is not available over Modbus.

AutoTemp keeps the setpoint so close to the water temperature that the unit never reaches thermo off. It is tuned for **±4 °C**: it raises the setpoint at +2.8 °C and always at +3 °C, a margin of 1 °C. With a smaller hysteresis, lower `up_gap`, `emergency_gap` and `frost_max_gap` so they stay below it.

The lowest heating setpoint the unit accepts is **20 °C** with the backup heater switched off; lower values are stored as 20 °C. AutoTemp therefore uses 20 °C as "off" and never sets less than 21 °C (`floor`) itself.

## Start (08:00)

The YAML is its own file: [therma-v-start.yaml](therma-v-start.yaml).

It switches heating on, sets **outlet control** and the circuit 1 setpoint to 60 °C, so the compressor starts reliably. The time is in its trigger (`at: '08:00:00'`).

The start must set **outlet control**: the cold start and the kick-in only take over from there.

## AutoTemp

The YAML is its own file: [autotemp-heat-circuit-1.yaml](autotemp-heat-circuit-1.yaml). Everything worth tuning is at the top (`trigger_variables`) or the bottom (`variables`) of it.

What it does until 17:00 while the compressor runs:

- **Cold start.** Once the compressor has run 1 minute on outlet control (the warm-up of the start automation) and the inlet is still below `inlet_switch` (22 °C), it stays on outlet control and keeps the setpoint just below the outlet temperature (outlet rounded down − 1, at least `floor`), adjusting it on every change. The water is then slightly above the setpoint, so the unit throttles to about minimum speed and takes little heat from the cold morning air. On inlet control this is not possible while the inlet is below 21 °C: the setpoint cannot go below the inlet, so the unit would run at noticeable power until the water is warm.
- **Kick-in.** Once the inlet reaches `inlet_switch`, it switches to inlet control and sets the setpoint just below the inlet temperature (inlet − 1, at least `floor` and the ramp). Inlet control first, then the setpoint: the other way round the unit would briefly be on outlet control with a low setpoint, which is thermo off. If the inlet is already at 22 °C or above at the start, the kick-in follows the 1-minute warm-up directly.
- **Follow the inlet.** The setpoint goes up 1 °C when the inlet has been `up_gap` (2.8 °C) above it for 20 seconds, and down 1 °C when the inlet has been `down_gap` (1 °C) below it for 5 minutes. The two thresholds are far enough apart that it does not bounce. From `emergency_gap` (3 °C) above, it raises in any case.
- **Morning ramp.** A minimum setpoint rises from `floor` at 09:00 to a target at 13:00 and is then held: 38 °C at 0 °C outside, 33 °C at 15 °C outside, linear in between (outdoor temperature of the unit). The setpoint never goes below it, so the house is warm by the afternoon even if it takes up a lot of heat.
- **Frost protection.** While the air after the evaporator (`temperature_after_evaporator`) is below `frost_limit` (1 °C), it does not raise but lowers the setpoint every 2 minutes, so the unit throttles and takes less heat from the air. It stops lowering once the inlet would be more than `frost_max_gap` above the setpoint, keeping the margin to thermo off.
- **Defrost.** During a defrost and for 5 minutes after it, nothing happens: the defrost cools the water, and the dip would otherwise lower the setpoint.
- **Oil boost.** After about 60 minutes below roughly 1500 rpm the unit spins the compressor up to about 3600 rpm for a moment to bring the compressor oil back (oil return). After 55 minutes below `low_rpm`, AutoTemp raises the setpoint to inlet + 3 °C (up to `boost_ceiling`, 45 °C), waits until the compressor has been at or above `low_rpm` for 60 seconds, then sets it to 2 °C below the inlet so the compressor slows down again. Running above 1500 rpm appears to reset the unit's count, so the hard spike is replaced by a few minutes at about 1700 rpm.
- **Off.** At or below `off_setpoint` (20 °C) it does nothing at all. Setting the slider to 20 °C (its lowest position) by hand switches the unit off for the rest of the day without AutoTemp working against it; this also ends a running oil boost.

It re-checks every 5 minutes, so it catches up after a restart of Home Assistant or after being switched on again.

### What to know

- **The oil boost is a finding from one unit, not documented by LG.** On the 12 kW unit it was written on, it avoids the hourly spikes as long as the speed stays clearly below 1500 rpm; when the speed sits right at 1500 rpm the unit still counts it as low. If the spikes still come, try a higher `low_rpm` (e.g. 1600) and a shorter wait in the `oil_boost` trigger (e.g. 50 minutes). *Settings → Automations → AutoTemp → ⋮ → Traces* shows each run with the trigger, the branch taken and the values it saw.
- **The cold start ignores the ramp, frost protection and the oil boost.** It usually lasts only until the inlet reaches 22 °C. If even the outlet is below 22 °C, the setpoint stays at 21 °C and the unit runs harder until the outlet passes it.
- **Switching to outlet control by hand during the day** is undone within a minute once the inlet is at 22 °C or above (kick-in); below that, AutoTemp follows the outlet. Set the slider to 20 °C or switch the automation off first.
- **After 17:00 it does nothing.** Between 17:00 and the stop nothing adjusts the setpoint, and the unit may reach thermo off or do an oil-return run on its own. A start after 17:00 stays on outlet control at 60 °C until the stop.
- **Error log entries while the editor is open.** With the automation open in the editor, Home Assistant may log `'speed_entity' is undefined` for the two templates of the oil boost's `wait_for_trigger`: the editor subscribes to them without the automation's variables. When the automation runs, they have them.

## Stop (18:00)

The YAML is its own file: [therma-v-stop.yaml](therma-v-stop.yaml).

It sets the circuit 1 setpoint to 20 °C, the unit's lowest value with the backup heater off: with inlet control and a hysteresis of ±4 °C the unit switches off once the inlet is at 24 °C, which after a day of heating it always is. 20 °C is also "off" for AutoTemp, so it stops adjusting at once, even before 17:00. Heating stays switched on, so on a very cold night the unit restarts when the inlet drops below 16 °C and heats until it is back at 24 °C (safety net). It also resets the max compressor modulation to 40 %, in case it was raised by hand on a cold day. The time is in its trigger (`at: '18:00:00'`).
