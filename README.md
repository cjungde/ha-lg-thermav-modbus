# LG ThermaV R290 — Home Assistant Integration

<p align="center"><img src="https://raw.githubusercontent.com/cjungde/ha-lg-thermav-modbus/main/custom_components/lg_thermav_r290/brand/icon.png" alt="LG ThermaV R290" width="128"></p>

HACS custom integration for the LG ThermaV R290 heat pump via Modbus TCP or RTU.

Replaces a hand-crafted YAML Modbus configuration with native HA entities: sensors, binary sensors, switches, buttons, number inputs, and select dropdowns — all updated on every poll cycle without requiring template sensors or automations.

---

## Features

- **Sensors** — temperatures (inlet, outlet, DHW, outdoor, refrigerant circuit), flow rate, pressures, compressor speed, error code, operation mode, control method, energy state
- **Computed thermal power sensors** — total / heating circuit / DHW, calculated from flow rate and ΔT each poll cycle (Q = flow/60 × ΔT × 4186 W)
- **Binary sensors** — compressor, pumps, DHW heating, defrost, backup heater stages, fault, silent mode, cooling, emergency modes, energy state slots 0–8
- **Switches** — main power, DHW, silent mode, emergency stop
- **Buttons** — start DHW disinfection (momentary trigger coil)
- **Number inputs** — flow temperature setpoints (circuit 1, circuit 2), DHW target temperature, heating curve shift values (circuit 1, circuit 2)
- **Select inputs** — operation mode (Heating / Cooling / Auto), control method (outlet temp / inlet temp / room air)
- Supports **Modbus TCP**, **Modbus TCP-RTU**, and **Modbus RTU** (serial)
- Configurable poll interval (default 30 s), reconfigurable without restart
- Shares one Modbus connection with every other integration on the same gateway

---

## Coming from basti242's YAML setup?

[Entity translation table](docs/migration-from-yaml.md): every entity of [basti242/homeassistant_lg_therma_v_modbus](https://github.com/basti242/homeassistant_lg_therma_v_modbus) next to its counterpart here, including the differences that matter when switching (inverted water-flow bit, missing write entities).

---

## Experimental registers

The device answers on 18 registers that the manual does not list (a read-only scan on 2026-10-03, R290 9 kW):

| Type | Registers |
|---|---|
| Input | 30015, 30018, 30064 |
| Holding | 40011–40023, 40063, 40064 |

Nothing in the manual or in the community projects I could find explains them. To find out what they are, the integration can record them over a longer time.

Switch it on under *Settings → Devices & Services → LG ThermaV R290 → Configure → Experimental registers*. This adds 18 diagnostic sensors named `Experimental Input 30015`, `Experimental Holding 40011`, … They carry the raw, unscaled 16-bit value and have long-term statistics, so they can be compared with compressor speed, temperatures and defrost cycles. Switching the option off removes them again.

**They are read-only.** The integration only ever writes a fixed list of known addresses (holding 0, 1, 2, 4, 5, 7, 8, 23, 24 and coils 0–4 and 6 — the last of each being the optional limits below); every other write is refused before it reaches the bus, so none of these registers can be written by the integration, whichever entity or service asks. A register that stops answering leaves its sensor empty and does not affect the other values.

The full result of the scan, what the manual lists and what it does not, is in [docs/register-scan.md](docs/register-scan.md).

Please tell me what you see, in particular if the values move with the compressor. A first reading from my unit: input 30015 reads 64887 (−64.9 °C as a signed tenth, the pattern of a temperature channel without a sensor), input 30018 reads 12000, and all of holding 40011–40023 read 0.

---

## Optional limits — detected per device

Three addresses from the manual are served by some units and not by others:

| Entity | Address | Range |
|---|---|---|
| `number.lg_thermav_r290_max_compressor_modulation` | Holding 23 (40024) | 0–100 %, 0 = no limit |
| `number.lg_thermav_r290_power_limit` | Holding 24 (40025) | 0.1–25.0 kW |
| `switch.lg_thermav_r290_power_limit_enable` | Coil 6 (00007) | whether the unit obeys the power limit |

No two of the units reported so far agree. A 12 kW unit serves holding 23; the
manual of an HM071HF UB40 lists coil 6 and holding 24 but not holding 23; and on
the HN1639HC NK0 this integration was written against, all three stay silent
(measured 2026-10-03 and again 2026-10-17, with holding 22 and coil 5 answering
in the same second as a control).

So the integration asks the device instead of assuming. **An entity exists only
where the unit answered** — a slider that can never show a value and whose write
goes nowhere is worse than an absent one. Nothing has to be configured.

What was found is shown by the diagnostic sensor **Optional Registers**: its
state is how many of the three answered, and its attributes give each one's
verdict plus `source`, which says where that verdict came from:

| `source` | Meaning |
|---|---|
| `hit` | read from the stored result; the device confirmed it is the same one |
| `positive_only` | the unit does not report its identity (input 9997/9998 are optional too), so a stored "not served" was discarded and asked again. A `false` here is this session's own measurement |
| `miss`, `definitions_changed`, `identity_changed` | nothing was believed; all three were asked in this session |

### Why the result is stored

An address this device family does not serve is not refused — it is **not
answered at all**. Every probe therefore costs a full request timeout, which
this integration raises to 20 s because it shares its Modbus connection. The
result is written to Home Assistant storage, keyed by host, port and slave id,
and read back on every later start, so the cost arises once per installation.

Two safeguards come with that:

- A probe runs **only right after a complete, successful poll**. A dead gateway
  times out exactly like an unserved address, and that poll is the witness that
  the link was alive. Without it an unplugged cable would be remembered as
  missing hardware.
- At most **one probe per cycle**. A unit serving none of the three would
  otherwise stall the bus for a full minute in a single poll — and everything
  else on that bus with it.

If a unit gains the feature through a firmware update, delete and re-add the
integration, or remove the `*.lg_thermav_r290_capabilities` file from
`.storage`; the next start asks again.

> **Coil 5 (00006) is deliberately left out.** It triggers emergency operation,
> which runs the machine outside its normal control. The write guard refuses it,
> and that is documented in the code so it is not mistaken for an oversight.

---

## Requirements

**Home Assistant 2026.10.0 or newer.** From version 1.0.0 the integration no
longer speaks to the bus itself. It asks Home Assistant's `modbus` component
for a unit on a *shared* connection, which means:

The floor is **2026.10**, not the 2026.9 that first shipped `async_get_unit`.
One call decides it: the coordinator asks its unit for a 20-second timeout
floor through `require_timeout`, and that method does not exist in the
`modbus-connection` 4.10.0 which the whole 2026.9 line pins — it arrived in
4.12.3, and 2026.10 pins 4.12.4. Without the floor a shared connection keeps
the library default of 10 s, which is too tight once several consumers
serialize behind one lock.

- Every integration pointing at the same gateway with the same link settings
  ends up on one connection, and their requests serialize behind its lock.
  This matters on RS485, where the line can only carry one conversation at a
  time: two clients with two sockets onto one gateway interleave their
  requests and provoke transaction-id mismatches and framing errors that hit
  *both* of them.
- The Modbus stack is Home Assistant's own (`modbus-connection` on the tmodbus
  backend), so nothing is installed into the container on our behalf. The
  `requirements` list in the manifest is empty.
