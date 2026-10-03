# Migrating from basti242's YAML setup

This maps every entity of [basti242/homeassistant_lg_therma_v_modbus](https://github.com/basti242/homeassistant_lg_therma_v_modbus) (`modbus_lg_heatpump.yaml`, state of 2026-05-05) to its counterpart in this integration.

There is no automatic migration: the entities have different ids and belong to one device now. Update dashboards, automations and the Energy configuration by hand. Running both side by side for a while and comparing the values is the safest way across.

> The new entity ids follow from the entity names with the default device name `LG ThermaV R290`. Check them under *Developer tools → States* before changing a dashboard.

## Sensors (input registers, FC04)

| Reg. | basti242 | This integration |
|---|---|---|
| 0 | `sensor.hp_error_code` | `sensor.lg_thermav_r290_error_code` |
| 1 | `sensor.hp_odu_operation_cycle` | `sensor.lg_thermav_r290_operation_cycle_odu` |
| 2 | `sensor.hp_inlet_temp` | `sensor.lg_thermav_r290_inlet_temperature` |
| 3 | `sensor.hp_outlet_temp` | `sensor.lg_thermav_r290_outlet_temperature` |
| 4 | `sensor.hp_backup_heater_outlet_temp` | `sensor.lg_thermav_r290_backup_heater_outlet_temperature` |
| 5 | `sensor.hp_dhw_water_temp` | `sensor.lg_thermav_r290_dhw_temperature` |
| 6 | `sensor.hp_solar_collector_temp` | `sensor.lg_thermav_r290_solar_collector_temperature` |
| 7 | `sensor.hp_temp_technikraum` | `sensor.lg_thermav_r290_room_air_temperature_circuit_1` |
| 8 | `sensor.hp_flow_rate` | `sensor.lg_thermav_r290_flow_rate` |
| 9 | `sensor.hp_flow_temp_circle_2` | `sensor.lg_thermav_r290_flow_temperature_circuit_2` |
| 10 | `sensor.hp_room_air_temp_circuit2_input` | `sensor.lg_thermav_r290_room_air_temperature_circuit_2` |
| 11 | `sensor.hp_energy_state_input` | `sensor.lg_thermav_r290_energy_control_signal` |
| 12 | `sensor.hp_outside_temp` | `sensor.lg_thermav_r290_outdoor_temperature` |
| 13 | `sensor.hp_water_pressure` | `sensor.lg_thermav_r290_water_pressure` |
| 16 | `sensor.hp_temp_liquid_gas` | `sensor.lg_thermav_r290_liquid_gas_temperature` |
| 18 | `sensor.hp_temp_suction` | `sensor.lg_thermav_r290_suction_temperature` |
| 19 | `sensor.hp_temp_heatgas` | `sensor.lg_thermav_r290_hot_gas_temperature` |
| 20 | `sensor.hp_temp_before_vaporiser` | `sensor.lg_thermav_r290_temperature_before_evaporator` |
| 21 | `sensor.hp_temp_after_vaporiser` | `sensor.lg_thermav_r290_temperature_after_evaporator` |
| 22 | `sensor.hp_high_pressure` | `sensor.lg_thermav_r290_high_pressure_condenser` |
| 23 | `sensor.hp_low_pressure` | `sensor.lg_thermav_r290_low_pressure_evaporator` |
| 24 | `sensor.hp_compressor_rpm` | `sensor.lg_thermav_r290_compressor_speed` |
| 9998 | `sensor.hp_product_info` | `sensor.lg_thermav_r290_product_information` (plus `…_device_group` from 9997) |

## Holding registers (FC03)

| Reg. | basti242 | This integration |
|---|---|---|
| 0 | `sensor.hp_operation_mode_raw` + `select.hp_operation_mode_select` | `select.lg_thermav_r290_operation_mode` (+ text sensor `sensor.…_operation_mode`) |
| 1 | `sensor.hp_control_method_raw` + `select.hp_control_method_select` | `select.lg_thermav_r290_control_method` (+ `sensor.…_control_method`) |
| 2 | `sensor.hp_target_temp_circuit1` + `number.hp_hk1_target_temperatur_number` | `number.lg_thermav_r290_target_temperature_circuit_1_radiators` |
| 3 | `sensor.hp_room_air_temp_circuit1` + `number.hp_room_air_temp_circuit1_number` | `sensor.lg_thermav_r290_room_air_temperature_circuit_1_holding` (read only) |
| 4 | `sensor.hp_shift_value_in_auto_mode_circuit1` + `…_number` | `number.lg_thermav_r290_setpoint_shift_circuit_1` |
| 5 | `sensor.hp_target_temp_circuit2` + `number.hp_hk2_target_temperatur_number` | `number.lg_thermav_r290_target_temperature_circuit_2_underfloor` |
| 6 | `sensor.hp_room_air_temp_circuit2` + `number.hp_room_air_temp_circuit2_number` | `sensor.lg_thermav_r290_room_air_temperature_circuit_2_holding` (read only) |
| 7 | `sensor.hp_shift_value_in_auto_mode_circuit2` + `…_number` | `number.lg_thermav_r290_setpoint_shift_circuit_2` |
| 8 | `sensor.hp_dhw_target_temp` + `number.hp_dhw_target_temperatur_number` | `number.lg_thermav_r290_dhw_target_temperature` |
| 9 | `sensor.lg_wp_energiezustand_eingang` + `select.hp_energy_state_select` | `sensor.lg_thermav_r290_energy_state` and `binary_sensor.…_energy_state_*` (read only) |

## Switches and triggers (coils, FC01/05)

| Coil | basti242 | This integration |
|---|---|---|
| 0 | `switch.hp_hauptschalter` | `switch.lg_thermav_r290_heat_pump` |
| 1 | `switch.hp_dhw` | `switch.lg_thermav_r290_dhw` |
| 2 | `switch.lg_wp_ruhemodus` | `switch.lg_thermav_r290_silent_mode` |
| 3 | `switch.hp_dhw_desinfection_mode` | `button.lg_thermav_r290_start_disinfection` (trigger, not a switch) |
| 4 | `switch.hp_emergency_stop` | `switch.lg_thermav_r290_emergency_stop` |

## Binary sensors (discrete inputs, FC02)

| Bit | basti242 (`binary_sensor.…`) | This integration (`binary_sensor.…`) |
|---|---|---|
| 10001 | `hp_water_flow_status` | `lg_thermav_r290_water_flow` (**logic inverted**, see below) |
| 10002 | `hp_water_pump_status` | `lg_thermav_r290_water_pump` |
| 10003 | `hp_ext_water_pump_status` | `lg_thermav_r290_external_water_pump` |
| 10004 | `hp_compressor_status` | `lg_thermav_r290_compressor` |
| 10005 | `hp_defrosting_status` | `lg_thermav_r290_defrost` |
| 10006 | `hp_dhw_heating_status` | `lg_thermav_r290_dhw_heating` |
| 10007 | `hp_dhw_tank_desinfection_status` | `lg_thermav_r290_dhw_disinfection` |
| 10008 | `hp_silent_mode_status` | `lg_thermav_r290_silent_mode` |
| 10009 | `hp_cooling_status` | `lg_thermav_r290_cooling_active` (**not reliable**, see README) |
| 10010 | `hp_solar_pump_status` | `lg_thermav_r290_solar_pump` |
| 10011 | `hp_backup_heater_step1_status` | `lg_thermav_r290_backup_heater_step_1` |
| 10012 | `hp_backup_heater_step2_status` | `lg_thermav_r290_backup_heater_step_2` |
| 10013 | `hp_dhw_boost_heater_status` | `lg_thermav_r290_dhw_boost_heater` |
| 10014 | `hp_error_status` | `lg_thermav_r290_fault` |
| 10015 | `hp_emergency_operation_available_space_heating_cooling` | `lg_thermav_r290_emergency_heating_cooling_available` |
| 10016 | `hp_emergency_operation_available_dhw` | `lg_thermav_r290_emergency_dhw_available` |
| 10017 | `hp_mix_pump_status` | `lg_thermav_r290_mixing_pump` |

## Only in this integration

- Computed thermal power: `…_thermal_power_total`, `…_thermal_power_heating_circuit`, `…_thermal_power_dhw`.
- The energy states 0–8 as individual binary sensors.

## Only in basti242's setup (not implemented here)

| basti242 | Register | Here |
|---|---|---|
| `number.hp_room_air_temp_circuit1_number` / `…circuit2_number` | Holding 3 / 6 (writable) | read-only sensor |
| `select.hp_energy_state_select` | Holding 9 (writable) | read-only |
| `sensor.hp_power_limit` + `number.hp_power_limit_number` | Holding 24 | not implemented |
| `switch.hp_emergency_stop_switch` | Coil 5 | not implemented |
| `switch.hp_active_power_limitation` | Coil 6 | not implemented |

## Differences that can bite when switching

- **`water_flow` is inverted.** basti242 treats 10001 as a *problem* sensor per the manual (1 = flow too low). On the R290 monoblock the bit is set while water is flowing (see the note in the README). Automations built on `hp_water_flow_status` have to be flipped.
- **Register 7 is called "Technikraum" in the YAML.** It is the same value as `Room Air Temperature Circuit 1` here. Whether it really reports room air has not been checked.
- **DHW target range:** the YAML allows 45–60 °C, this integration 35–60 °C.
