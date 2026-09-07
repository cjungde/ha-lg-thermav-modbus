# LG ThermaV R290 — Home Assistant Integration

HACS custom integration for the LG ThermaV R290 heat pump via Modbus TCP or RTU.

Replaces a hand-crafted YAML Modbus configuration with native HA entities: sensors, binary sensors, switches, buttons, number inputs, and select dropdowns — all updated on every poll cycle without requiring template sensors or automations.

---

## Relation to ha-lg-thermav-r290

This repository succeeds [cjungde/ha-lg-thermav-r290](https://github.com/cjungde/ha-lg-thermav-r290), which stays available for Home Assistant 2026.8 and older. The split exists because the two cannot be one: the version here requires Home Assistant 2026.9 and does not carry a Modbus stack of its own, and there is no way to express that as a single HACS release without dropping every user on an older core.

**Do not install both.** They deliberately share the integration domain `lg_thermav_r290`, so that moving across is a straight swap — entity ids, history and long-term statistics all survive it. That same property means two copies would claim one directory. Uninstall the old one first, then install this one and restart; the config entry is read as it stands and nothing has to be re-entered.

The predecessor's commit history is not reproduced here. Where a decision needs its reasoning, the reasoning was moved into the code as comments — see `number.py` on the DHW maximum, and `coordinator.py` on the flow-rate discrete input.

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

Users on Home Assistant 2026.8 or older should stay on 0.0.14.

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
> device class `running`. Up to and including v0.x it was named
> `..._water_flow_insufficient` with device class `problem`, which raised a false
> problem alert on every pump run. **After updating, the old entity remains in the
> registry as `unavailable` and can be removed manually.**

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

> **Breaking change in 0.0.11:** this replaces `switch.lg_thermav_r290_disinfection_mode`,
> which modelled a trigger coil as a switch and therefore always read back `off`,
> even when the write succeeded. **After updating, the old switch remains in the
> registry as `unavailable` and can be removed manually.** Note that the trigger
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
- Heating circuit / DHW split is based on the `di_dhw_heating` discrete input; when DHW is active the full flow is attributed to DHW and the heating circuit sensor reports 0, and vice versa.
- Shift values (holding regs 4, 7) are stored as two's-complement uint16; values ≥ 32768 are interpreted as negative.
- Tested on LG ThermaV R290 9 kW via Modbus TCP, slave ID 33.
- `tools/make_shadow.py` builds a read-only copy of the integration under a
  second domain so a change to the Modbus layer can be measured against the
  running one on the same hardware. See `tools/README.md`.

---

## License

MIT