- The same device may not be claimed twice with different link settings —
  plain TCP and RTU-over-TCP on one socket, say. The config flow reports that
  as an error rather than silently reframing.

---

## Installation via HACS

1. In HACS → Integrations → ⋮ → Custom repositories, add `https://github.com/cjungde/ha-lg-thermav-modbus` with category **Integration**.
2. Install "LG ThermaV R290".
3. Restart Home Assistant.
4. Settings → Devices & Services → Add Integration → search "LG ThermaV R290".

### Manual installation

Copy the `custom_components/lg_thermav_r290/` folder into your HA `custom_components/` directory and restart.

---

## Configuration

The config flow asks for connection type first, then connection-specific parameters:

| Parameter | Default | Notes |
|---|---|---|
| Connection type | — | TCP / TCP-RTU / RTU |
| Host / IP | — | TCP only |
| Port | 502 | TCP only |
| Serial port | — | RTU only (e.g. `/dev/ttyUSB0`) |
| Baudrate | 9600 | RTU only |
| Parity | N | RTU only |
| Stop bits | 1 | RTU only |
| Slave ID | 1 | 1–247 |
| Poll interval | 30 s | Adjustable in Options |

---

## Entities

### Sensors

| Entity | Description | Unit |
|---|---|---|
| `sensor.lg_thermav_r290_inlet_temperature` | Inlet water temperature | °C |
| `sensor.lg_thermav_r290_outlet_temperature` | Outlet water temperature | °C |
| `sensor.lg_thermav_r290_dhw_temperature` | DHW tank temperature | °C |
| `sensor.lg_thermav_r290_outdoor_temperature` | Outdoor air temperature | °C |
| `sensor.lg_thermav_r290_backup_heater_outlet_temperature` | Backup heater outlet temp | °C |
| `sensor.lg_thermav_r290_flow_temperature_circuit_2` | Flow temperature circuit 2 | °C |
| `sensor.lg_thermav_r290_flow_rate` | Water flow rate | l/min |
| `sensor.lg_thermav_r290_water_pressure` | Water pressure | bar |
| `sensor.lg_thermav_r290_high_pressure_condenser` | High pressure (condenser) | bar |
| `sensor.lg_thermav_r290_low_pressure_evaporator` | Low pressure (evaporator) | bar |
| `sensor.lg_thermav_r290_compressor_speed` | Compressor speed | rpm |
| `sensor.lg_thermav_r290_error_code` | Error code | — |
| `sensor.lg_thermav_r290_thermal_power_total` | Total thermal power output | W |
| `sensor.lg_thermav_r290_thermal_power_heating_circuit` | Heating circuit thermal power | W |
| `sensor.lg_thermav_r290_thermal_power_dhw` | DHW thermal power | W |
| `sensor.lg_thermav_r290_operation_mode` | Operation mode (label) | — |
| `sensor.lg_thermav_r290_control_method` | Control method (label) | — |
| `sensor.lg_thermav_r290_energy_state` | Energy state (label) | — |

