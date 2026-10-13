# LG ThermaV R290 — Home Assistant Integration

<p align="center"><img src="https://raw.githubusercontent.com/cjungde/ha-lg-thermav-modbus/main/custom_components/lg_thermav_r290/brand/icon.png" alt="LG ThermaV R290" width="128"></p>

HACS custom integration for the LG ThermaV R290 heat pump via Modbus TCP or RTU.

Replaces a hand-crafted YAML Modbus configuration with native HA entities: sensors, binary sensors, switches, buttons, number inputs, and select dropdowns — all updated on every poll cycle without requiring template sensors or automations.

---

## Features

- **Sensors** — temperatures (inlet, outlet, DHW, outdoor, refrigerant circuit), flow rate, pressures, compressor speed, error code, operation mode, control method, energy state
- **Energy registers (optional)** — electrical power, cumulative electrical energy per mode, demand vs. supply and the unit's own thermal power from input registers 34–51; off by default, see [Energy registers](#energy-registers-optional)
- **Computed thermal power sensors** — total / heating circuit / DHW, calculated from flow rate and ΔT each poll cycle (Q = flow/60 × ΔT × 4186 W)
- **Binary sensors** — compressor, pumps, DHW heating, defrost, backup heater stages, fault, silent mode, cooling, emergency modes, energy state slots 0–8
- **Switches** — main power, DHW, silent mode, emergency stop
- **Buttons** — start DHW disinfection (momentary trigger coil)
- **Number inputs** — flow temperature setpoints (circuit 1, circuit 2), DHW target temperature, heating curve shift values (circuit 1, circuit 2); optional max compressor modulation (40–100 %)
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

**They are read-only.** The integration only ever writes a fixed list of known addresses (holding 0, 1, 2, 4, 5, 7, 8 and coils 0–4, plus holding 23 while the compressor modulation limit option is on); every other write is refused before it reaches the bus, so none of these registers can be written by the integration, whichever entity or service asks. A register that stops answering leaves its sensor empty and does not affect the other values.

The full result of the scan, what the manual lists and what it does not, is in [docs/register-scan.md](docs/register-scan.md).

Please tell me what you see, in particular if the values move with the compressor. A first reading from my unit: input 30015 reads 64887 (−64.9 °C as a signed tenth, the pattern of a temperature channel without a sensor), input 30018 reads 12000, and all of holding 40011–40023 read 0.

---

## Requirements

**Home Assistant 2026.9.0 or newer.** From version 1.0.0 the integration no
longer speaks to the bus itself. It asks Home Assistant's `modbus` component
for a unit on a *shared* connection, which means:

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
| Energy registers | off | Options; input 34–51, not served by every unit |
| Compressor modulation limit | off | Options; holding 23, not served by every unit |

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

### Energy registers (optional)

Switch on **Energy registers** in the integration's options. These are 32-bit values in input registers 34–51 that the manual does not list. Not every unit serves them: a read-only scan of a 9 kW unit got no answer from input 25–62, while a 12 kW unit answers on 34–51.

| Entity | Registers | Unit |
| --- | --- | --- |
| `sensor.lg_thermav_r290_electrical_power_total_system` | 34–35 | W |
| `sensor.lg_thermav_r290_electrical_power_heat_pump` | 36–37 | W |
| `sensor.lg_thermav_r290_electrical_energy_total` | 38–39 | Wh (shown as kWh) |
| `sensor.lg_thermav_r290_electrical_energy_space_heating` | 40–41 | Wh (shown as kWh) |
| `sensor.lg_thermav_r290_electrical_energy_space_cooling` | 42–43 | Wh (shown as kWh) |
| `sensor.lg_thermav_r290_electrical_energy_dhw` | 44–45 | Wh (shown as kWh) |
| `sensor.lg_thermav_r290_demand_vs_supply` | 46–47 | none (reads 0–12 on a 12 kW unit) |
| `sensor.lg_thermav_r290_thermal_power_heat_pump_register` | 48–49 | W |
| `sensor.lg_thermav_r290_thermal_energy_space_heating` | 50–51 | Wh (shown as kWh) |

The block is read in one request, high word first. A unit that does not answer leaves the sensors without a value and does not affect the other entities; after three misses in a row the read is skipped for 20 polls before it is tried again, so a unit that does not serve the block costs a few timeouts, not one per poll. Registers 52–55 (cumulative thermal yield for cooling and DHW) are not read; they do not answer on a 12 kW unit. Switching the option off removes the sensors again.

`thermal_power_heat_pump_register` is the unit's own figure and is separate from the computed `thermal_power_*` sensors below.

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
| `number.lg_thermav_r290_max_compressor_modulation` | 40–100 % | 23 (optional, see below) |

#### Max compressor modulation (optional)

Switch on **Compressor modulation limit** in the integration's options. Holding register 23 (40024) caps how far the compressor may modulate, in percent: 40–100 sets a limit, 0 means no limit is set. It is not in the manual's table and not every unit serves it — the 9 kW unit in [docs/register-scan.md](docs/register-scan.md) does not answer on it, a 12 kW unit does.

- Writable **only while the option is on**; with it off the integration refuses every write to register 23.
- Every write is clamped to 40–100 % and read back, so the slider shows what the unit stored.
- While the unit reports 0 (no limit), the slider shows *unknown*; the attributes `register_value` and `limit_active` show the raw state.
- A unit that does not answer leaves the slider unavailable, with the same back-off as the energy registers. Switching the option off removes the entity.

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
| FC04 (input) | 34–51 | Optional: electrical power/energy, demand vs. supply, thermal yield |
| FC04 (input) | 9997–9998 | Product info, device group |
| FC03 (holding) | 0–9 | Operation mode, control method, setpoints, shift values, energy state |
| FC03 (holding) | 23 | Optional: max compressor modulation (writable while the option is on) |
| FC01 (coils) | 0–4 | Main switch, DHW, silent mode, disinfection trigger, emergency stop |
| FC02 (discrete) | 0–16 | Status bits (compressor, pumps, defrost, faults, …) |

---

## Notes

- Thermal power formula: `Q [W] = (flow_rate [l/min] / 60) × (outlet_temp − inlet_temp) [K] × 4186 [J/(l·K)]`
- Heating circuit / DHW split is based on the `di_dhw_heating` discrete input; when DHW is active the full flow is attributed to DHW and the heating circuit sensor reports 0, and vice versa.
- Shift values (holding regs 4, 7) are stored as two's-complement uint16; values ≥ 32768 are interpreted as negative.
- Tested on LG ThermaV R290 9 kW via Modbus TCP, slave ID 33.
- `tools/make_shadow.py` builds a read-only copy of the integration under a
  second domain so a change to the Modbus layer can be measured against the
  running one on the same hardware. See `tools/README.md`.

---

## License

MIT
