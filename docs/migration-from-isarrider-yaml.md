# Migrating from isarrider's YAML setup

This maps every part of [isarrider/homeassistant_lg_therma_v_modbus](https://github.com/isarrider/homeassistant_lg_therma_v_modbus) (`modbus_lg_heatpump.yaml`, state of 2026-10-03) to its counterpart in this integration: Modbus entities, helpers, template sensors and automations. It also lists every difference in behaviour that matters when switching.

That YAML setup was written for a **12 kW** R290 on **Modbus RTU** (USB serial adapter, 9600 8N1, slave 1), firmware **kernel 3.0.9 / ramdisk 3.07.6a (2025-01-21)**. Which optional registers a unit serves may depend on firmware, so compare yours if something below does not answer. The 12 kW serves registers that the 9 kW unit in [register-scan.md](register-scan.md) does not, and the integration covers them behind options (see [Options to switch on](#2-options-to-switch-on)).

For basti242's YAML setup, which this one grew out of, see [migration-from-yaml.md](migration-from-yaml.md).

> The entity ids below follow from the entity names with the default device name `LG ThermaV R290`. If you renamed the device, the prefix differs. Check them under *Developer tools → States* before changing a dashboard or an automation.

---

## Contents

1. [Before you start](#1-before-you-start)
2. [Options to switch on](#2-options-to-switch-on)
3. [Sensors (input registers, FC04)](#3-sensors-input-registers-fc04)
4. [Holding registers (FC03)](#4-holding-registers-fc03)
5. [Switches and triggers (coils, FC01/05)](#5-switches-and-triggers-coils-fc0105)
6. [Binary sensors (discrete inputs, FC02)](#6-binary-sensors-discrete-inputs-fc02)
7. [Helpers: input_number and input_select](#7-helpers-input_number-and-input_select)
8. [Template sensors](#8-template-sensors)
9. [Automations](#9-automations)
10. [Differences that can bite](#10-differences-that-can-bite)
11. [Only in the YAML (not in the integration)](#11-only-in-the-yaml-not-in-the-integration)
12. [Only in the integration](#12-only-in-the-integration)
13. [Keeping history](#13-keeping-history)
14. [Rewriting your own automations](#14-rewriting-your-own-automations)
15. [Step-by-step checklist](#15-step-by-step-checklist)

---

## 1. Before you start

- **Home Assistant 2026.9 or newer.** The integration uses Home Assistant's shared Modbus connection (see the README, *Requirements*).
- **One serial port, one owner.** A USB serial adapter can only be opened by one connection at a time. The YAML `modbus:` hub `lg_heatpump` and the integration both want `/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller-if00-port0`. Whether Home Assistant hands them one shared connection has not been tested. The safe way is to switch in one go: remove (or comment out) the YAML package, restart, then add the integration. Running both at once on the same adapter is not recommended.
- **Connection settings.** The config flow asks for the same values the YAML hub sets:

  | YAML hub (`modbus:`) | Config flow |
  |---|---|
  | `type: serial`, `method: rtu` | Connection type **RTU** |
  | `port: /dev/serial/by-id/usb-Prolific_…-port0` | Serial port (use the same `/dev/serial/by-id/…` path, it survives reboots) |
  | `baudrate: 9600` | Baudrate 9600 |
  | `parity: N` | Parity N |
  | `stopbits: 1` | Stop bits 1 |
  | `bytesize: 8` | fixed at 8, not asked |
  | `slave: 1` (on every entity) | Slave ID 1 |
  | `scan_interval: 10` (on every entity) | Poll interval, see below |

- **Poll interval.** The YAML polls every 10 s, and so does the integration by default; it reads everything in one cycle. The interval can be changed in the integration's options (allowed range 5–3600 s). The identity registers 9997/9998, which the YAML reads every 3600 s, are read once per start.

---

## 2. Options to switch on

*Settings → Devices & Services → LG ThermaV R290 → Configure.* All are off by default, because not every unit serves these registers. On the 12 kW, switch on:

| Option | Gives you | YAML counterpart |
|---|---|---|
| **Energy registers** | Input 34–51 as sensors, plus *Heating COP (Cumulative)* and *COP Current* | `hp_ENERGY_*`, `hp_Demand_vs_Supply`, the COP template |
| **Compressor modulation limit** | The *Max Compressor Modulation* slider on holding 23 | `hp_compressor_modulation` + `input_number.hp_compressor_modulation_slider` + two automations |

Optional:

| Option | Gives you |
|---|---|
| **Experimental registers** | Raw diagnostic sensors for 18 undocumented addresses, including input 17 (see [§3](#3-sensors-input-registers-fc04)) |

The power limit (holding 24 + coil 6) is **not** in the integration yet; see [§11](#11-only-in-the-yaml-not-in-the-integration).

---

## 3. Sensors (input registers, FC04)

| Reg. | YAML (`sensor.…`) | Integration (`sensor.…`) | Notes |
|---|---|---|---|
| 0 | `hp_error_code` | `lg_thermav_r290_error_code` | |
| 1 | `hp_odu_operation_cycle` | `lg_thermav_r290_operation_cycle_odu` | Raw number in both. Labels: see [§11](#11-only-in-the-yaml-not-in-the-integration). |
| 2 | `hp_inlet_temp` | `lg_thermav_r290_inlet_temperature` | |
| 3 | `hp_outlet_temp` | `lg_thermav_r290_outlet_temperature` | |
| 4 | `hp_backup_heater_outlet_temp` | `lg_thermav_r290_backup_heater_outlet_temperature` | |
| 5 | `hp_dhw_water_temp` | `lg_thermav_r290_dhw_temperature` | |
| 6 | `hp_solar_collector_temp` | `lg_thermav_r290_solar_collector_temperature` | |
| 7 | `hp_temp_technikraum` | `lg_thermav_r290_room_air_temperature_circuit_1` | Same value. The manual calls input 30008 *room air temperature circuit 1*; without a wired remote the unit reports its own sensor, hence "Technikraum" in the YAML. |
| 8 | `hp_flow_rate` | `lg_thermav_r290_flow_rate` | Both `L/min`, device class `volume_flow_rate`. |
| 9 | `hp_flow_temp_circle_2` | `lg_thermav_r290_flow_temperature_circuit_2` | |
| 10 | `hp_room_air_temp_circuit2_input` | `lg_thermav_r290_room_air_temperature_circuit_2` | |
| 11 | `hp_energy_state_input` | `lg_thermav_r290_energy_control_signal` (raw) and `lg_thermav_r290_energy_state_reported` (label) | The labelled *Energy State* without "(Reported)" reads holding 9, see [§10](#10-differences-that-can-bite). |
| 12 | `hp_outside_temp` | `lg_thermav_r290_outdoor_temperature` | |
| 13 | `hp_water_pressure` | `lg_thermav_r290_water_pressure` | ×0.1 bar in both. |
| 16 | `hp_temp_liquid_gas` | `lg_thermav_r290_liquid_gas_temperature` | **Scale differs: YAML ×0.001, integration ×0.1.** See [§10](#10-differences-that-can-bite). |
| 17 | `hp_temp_pipe_out` | *(none)* — raw value only as `Experimental Input 30018` with the Experimental option | Reads a constant 12000, not a temperature. See [§10](#10-differences-that-can-bite). |
| 18 | `hp_temp_suction` | `lg_thermav_r290_suction_temperature` | |
| 19 | `hp_temp_heatgas` | `lg_thermav_r290_hot_gas_temperature` | |
| 20 | `hp_temp_before_vaporiser` | `lg_thermav_r290_temperature_before_evaporator` | |
| 21 | `hp_temp_after_vaporiser` | `lg_thermav_r290_temperature_after_evaporator` | |
| 22 | `hp_high_pressure` | `lg_thermav_r290_high_pressure_condenser` | ×0.01 bar in both. |
| 23 | `hp_low_pressure` | `lg_thermav_r290_low_pressure_evaporator` | ×0.01 bar in both. |
| 24 | `hp_compressor_rpm` | `lg_thermav_r290_compressor_speed` | ×60 in both. Unit `U/min` → `rpm`. |
| 34–35 | `hp_energy_instantaneous_total_system` | `lg_thermav_r290_electrical_power_total_system` | *Energy registers* option. W, uint32. |
| 36–37 | `hp_energy_instantaneous_total` | `lg_thermav_r290_electrical_power_heat_pump` | *Energy registers* option. W, uint32. |
| 38–39 | `hp_energy_accumulative_total` | `lg_thermav_r290_electrical_energy_total` | *Energy registers* option. Wh (shown as kWh). State class differs, see [§10](#10-differences-that-can-bite). |
| 40–41 | `hp_energy_accumulative_heat` | `lg_thermav_r290_electrical_energy_space_heating` | as above |
| 42–43 | `hp_energy_accumulative_cool` | `lg_thermav_r290_electrical_energy_space_cooling` | as above |
| 44–45 | `hp_energy_accumulative_dhw` | `lg_thermav_r290_electrical_energy_dhw` | as above |
| 46–47 | `hp_demand_vs_supply` | `lg_thermav_r290_demand_vs_supply` | *Energy registers* option. **No unit** (the YAML says %); it reads 0–12 on the 12 kW. |
| 48–49 | `hp_energy_instantaneous_total_th` | `lg_thermav_r290_thermal_power_heat_pump_register` | *Energy registers* option. W, uint32. |
| 50–51 | `hp_energy_accumulative_heat_th` | `lg_thermav_r290_thermal_energy_space_heating` | *Energy registers* option. Wh (shown as kWh). |
| 52–55 | commented out (`hp_ENERGY_ACCUMULATIVE_COOL_TH`, `…_DHW_TH`) | not read | Do not answer on the 12 kW. Reading them in the same block would drop the whole energy read. |
| 9997 | `hp_product_group` | `lg_thermav_r290_device_group` | **Disabled by default**: enable it in the entity settings. |
| 9998 | `hp_product_info` | `lg_thermav_r290_product_information` | **Disabled by default**: enable it in the entity settings. |

---

## 4. Holding registers (FC03)

In the YAML every holding register is a read sensor, and the writable ones get a helper plus a pair of automations (see [§7](#7-helpers-input_number-and-input_select) and [§9](#9-automations)). In the integration a writable register is **one entity** that reads and writes.

| Reg. | YAML read sensor | Integration | Writable here |
|---|---|---|---|
| 0 | `sensor.hp_operation_mode` | `select.lg_thermav_r290_operation_mode` (+ text sensor `sensor.lg_thermav_r290_operation_mode`) | yes |
| 1 | `sensor.hp_control_method` | `select.lg_thermav_r290_control_method` (+ text sensor `sensor.lg_thermav_r290_control_method`) | yes |
| 2 | `sensor.hp_target_temp_circuit1` | `number.lg_thermav_r290_target_temperature_circuit_1_radiators` | yes, 20–60 °C |
| 3 | `sensor.hp_room_air_temp_circuit1` | `sensor.lg_thermav_r290_room_air_temperature_circuit_1_holding` — **disabled by default** | no (read only in both) |
| 4 | `sensor.hp_shift_value_in_auto_mode_circuit1` | `number.lg_thermav_r290_setpoint_shift_circuit_1` | yes, −5…+5 |
| 5 | `sensor.hp_target_temp_circuit2` | `number.lg_thermav_r290_target_temperature_circuit_2_underfloor` | yes, 20–40 °C |
| 6 | `sensor.hp_room_air_temp_circuit2` | `sensor.lg_thermav_r290_room_air_temperature_circuit_2_holding` — **disabled by default** | no (read only in both) |
| 7 | `sensor.hp_shift_value_in_auto_mode_circuit2` | `number.lg_thermav_r290_setpoint_shift_circuit_2` | yes, −5…+5 |
| 8 | `sensor.hp_dhw_target_temp` | `number.lg_thermav_r290_dhw_target_temperature` | yes, 35–65 °C |
| 9 | `sensor.hp_energy_state_input_raw` | `sensor.lg_thermav_r290_energy_state` (label) and `binary_sensor.lg_thermav_r290_energy_state_*` (one per value 0–8) | no (read only in both) |
| 23 | `sensor.hp_compressor_modulation` | `number.lg_thermav_r290_max_compressor_modulation` (*Compressor modulation limit* option) | yes, 40–100 %, only while the option is on |
| 24 | `sensor.hp_power_limitation` | not in the integration yet | — |

The integration only ever writes a fixed list of addresses: holding 0, 1, 2, 4, 5, 7, 8, plus holding 23 while its option is on. Every other write is refused before it reaches the bus.

---

## 5. Switches and triggers (coils, FC01/05)

| Coil | YAML (`switch.…`) | Integration | Notes |
|---|---|---|---|
| 0 | `hp_hauptschalter` | `switch.lg_thermav_r290_heat_pump` | |
| 1 | `hp_dhw` | `switch.lg_thermav_r290_dhw` | |
| 2 | `hp_silent_mode` | `switch.lg_thermav_r290_silent_mode` | |
| 3 | `hp_dhw_desinfection_mode` | `button.lg_thermav_r290_start_disinfection` | **A button, not a switch.** See [§10](#10-differences-that-can-bite). |
| 4 | `hp_emergency_stop_switch_off` (YAML comment: emergency operation, space heating) | `switch.lg_thermav_r290_emergency_stop` | Same coil, different name. |
| 5 | `hp_emergency_stop_switch_on` (YAML comment: emergency operation, DHW) | read internally, **not writable** | See [§10](#10-differences-that-can-bite). |
| 6 | `hp_active_power_limit` | not in the integration yet | See [§11](#11-only-in-the-yaml-not-in-the-integration). |

The YAML verifies each switch by reading its coil back. The integration does the same: after every write it refreshes, so a switch shows what the unit stored.

---

## 6. Binary sensors (discrete inputs, FC02)

| Bit | YAML (`binary_sensor.…`) | Integration (`binary_sensor.…`) | Device class here |
|---|---|---|---|
| 10001 | `hp_water_flow_status` | `lg_thermav_r290_water_flow` | running |
| 10002 | `hp_water_pump_status` | `lg_thermav_r290_water_pump` | running |
| 10003 | `hp_ext_water_pump_status` | `lg_thermav_r290_external_water_pump` | running |
| 10004 | `hp_compressor_status` | `lg_thermav_r290_compressor` | running |
| 10005 | `hp_defrosting_status` | `lg_thermav_r290_defrost` | running |
| 10006 | `hp_dhw_heating_status` | `lg_thermav_r290_dhw_heating` | running |
| 10007 | `hp_dhw_tank_desinfection_status` | `lg_thermav_r290_dhw_disinfection` | running |
| 10008 | `hp_silent_mode_status` | `lg_thermav_r290_silent_mode` | — |
| 10009 | `hp_cooling_status` | `lg_thermav_r290_cooling_active` | cold — **not reliable**, see [§10](#10-differences-that-can-bite) |
| 10010 | `hp_solar_pump_status` | `lg_thermav_r290_solar_pump` | running |
| 10011 | `hp_backup_heater_step1_status` | `lg_thermav_r290_backup_heater_step_1` | heat |
| 10012 | `hp_backup_heater_step2_status` | `lg_thermav_r290_backup_heater_step_2` | heat |
| 10013 | `hp_dhw_boost_heater_status` | `lg_thermav_r290_dhw_boost_heater` | heat |
| 10014 | `hp_error_status` | `lg_thermav_r290_fault` | problem |
| 10015 | `hp_emergency_operation_available_space_heating_cooling` | `lg_thermav_r290_emergency_heating_cooling_available` | — |
| 10016 | `hp_emergency_operation_available_dhw` | `lg_thermav_r290_emergency_dhw_available` | — |
| 10017 | `hp_mix_pump_status` | `lg_thermav_r290_mixing_pump` | running |

The YAML name for 10015 contains a `/` (`…space_heating/cooling`); Home Assistant turns it into `_` in the entity id, as shown.

---

## 7. Helpers: input_number and input_select

All nine helpers can be deleted after switching. Their job (a control in the UI that writes a register and follows it) is done by the integration's `number` and `select` entities, which read and write the register directly.

| YAML helper | Range / options in the YAML | Integration | Range / options here |
|---|---|---|---|
| `input_number.hp_shift_value_in_auto_mode_circuit1` | −5…5, step 1 | `number.lg_thermav_r290_setpoint_shift_circuit_1` | −5…5, step 1 |
| `input_number.hp_shift_value_in_auto_mode_circuit2` | −5…5, step 1 | `number.lg_thermav_r290_setpoint_shift_circuit_2` | −5…5, step 1 |
| `input_number.hp_hk1_target_temperatur` | 20–60 °C, step 1 | `number.lg_thermav_r290_target_temperature_circuit_1_radiators` | 20–60 °C, step 1 |
| `input_number.hp_hk2_target_temperatur` | 20–40 °C, step 1 | `number.lg_thermav_r290_target_temperature_circuit_2_underfloor` | 20–40 °C, step 1 |
| `input_number.hp_dhw_target_temperatur` | 40–60 °C, step 1 | `number.lg_thermav_r290_dhw_target_temperature` | **35–65 °C**, step 1 |
| `input_number.hp_compressor_modulation_slider` | 40–100 %, slider | `number.lg_thermav_r290_max_compressor_modulation` | 40–100 %, slider (*Compressor modulation limit* option) |
| `input_number.hp_power_limitation_slider` | 0.1–25.0 kW, slider | not in the integration yet | — |
| `input_select.hp_set_operation_mode` | Kühlen / Heizen / Auto | `select.lg_thermav_r290_operation_mode` | Cooling / Heating / Auto |
| `input_select.hp_set_control_method` | Wasserauslasstemp. Steuerung / Wassereinlasstemp. Steuerung / Raumluftsteuerung | `select.lg_thermav_r290_control_method` | Outlet Water Temp Control / Inlet Water Temp Control / Room Air Control |

The register values behind the options are identical: operation mode Cooling 0, Heating 4, Auto 3; control method 0, 1, 2. (The YAML's comment on holding register 0 says *1 = Heating*; its automations and the integration both use 4.)

---

## 8. Template sensors

| YAML template | Integration | Difference |
|---|---|---|
| `sensor.hp_energy_state` (*HP Energy State*) | `sensor.lg_thermav_r290_energy_state_reported` | Same register (input 11). Labels are English instead of German, with the value in front (`2 – Normal Operation`); a value outside 0–8 shows as the number instead of *Unknown*. Not to be confused with `sensor.lg_thermav_r290_energy_state`, which labels holding 9; see [§10](#10-differences-that-can-bite). |
| `sensor.hp_heating_cop_calculated` (*HP Heating COP (Calculated)*) | `sensor.lg_thermav_r290_heating_cop_cumulative` (*Energy registers* option) | Same formula, input 50 ÷ input 40. No value instead of `0` while no electrical energy is counted. No unit (the YAML uses `COP`). |
| *HP DHW COP (Calculated)* (commented out) | none | Its thermal counter (input 54) does not answer on the 12 kW. |

---

## 9. Automations

All 18 automations can be deleted after switching. Each pair (helper → register, register → helper) existed to keep a helper and a register in sync; a `number` or `select` entity is both at once.

| YAML automation (`id`) | Writes / syncs | Replaced by |
|---|---|---|
| `hp_automation_operation_mode_modbus_update` | input_select → holding 0 | `select.lg_thermav_r290_operation_mode` |
| `hp_automation_operation_mode_input_select_update` | holding 0 → input_select | same |
| `hp_automation_control_method_modbus_update` | input_select → holding 1 | `select.lg_thermav_r290_control_method` |
| `hp_automation_control_method_input_select_update` | holding 1 → input_select | same |
| `hp_automation_set_shift_value_in_auto_mode_circuit1_modbus_update` | input_number → holding 4 (negatives +65536) | `number.lg_thermav_r290_setpoint_shift_circuit_1` (two's complement handled internally) |
| `hp_automation_set_shift_value_in_auto_mode_circuit1_input_slider_update` | holding 4 → input_number | same |
| `hp_automation_set_shift_value_in_auto_mode_circuit2_modbus_update` | input_number → holding 7 | `number.lg_thermav_r290_setpoint_shift_circuit_2` |
| `hp_automation_set_shift_value_in_auto_mode_circuit2_input_slider_update` | holding 7 → input_number | same |
| `hp_automation_set_target_temperatur_hk1_modbus_update` | input_number ×10 → holding 2 | `number.lg_thermav_r290_target_temperature_circuit_1_radiators` |
| `hp_automation_set_target_temperatur_hk1_input_slider_update` | holding 2 → input_number | same |
| `hp_automation_set_target_temperatur_hk2_modbus_update` | input_number ×10 → holding 5 | `number.lg_thermav_r290_target_temperature_circuit_2_underfloor` |
| `hp_automation_set_target_temperatur_hk2_input_slider_update` | holding 5 → input_number | same |
| `hp_automation_set_target_temperatur_modbus_update` | input_number ×10 → holding 8 | `number.lg_thermav_r290_dhw_target_temperature` |
| `hp_automation_set_target_temperatur_input_slider_update` | holding 8 → input_number | same |
| `hp_automation_set_hp_comp_target_percent_modbus_update` | slider → holding 23 | `number.lg_thermav_r290_max_compressor_modulation` |
| `hp_compressor_mod_sync` | holding 23 → slider | same |
| `hp_power_limit_write` | slider ×10 → holding 24 | not in the integration yet |
| `hp_power_limit_sync` | holding 24 → slider | not in the integration yet |

A side effect worth knowing: the YAML notes that a slider change can take up to 60 s to show in the state sensors. In the integration a write is followed by an immediate refresh, so the entity shows the stored value right away.

---

## 10. Differences that can bite

### Values and units

- **Input 16 (liquid gas temperature) is 100× larger here.** The YAML scales it by 0.001 (marked "Scale???"), the integration by 0.1, measured against the other refrigerant temperatures. A YAML reading of 0.25 °C is 25.0 °C here. History from the two is not comparable.
- **Input 17 is not a temperature.** The YAML shows `hp_temp_pipe_out` as a constant 12.00 °C (raw 12000 × 0.001). The integration does not present it as a sensor. With the *Experimental registers* option it appears raw as `Experimental Input 30018`.
- **Demand vs Supply has no unit.** The YAML shows %, but the register reads 0–12 on the 12 kW, so it is not a percentage.
- **Energy counters use `total_increasing`, not `total`.** Both in Wh. With `total_increasing` a counter reset is treated as a new cycle rather than a drop. In the Energy dashboard you have to pick the new entities; the old statistics stay with the old ids.
- **Compressor speed unit** is `rpm` instead of `U/min`. The value is the same.
- **Temperatures** are rounded to 0.1 °C; the YAML shows 2 decimals. The register resolution is 0.1 °C either way.

### Two Energy State sensors

The YAML's *HP Energy State* labels **input 11** (`hp_energy_state_input`), the state the unit reports as active. Its counterpart here is `sensor.lg_thermav_r290_energy_state_reported`, with the same values in English.

The integration's *Energy State* (`sensor.lg_thermav_r290_energy_state`) and the nine `energy_state_*` binary sensors label **holding 9** (`hp_energy_state_input_raw` in the YAML), the command register. If the SG-Ready state reaches the unit through its contacts rather than a Modbus write, holding 9 may never change. Automations built on *HP Energy State* should use `energy_state_reported`.

Which of the two follows SG-Ready on a 12 kW has not been checked yet; compare both over a few SG-Ready changes.

### Controls

- **Coil 3 is a button.** The manual specifies it as a trigger (`0: hold status / 1: start operation`). The unit clears it by itself after the write, so the YAML switch always reads back `off`, even when the write worked. Use `button.lg_thermav_r290_start_disinfection` and watch `binary_sensor.lg_thermav_r290_dhw_disinfection` to see whether the cycle started. The trigger only works if disinfection is enabled on the unit (installer menu → DHW → disinfection active).
- **Coil 5 cannot be written.** The YAML switch `hp_emergency_stop_switch_on` writes it. The manual calls it a trigger for emergency operation, so the integration reads it but no entity can write it.
- **Coil 4 has a different name.** YAML: `hp_emergency_stop_switch_off`, commented as emergency operation for space heating. Here: `switch.lg_thermav_r290_emergency_stop`. Same coil, same writes.
- **Setpoint ranges.** HK1 allows 20–60 °C, as in the YAML. DHW allows 35–65 °C here (YAML 40–60). The unit applies its own limits on top: a value it does not accept is stored clamped, and the entity shows what was stored.
- **Max compressor modulation shows *unknown* when no limit is set.** The register holds 0 for "no limit". The YAML slider then keeps its last position (its sync automation cannot set 0 on a 40–100 slider); the integration shows *unknown*, with `register_value: 0` and `limit_active: false` as attributes. Every write is clamped to 40–100, so the slider can never send 0.

### Status bits

- **Water flow (10001) means the same as in the YAML.** The YAML's comment (*0 = no flow, 1 = flow*) matches what the unit does. The LG manual documents it the other way round; the integration follows the measured behaviour and uses device class `running`. No automation needs flipping.
- **Cooling status (10009) is not reliable on the R290.** It was measured `on` during heating for days. Do not build automations on `binary_sensor.lg_thermav_r290_cooling_active` (README, note on discrete input 10009).

### Polling and failures

- **One poll cycle reads everything.** The YAML schedules each entity separately. If a documented block fails, the whole update fails and all entities go unavailable together, rather than single sensors going stale.
- **Optional registers never fail the update.** If the energy block or holding 23 stop answering, only their entities lose their value; after three misses in a row that read pauses for 20 polls.

---

## 11. Only in the YAML (not in the integration)

| YAML | Status |
|---|---|
| Power limit: `sensor.hp_power_limitation` (holding 24), `input_number.hp_power_limitation_slider`, `switch.hp_active_power_limit` (coil 6), automations `hp_power_limit_write` / `hp_power_limit_sync` | Not in the integration yet. The addresses come from a community forum, they do not answer on the scanned 9 kW, and nobody has confirmed on an R290 that writing them has an effect. A draft implementation, behind an off-by-default *unverified* option, waits for that check. |
| Labels for the ODU operation cycle (input 1) | The YAML comment gives 0 Off, 1 Standby, 2 Running, 3 Defrost; LG's table for 30002 gives 0 Standby/Off, 1 Cooling, 2 Heating. Until a unit's history shows which is right, the integration exposes the raw number only. A draft label sensor exists. |
| *HP DHW COP (Calculated)* (commented out) | Its thermal counter does not answer on the 12 kW. |

---

## 12. Only in the integration

- **Computed thermal power**: `sensor.lg_thermav_r290_thermal_power_total`, `…_thermal_power_heating_circuit`, `…_thermal_power_dhw`, from flow rate and ΔT each poll (`Q = flow/60 × ΔT × 4186 W`). Independent of the energy registers.
- **Current COP**: `sensor.lg_thermav_r290_cop_current` (*Energy registers* option), input 48 ÷ input 36, no value while the electrical power is below 100 W.
- **System COP**: `sensor.lg_thermav_r290_cop_system` (*Energy registers* option), input 48 ÷ input 34 (total system), same idle rule. Lower than the current COP whenever something besides the heat pump, such as a backup heater, draws power.
- **Text sensors for the selects**: `sensor.lg_thermav_r290_operation_mode`, `sensor.lg_thermav_r290_control_method`.
- **Energy states as binary sensors**: `binary_sensor.lg_thermav_r290_energy_state_not_used`, `…_forced_off`, `…_normal_operation`, `…_on_recommendation`, `…_on_command`, `…_on_command_step_2`, `…_on_recommendation_step_1`, `…_energy_saving_mode`, `…_super_energy_saving_mode` (one per value of holding 9).
- **Experimental registers** (option): raw sensors for undocumented addresses, see the README.
- **One device** in the device registry, with a config flow, options, and *Reconfigure* for the connection.

---

## 13. Keeping history

The integration's entities have new ids, so their history starts empty. Two ways to keep the old history in view:

- **Side by side in a history graph.** The old YAML entities' recorded history stays in the database until the recorder purges it (long-term statistics stay longer). Put old and new entity in one history card for the overlap.
- **Rename to the old id.** After removing the YAML package and restarting, the old YAML entities stay in the entity registry as *unavailable* (they had a `unique_id`), and their ids stay taken. Delete the old entity first (*Settings → Entities*, select it, *Delete*), then give the integration entity the old id in its entity settings (for example `sensor.lg_thermav_r290_outdoor_temperature` → `sensor.hp_outside_temp`). From then on its states are recorded under the old id, so the graph continues the old history. Do it early: whatever was recorded under the new id before the rename stays with that id, and Home Assistant may log that it could not move it because the old id is already in use. **Only do this where the value means the same thing in the same unit.** Do not do it for input 16 (scale differs), input 17 (gone), Demand vs Supply (% → no unit), the energy counters if you rely on their long-term statistics (`total` → `total_increasing`), or *Energy State* (rename `energy_state_reported` instead, which reads the same register as *HP Energy State*; its values are English, so the old German states do not continue). Check *Developer tools → Statistics* afterwards for unit warnings.

Renaming makes the entity ids in this guide and the README no longer apply to your system; dashboards and automations then keep working unchanged.

---

## 14. Rewriting your own automations

Replace `modbus.write_register` / `modbus.write_coil` calls and helper writes with service calls on the integration's entities.

**Target temperature, circuit 1** (YAML: write ×10 to holding 2):

```yaml
# before
- action: modbus.write_register
  data:
    hub: lg_heatpump
    slave: 1
    address: 2
    value: 450
# after
- action: number.set_value
  target:
    entity_id: number.lg_thermav_r290_target_temperature_circuit_1_radiators
  data:
    value: 45
```

**Operation mode** (YAML: Heizen → 4 on holding 0):

```yaml
- action: select.select_option
  target:
    entity_id: select.lg_thermav_r290_operation_mode
  data:
    option: Heating   # Cooling / Heating / Auto
```

**Setpoint shift** (YAML: negative values +65536):

```yaml
- action: number.set_value
  target:
    entity_id: number.lg_thermav_r290_setpoint_shift_circuit_1
  data:
    value: -2   # plain value; the conversion is done internally
```

**Compressor modulation** (YAML: slider → holding 23):

```yaml
- action: number.set_value
  target:
    entity_id: number.lg_thermav_r290_max_compressor_modulation
  data:
    value: 60   # 40–100 %, clamped
```

**Disinfection** (YAML: `switch.turn_on` on coil 3):

```yaml
- action: button.press
  target:
    entity_id: button.lg_thermav_r290_start_disinfection
```

**Triggers and conditions**: replace entity ids by the tables above. State values change where the type changed:

| YAML state | Integration state |
|---|---|
| `sensor.hp_operation_mode` = `4` | `select.lg_thermav_r290_operation_mode` = `Heating` (there is no numeric operation-mode sensor here) |
| `input_select.hp_set_operation_mode` = `Heizen` | `select.lg_thermav_r290_operation_mode` = `Heating` |
| `sensor.hp_energy_state` = `Normalbetrieb` | `sensor.lg_thermav_r290_energy_state_reported` = `2 – Normal Operation` |
| `sensor.hp_heating_cop_calculated` = `0` before any energy is counted | `unknown` |

---

## 15. Step-by-step checklist

1. Note the current values of all writable registers (operation mode, control method, HK1/HK2/DHW targets, shift values, compressor modulation), so you can compare after switching.
2. Export or screenshot dashboards and automations that use `hp_*` entities or the helpers.
3. Remove (or comment out) the YAML package: the `modbus:` hub, `input_number:`, `input_select:`, `template:` and `automation:` parts. Restart Home Assistant.
4. *Settings → Devices & Services → Add Integration → LG ThermaV R290*: connection type RTU, the same `/dev/serial/by-id/…` port, 9600, N, 1, slave 1.
5. *Configure*: **Energy registers** on, **Compressor modulation limit** on. Experimental registers only if you want to record the undocumented addresses.
6. Enable the disabled-by-default sensors you used: device group, product information, room air temperature circuit 1/2 (holding).
7. Compare the values from step 1 with the new entities. Compressor modulation shows *unknown* if no limit is set.
8. Update the Energy dashboard: pick the new electrical energy sensors (and the thermal one if you use it).
9. Rewrite automations and dashboards using the tables in §3–§9 and the examples in §14. Check [§10](#10-differences-that-can-bite) for every automation that uses input 16, input 17, Energy State, coil 3, coil 5, or setpoints outside the new ranges.
10. Delete the old YAML entities left in the entity registry (they show as *unavailable*).
11. Optionally rename integration entities to their old ids where the meaning is identical ([§13](#13-keeping-history)). This only works after step 10.
12. Delete the YAML file once everything works.