### Binary sensors

| Entity | Description |
|---|---|
| `binary_sensor.lg_thermav_r290_compressor` | Compressor running |
| `binary_sensor.lg_thermav_r290_water_pump` | Water pump running |
| `binary_sensor.lg_thermav_r290_external_water_pump` | External water pump |
| `binary_sensor.lg_thermav_r290_dhw_heating` | DHW heating active |
| `binary_sensor.lg_thermav_r290_defrost` | Defrost active |
| `binary_sensor.lg_thermav_r290_dhw_disinfection` | DHW disinfection |
| `binary_sensor.lg_thermav_r290_backup_heater_step_1` | Backup heater step 1 |
| `binary_sensor.lg_thermav_r290_backup_heater_step_2` | Backup heater step 2 |
| `binary_sensor.lg_thermav_r290_dhw_boost_heater` | DHW boost heater |
| `binary_sensor.lg_thermav_r290_fault` | Fault active |
| `binary_sensor.lg_thermav_r290_silent_mode` | Silent mode |
| `binary_sensor.lg_thermav_r290_cooling_active` | Cooling active |
| `binary_sensor.lg_thermav_r290_water_flow` | Water flow present (see note below) |
| `binary_sensor.lg_thermav_r290_energy_state_normal_operation` | Energy state: normal (value 2) |
| … | Energy states 0–8 as individual binary sensors |

> **Note on discrete input 10001 (water flow).** The LG manual documents this bit as
> `0 = flow rate OK / 1 = flow rate too low`. On the R290 monoblock it behaves the
> other way round: the bit is set while water is flowing. Measured on 2026-08-18 —
> `di[0] = 0` at 5.0 LPM with the pump off, `di[0] = 1` at 15.3 and 29.5 LPM with the
> pump running, with `di[0]` and `di[1]` (pump) identical in every sample of the same
> poll. A read offset is ruled out, since `di[3]` (compressor) and `di[5]` (DHW heating)
> stay correctly aligned.
>
> The entity is therefore exposed as `binary_sensor.lg_thermav_r290_water_flow` with
> device class `running`. Exposing it as a `problem` sensor (as the manual suggests)
> would raise a false problem alert on every pump run.

> **Note on discrete input 10009 (cooling status).** The R290 manual (p. 158,
> *Diskretes Register 0x02*) documents this bit as `0 = no cooling / 1 = cooling
> operation`. On this unit the bit is set **while the heat pump is heating**.
> Measured on 2026-09-24: `di[8] = 1` with the compressor running, flow 37.8 °C
> above return 35.7 °C and 3487 W going into the heating circuit, operation mode
> `Auto`, no cooling anywhere in the system.
>
> A read offset is ruled out. `di[1]`/`di[2]` tracked a 3-minute-on / 15-minute-off
> pump cycle correctly to the second, `di[3]` (compressor) is consistent over days,
> and `di[13]`–`di[16]` match the R290 manual exactly (10014 fault, 10015 emergency
> space heating, 10016 emergency DHW, 10017 mix pump). Note that the memory map of
> other Therma V models differs here — on the HN1600MC, 10014 is *Emergency
> Operation Available (DHW)*. **Use the R290 manual, not a generic Therma V one.**
>
> The bit does not correlate with compressor state either: it stayed `on`
> continuously from 2026-09-21 22:03 to 2026-09-24 07:02 while the unit started and
> stopped repeatedly. What it actually reports on this model is unknown.
>
> The entity `binary_sensor.lg_thermav_r290_cooling_active` is therefore **not
> usable for diagnostics** on the R290 monoblock. It is left in place because the
> register is read anyway and the mapping follows the manual — but do not build
> automations on it.
>
> This is the **second** discrete input on this model that departs from the
> manufacturer's description, after 10001 above.

### Switches

| Entity | Modbus coil |
|---|---|
| `switch.lg_thermav_r290_heat_pump` | Coil 0 |
| `switch.lg_thermav_r290_dhw` | Coil 1 |
| `switch.lg_thermav_r290_silent_mode` | Coil 2 |
| `switch.lg_thermav_r290_emergency_stop` | Coil 4 |
| `switch.lg_thermav_r290_power_limit_enable` | Coil 6 — only where the unit serves it, see *Optional limits* |

### Buttons

Coil 3 is a momentary trigger, not a state switch. The manual specifies it as
`0: hold status / 1: start operation` — the unit clears the coil by itself after
the write, so reading it back is never a confirmation. Use the binary sensor to
see whether the operation actually started.

| Entity | Modbus coil | Status entity |
|---|---|---|
| `button.lg_thermav_r290_start_disinfection` | Coil 3 (trigger) | `binary_sensor.lg_thermav_r290_dhw_disinfection` (discrete 6) |

> A trigger coil modelled as a switch would always read back `off`, even when the
> write succeeded, which is why this is a button. Note that the trigger
> only has an effect if disinfection is enabled on the unit itself
> (installer menu → DHW → disinfection active; factory default is off).

### Number inputs

| Entity | Range | Holding register |
|---|---|---|
| `number.lg_thermav_r290_target_temperature_circuit_1_radiators` | 30–50 °C | 2 (×0.1) |
| `number.lg_thermav_r290_target_temperature_circuit_2_underfloor` | 20–40 °C | 5 (×0.1) |
| `number.lg_thermav_r290_dhw_target_temperature` | 35–60 °C | 8 (×0.1) |
| `number.lg_thermav_r290_setpoint_shift_circuit_1` | −5…+5 K | 4 (signed) |
| `number.lg_thermav_r290_setpoint_shift_circuit_2` | −5…+5 K | 7 (signed) |
| `number.lg_thermav_r290_max_compressor_modulation` | 0–100 % | 23 — only where the unit serves it |
| `number.lg_thermav_r290_power_limit` | 0.1–25.0 kW | 24 (×0.1) — only where the unit serves it |

### Select inputs

| Entity | Options | Holding register |
|---|---|---|
| `select.lg_thermav_r290_operation_mode` | Heating / Cooling / Auto | 0 |
| `select.lg_thermav_r290_control_method` | Outlet / Inlet Water Temp Control / Room Air Control | 1 |

---

## Modbus register map (summary)

| FC | Address range | Content |
|---|---|---|
| FC04 (input) | 0–24 | Temperatures, flow, pressures, compressor speed, error code |
| FC04 (input) | 9997–9998 | Product info, device group |
| FC03 (holding) | 0–9 | Operation mode, control method, setpoints, shift values, energy state |
| FC01 (coils) | 0–4 | Main switch, DHW, silent mode, disinfection trigger, emergency stop |
| FC02 (discrete) | 0–16 | Status bits (compressor, pumps, defrost, faults, …) |

---

## Notes

- Thermal power formula: `Q [W] = (flow_rate [l/min] / 60) × (outlet_temp − inlet_temp) [K] × 4186 [J/(l·K)]`
- `flow_rate` has a hard floor of **5.0 l/min** (input register 8 × 0.1, passed through unchanged). With the circulation pump stopped the device keeps reporting exactly 5.0 instead of 0; in a long-term statistics check (May–Oct 2026) the value was never below 5.0 and never between 5.0 and about 9, and every hour with a constant 5.0 had the compressor at 0 rpm. It is a device property, not an integration artefact: the flow sensor is a SIKA VVX20 (standard variant, measuring range 5–80 l/min), a vortex sensor that cannot measure below the start of its range, so 5.0 means "flow between 0 and 5 l/min, not measurable" rather than an actual 5 l/min. Thermal power calculated from flows just above the floor is correspondingly coarse. If you need a true zero, treat `flow_rate ≤ 5.0` with the compressor off as 0 in a template sensor — a threshold below 5 will not catch it. The thermal power sensors are practically unaffected because the outlet/inlet spread approaches 0 when the pump stands. If the circuits are set to continuous pump operation the pump never stops and the floor is no longer visible.
- Heating circuit / DHW split is based on the `di_dhw_heating` discrete input; when DHW is active the full flow is attributed to DHW and the heating circuit sensor reports 0, and vice versa.
- Shift values (holding regs 4, 7) are stored as two's-complement uint16; values ≥ 32768 are interpreted as negative.
- Tested on LG ThermaV R290 9 kW via Modbus TCP, slave ID 33.
- `tools/make_shadow.py` builds a read-only copy of the integration under a
  second domain so a change to the Modbus layer can be measured against the
  running one on the same hardware. See `tools/README.md`.

---

## License

MIT
