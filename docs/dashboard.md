# Example dashboard

Two ready-to-paste dashboards:

- [Compact view](#compact-view): the essentials on one page.
- [Full view](#full-view): a sections view with every entity of the integration, grouped by topic.

## Compact view

A ready-to-paste dashboard view for the heat pump, built from Home Assistant's own cards only; nothing to install. Entity ids are the defaults (`…lg_therma_v_r290_…`); if you renamed yours, adjust them.

**To use it:** *Settings → Dashboards → Add dashboard → New dashboard from scratch*, open it, *⋮ → Edit dashboard → ⋮ → Raw configuration editor*, and paste the YAML below (it replaces the empty `views:`). Or paste only the cards you want into an existing view.

Cards marked *(option)* need that option switched on in *Configure → Options*; remove them otherwise, or Home Assistant shows them as unavailable.

```yaml
views:
  - title: Heat pump
    path: heat-pump
    icon: mdi:heat-pump
    cards:
      # --- Now --------------------------------------------------------------
      - type: tile
        entity: sensor.lg_therma_v_r290_operation_state_odu
        name: Outdoor unit
      - type: glance
        title: Temperatures
        columns: 4
        entities:
          - entity: sensor.lg_therma_v_r290_outdoor_temperature
            name: Outdoor
          - entity: sensor.lg_therma_v_r290_outlet_temperature
            name: Flow
          - entity: sensor.lg_therma_v_r290_inlet_temperature
            name: Return
          - entity: sensor.lg_therma_v_r290_dhw_temperature
            name: DHW
      - type: glance
        title: Running
        columns: 4
        entities:
          - entity: binary_sensor.lg_therma_v_r290_compressor
            name: Compressor
          - entity: sensor.lg_therma_v_r290_compressor_speed
            name: Speed
          - entity: sensor.lg_therma_v_r290_flow_rate
            name: Flow rate
          - entity: binary_sensor.lg_therma_v_r290_defrost
            name: Defrost
          - entity: binary_sensor.lg_therma_v_r290_dhw_heating
            name: DHW heating
          - entity: binary_sensor.lg_therma_v_r290_backup_heater_step_1
            name: Heater 1
          - entity: binary_sensor.lg_therma_v_r290_backup_heater_step_2
            name: Heater 2
          - entity: binary_sensor.lg_therma_v_r290_fault
            name: Fault

      # --- Efficiency ---------------------------------------------------------
      # COP against your own meter (option: External electricity meter,
      # power sensor). Without it, use sensor.lg_therma_v_r290_cop_reported
      # (option: Energy registers), which tends to read low.
      - type: gauge
        entity: sensor.lg_therma_v_r290_cop_external_meter
        name: COP now
        min: 0
        max: 7
        needle: true
        severity:
          red: 0
          yellow: 2.5
          green: 3.5
      - type: entities
        title: Efficiency
        entities:
          - entity: sensor.lg_therma_v_r290_thermal_power_calculated
            name: Thermal power (flow × ΔT)
          - entity: sensor.lg_therma_v_r290_electrical_power_heat_pump
            name: Electrical power (unit, reads high)  # option: Energy registers
          - entity: sensor.lg_therma_v_r290_cop_cumulative_external_meter
            name: JAZ since start  # option: External electricity meter, energy sensor
          - entity: sensor.lg_therma_v_r290_thermal_energy_calculated
            name: Heat delivered  # option: External electricity meter, energy sensor

      # --- Controls -----------------------------------------------------------
      - type: entities
        title: Controls
        entities:
          - entity: switch.lg_therma_v_r290_heating_cooling
            name: Heating/Cooling
          - entity: switch.lg_therma_v_r290_dhw
            name: DHW
          - entity: switch.lg_therma_v_r290_silent_mode
            name: Silent mode
          - entity: select.lg_therma_v_r290_operation_mode
          - entity: select.lg_therma_v_r290_control_method
          - entity: number.lg_therma_v_r290_target_temperature_circuit_1_radiators
            name: Flow target circuit 1
          - entity: number.lg_therma_v_r290_setpoint_shift_circuit_1
            name: Shift circuit 1
          - entity: number.lg_therma_v_r290_dhw_target_temperature
            name: DHW target
          - entity: sensor.lg_therma_v_r290_energy_state_reported
            name: Energy state (SG Ready)

      # --- History ------------------------------------------------------------
      - type: history-graph
        title: Temperatures, 24 h
        hours_to_show: 24
        entities:
          - entity: sensor.lg_therma_v_r290_outlet_temperature
            name: Flow
          - entity: sensor.lg_therma_v_r290_inlet_temperature
            name: Return
          - entity: sensor.lg_therma_v_r290_outdoor_temperature
            name: Outdoor
          - entity: sensor.lg_therma_v_r290_dhw_temperature
            name: DHW
      - type: history-graph
        title: Compressor, 24 h
        hours_to_show: 24
        entities:
          - entity: sensor.lg_therma_v_r290_compressor_speed
            name: Speed
          - entity: binary_sensor.lg_therma_v_r290_compressor
            name: Running
          - entity: binary_sensor.lg_therma_v_r290_defrost
            name: Defrost

      # --- Per day (option: Compressor statistics) ----------------------------
      # Starts and run time are counters; "change" per day turns them into
      # starts per day and hours per day. Many starts for few hours = cycling.
      - type: statistics-graph
        title: Compressor starts per day
        chart_type: bar
        period: day
        days_to_show: 30
        stat_types:
          - change
        entities:
          - entity: sensor.lg_therma_v_r290_compressor_starts
            name: Starts
      - type: statistics-graph
        title: Compressor hours per day
        chart_type: bar
        period: day
        days_to_show: 30
        stat_types:
          - change
        entities:
          - entity: sensor.lg_therma_v_r290_compressor_run_time
            name: Hours
      - type: history-graph
        title: Average compressor speed while running, per day
        hours_to_show: 720
        entities:
          - entity: sensor.lg_therma_v_r290_compressor_average_speed
            name: Average rpm

      # --- Energy per day (option: External electricity meter / Energy registers)
      - type: statistics-graph
        title: Heat delivered per day
        chart_type: bar
        period: day
        days_to_show: 30
        stat_types:
          - change
        entities:
          - entity: sensor.lg_therma_v_r290_thermal_energy_calculated
            name: Heat (flow × ΔT)
          - entity: sensor.lg_therma_v_r290_thermal_energy_space_heating
            name: Heat (unit's counter)
```

### Notes

- **Statistics cards** need a day or two of data before they show bars; they read Home Assistant's long-term statistics, not the history.
- **Your own meter:** to compare electrical energy per day, add your meter's energy sensor to the *Heat delivered per day* card (or the Energy dashboard, *Individual devices*).
- **Names** on the cards are short labels set in the YAML; the entities keep their own names elsewhere.

## Full view

A sections view (Home Assistant 2024.3+) with every entity the integration creates: overview with a 24 h history, controls, status and diagnostics, efficiency and energy, the rarely used inputs, the energy states of holding 9, DHW and the experimental registers. Paste it the same way as the compact view. It is a separate dashboard; do not paste it into the compact one.

Most of it needs options switched on in *Configure → Options*; without them those rows show *Entity not found*. Remove them, or switch the option on:

| Option | Cards |
|---|---|
| Energy registers | *Power* (electrical, thermal reported), the COP tiles, *Electrical today*, *Space heating today*, *Counters*, *Demand vs supply* |
| Compressor statistics | *Compressor Average Speed*, *Compressor Starts*, *Compressor Run Time* |
| Compressor modulation limit | *Max Compressor Modulation* |
| Power limit | *Power Limit*, *Max Electrical Power* |
| Poll statistics | *Poll Duration*, *Bus Load* |
| Experimental registers | the *Experimental registers* section |

The *Target Room Air Temperature Circuit 1/2* sensors are disabled by default; enable them in the entity settings or remove the tiles. The weather card uses `weather.forecast_home`, the default of the Met.no integration; replace it with your own weather entity.

*Electrical today* and *Space heating today* read the long-term statistics, so they count from the time the integration was set up: the first day is incomplete.

```yaml
views:
  - title: Therma V
    path: therma-v
    type: sections
    max_columns: 4
    header:
      layout: responsive
      badges_position: bottom
      badges_wrap: wrap
    badges: []
    sections:
      - type: grid
        cards:
          - type: heading
            heading: Overview
          - type: entities
            show_header_toggle: false
            entities:
              - entity: switch.lg_therma_v_r290_heating_cooling
                name: Heating/Cooling
          - type: history-graph
            title: Last 24 h
            hours_to_show: 24
            logarithmic_scale: false
            entities:
              - entity: select.lg_therma_v_r290_control_method
                name: Control Method
              - entity: binary_sensor.lg_therma_v_r290_compressor
                name: Compressor
              - entity: binary_sensor.lg_therma_v_r290_defrost
                name: Defrost
              - entity: sensor.lg_therma_v_r290_outlet_temperature
                name: Outlet Temperature
              - entity: sensor.lg_therma_v_r290_compressor_speed
                name: Compressor Speed
              - entity: sensor.lg_therma_v_r290_outdoor_temperature
                name: Outdoor Temperature
              - entity: sensor.lg_therma_v_r290_temperature_after_evaporator
                name: Temperature After Evaporator
              - entity: sensor.lg_therma_v_r290_temperature_before_evaporator
                name: Temperature Before Evaporator
              - entity: sensor.lg_therma_v_r290_room_air_temperature_circuit_1
                name: Technikraum
              - entity: sensor.lg_therma_v_r290_inlet_temperature
                name: Inlet Temperature
              - entity: sensor.lg_therma_v_r290_flow_rate
                name: Flow Rate
      - type: grid
        cards:
          - type: heading
            heading: Control
          - type: entities
            title: Compressor & limits
            show_header_toggle: false
            entities:
              - entity: sensor.lg_therma_v_r290_compressor_speed
                name: Compressor Speed
              - entity: sensor.lg_therma_v_r290_compressor_average_speed
                name: Compressor Average Speed
              - entity: sensor.lg_therma_v_r290_compressor_starts
                name: Compressor Starts
              - entity: sensor.lg_therma_v_r290_compressor_run_time
                name: Compressor Run Time
              - entity: number.lg_therma_v_r290_max_compressor_modulation
                name: Max Compressor Modulation
              - entity: binary_sensor.lg_therma_v_r290_compressor
                name: Compressor
              - entity: switch.lg_therma_v_r290_silent_mode
                name: Silent Mode
              - entity: binary_sensor.lg_therma_v_r290_silent_mode
                name: Silent mode (status)
              - entity: switch.lg_therma_v_r290_power_limit
                name: Power Limit
              - entity: number.lg_therma_v_r290_max_electrical_power
                name: Max Electrical Power
          - type: entities
            title: Heating circuit 1
            show_header_toggle: false
            entities:
              - entity: sensor.lg_therma_v_r290_outdoor_temperature
                name: Outdoor Temperature
              - entity: sensor.lg_therma_v_r290_outlet_temperature
                name: Outlet Temperature
              - entity: sensor.lg_therma_v_r290_inlet_temperature
                name: Inlet Temperature
              - entity: number.lg_therma_v_r290_target_temperature_circuit_1_radiators
                name: Target Temperature Circuit 1 (Radiators)
              - entity: select.lg_therma_v_r290_control_method
                name: Control Method
              - entity: number.lg_therma_v_r290_setpoint_shift_circuit_1
                name: Setpoint Shift Circuit 1
              - entity: select.lg_therma_v_r290_operation_mode
                name: Operation Mode
              - entity: binary_sensor.lg_therma_v_r290_water_flow
                name: Water Flow
              - entity: sensor.lg_therma_v_r290_flow_rate
                name: Flow Rate
              - entity: sensor.lg_therma_v_r290_operation_state_odu
                name: Operation State (ODU)
              - entity: sensor.lg_therma_v_r290_operation_cycle_odu
                name: Operation cycle ODU (raw)
      - type: grid
        cards:
          - type: heading
            heading: Status & diagnostics
          - type: entities
            show_header_toggle: false
            entities:
              - entity: sensor.lg_therma_v_r290_operation_mode
                name: Operation Mode
              - entity: sensor.lg_therma_v_r290_control_method
                name: Control Method
              - entity: sensor.lg_therma_v_r290_energy_state_reported
                name: Energy state (input 11, reported)
              - entity: sensor.lg_therma_v_r290_energy_state
                name: Energy state (holding 9, command)
              - entity: sensor.lg_therma_v_r290_energy_control_signal
                name: Energy Control Signal
              - entity: sensor.lg_therma_v_r290_product_information
                name: Product Information
              - entity: sensor.lg_therma_v_r290_suction_temperature
                name: Suction Temperature
              - entity: sensor.lg_therma_v_r290_hot_gas_temperature
                name: Hot Gas Temperature
              - entity: sensor.lg_therma_v_r290_liquid_gas_temperature
                name: Liquid Gas Temperature
              - entity: sensor.lg_therma_v_r290_high_pressure_condenser
                name: High Pressure (Condenser)
              - entity: sensor.lg_therma_v_r290_low_pressure_evaporator
                name: Low Pressure (Evaporator)
              - entity: sensor.lg_therma_v_r290_error_code
                name: Error Code
              - entity: binary_sensor.lg_therma_v_r290_fault
                name: Fault
          - type: entities
            title: Power
            show_header_toggle: false
            state_color: false
            entities:
              - entity: sensor.lg_therma_v_r290_electrical_power_heat_pump
                name: Electrical (reported, reads high)
              - entity: sensor.lg_therma_v_r290_thermal_power_reported
                name: Thermal (reported)
              - entity: sensor.lg_therma_v_r290_thermal_power_calculated
                name: Thermal (flow × ΔT)
          - type: weather-forecast
            entity: weather.forecast_home
            show_current: true
            show_forecast: true
            forecast_type: daily
            round_temperature: false
            forecast_slots: 5
      - type: grid
        cards:
          - type: heading
            heading: Efficiency & energy
          - type: tile
            entity: sensor.lg_therma_v_r290_cop_reported
            name: COP (reported)
          - type: tile
            entity: sensor.lg_therma_v_r290_cop_calculated
            name: COP (flow × ΔT)
          - type: tile
            entity: sensor.lg_therma_v_r290_cop_system_reported
            name: COP system
          - type: tile
            entity: sensor.lg_therma_v_r290_cop_heating_cumulative
            name: COP heating (cumulative)
          - type: statistic
            entity: sensor.lg_therma_v_r290_electrical_energy_total
            name: Electrical today
            period:
              calendar:
                period: day
            stat_type: change
          - type: statistic
            entity: sensor.lg_therma_v_r290_thermal_energy_space_heating
            name: Space heating today
            period:
              calendar:
                period: day
            stat_type: change
          - type: entities
            title: Counters (electrical reads high)
            show_header_toggle: false
            state_color: false
            entities:
              - entity: sensor.lg_therma_v_r290_electrical_energy_total
                name: Electrical Energy Total
              - entity: sensor.lg_therma_v_r290_electrical_energy_space_heating
                name: Electrical Energy Space Heating
              - entity: sensor.lg_therma_v_r290_electrical_energy_space_cooling
                name: Electrical Energy Space Cooling
              - entity: sensor.lg_therma_v_r290_thermal_energy_space_heating
                name: Thermal Energy Space Heating
              - entity: sensor.lg_therma_v_r290_electrical_power_total_system
                name: Electrical Power Total System
              - entity: sensor.lg_therma_v_r290_thermal_power_heating_circuit_calculated
                name: Thermal Power Heating Circuit (Calculated)
              - entity: sensor.lg_therma_v_r290_demand_vs_supply
                name: Demand vs supply (0–12)
          - type: history-graph
            title: Water pressure (7 days)
            hours_to_show: 168
            logarithmic_scale: false
            entities:
              - entity: sensor.lg_therma_v_r290_water_pressure
                name: Water Pressure
          - type: entities
            show_header_toggle: false
            entities:
              - entity: sensor.lg_therma_v_r290_poll_duration
                name: Poll Duration
              - entity: sensor.lg_therma_v_r290_bus_load
                name: Bus Load
              - entity: sensor.lg_therma_v_r290_optional_registers
                name: Optional Registers
      - type: grid
        cards:
          - type: heading
            heading: Rarely used
          - type: tile
            entity: binary_sensor.lg_therma_v_r290_external_water_pump
            name: External Water Pump
          - type: tile
            entity: binary_sensor.lg_therma_v_r290_mixing_pump
            name: Mixing Pump
          - type: tile
            entity: sensor.lg_therma_v_r290_flow_temperature_circuit_2
            name: Flow Temperature Circuit 2
          - type: tile
            entity: number.lg_therma_v_r290_target_temperature_circuit_2_underfloor
            name: Target Temperature Circuit 2 (Underfloor)
          - type: tile
            entity: number.lg_therma_v_r290_setpoint_shift_circuit_2
            name: Setpoint Shift Circuit 2
          - type: tile
            entity: sensor.lg_therma_v_r290_room_air_temperature_circuit_2
            name: Room Air Temperature Circuit 2
          - type: tile
            entity: sensor.lg_therma_v_r290_target_room_air_temperature_circuit_1
            name: Target Room Air Temperature Circuit 1
          - type: tile
            entity: sensor.lg_therma_v_r290_target_room_air_temperature_circuit_2
            name: Target Room Air Temperature Circuit 2
          - type: tile
            entity: sensor.lg_therma_v_r290_backup_heater_outlet_temperature
            name: Backup Heater Outlet Temperature
          - type: tile
            entity: binary_sensor.lg_therma_v_r290_backup_heater_step_1
            name: Backup Heater Step 1
          - type: tile
            entity: binary_sensor.lg_therma_v_r290_backup_heater_step_2
            name: Backup Heater Step 2
          - type: tile
            entity: sensor.lg_therma_v_r290_device_group
            name: Device Group
          - type: tile
            entity: binary_sensor.lg_therma_v_r290_solar_pump
            name: Solar Pump
          - type: tile
            entity: sensor.lg_therma_v_r290_solar_collector_temperature
            name: Solar Collector Temperature
          - type: tile
            entity: binary_sensor.lg_therma_v_r290_cooling_active
            name: Cooling active (unreliable)
      - type: grid
        cards:
          - type: heading
            heading: Energy state (holding 9)
          - type: glance
            columns: 3
            state_color: true
            show_state: false
            entities:
              - entity: binary_sensor.lg_therma_v_r290_energy_state_not_used
                name: Not used
              - entity: binary_sensor.lg_therma_v_r290_energy_state_forced_off
                name: Forced off
              - entity: binary_sensor.lg_therma_v_r290_energy_state_normal_operation
                name: Normal
              - entity: binary_sensor.lg_therma_v_r290_energy_state_on_recommendation
                name: On recommend.
              - entity: binary_sensor.lg_therma_v_r290_energy_state_on_command
                name: On command
              - entity: binary_sensor.lg_therma_v_r290_energy_state_on_command_step_2
                name: On cmd step 2
              - entity: binary_sensor.lg_therma_v_r290_energy_state_on_recommendation_step_1
                name: On rec. step 1
              - entity: binary_sensor.lg_therma_v_r290_energy_state_energy_saving_mode
                name: Saving
              - entity: binary_sensor.lg_therma_v_r290_energy_state_super_energy_saving_mode
                name: Super saving
      - type: grid
        cards:
          - type: heading
            heading: DHW (unused)
          - type: tile
            entity: switch.lg_therma_v_r290_dhw
            name: DHW
          - type: tile
            entity: number.lg_therma_v_r290_dhw_target_temperature
            name: DHW Target Temperature
          - type: tile
            entity: sensor.lg_therma_v_r290_dhw_temperature
            name: DHW Temperature
          - type: tile
            entity: binary_sensor.lg_therma_v_r290_dhw_heating
            name: DHW Heating
          - type: tile
            entity: binary_sensor.lg_therma_v_r290_dhw_boost_heater
            name: DHW Boost Heater
          - type: tile
            entity: button.lg_therma_v_r290_start_disinfection
            name: Start Disinfection
          - type: tile
            entity: binary_sensor.lg_therma_v_r290_dhw_disinfection
            name: DHW Disinfection
          - type: tile
            entity: sensor.lg_therma_v_r290_electrical_energy_dhw
            name: Electrical Energy DHW
          - type: tile
            entity: sensor.lg_therma_v_r290_thermal_power_dhw_calculated
            name: Thermal Power DHW (Calculated)
      - type: grid
        cards:
          - type: heading
            heading: Experimental registers
          - type: entities
            show_header_toggle: false
            state_color: false
            entities:
              - entity: sensor.lg_therma_v_r290_experimental_input_30015
                name: Experimental Input 30015
              - entity: sensor.lg_therma_v_r290_experimental_input_30018
                name: Experimental Input 30018
              - entity: sensor.lg_therma_v_r290_experimental_input_30064
                name: Experimental Input 30064
              - entity: sensor.lg_therma_v_r290_experimental_holding_40011
                name: Experimental Holding 40011
              - entity: sensor.lg_therma_v_r290_experimental_holding_40012
                name: Experimental Holding 40012
              - entity: sensor.lg_therma_v_r290_experimental_holding_40013
                name: Experimental Holding 40013
              - entity: sensor.lg_therma_v_r290_experimental_holding_40014
                name: Experimental Holding 40014
              - entity: sensor.lg_therma_v_r290_experimental_holding_40015
                name: Experimental Holding 40015
              - entity: sensor.lg_therma_v_r290_experimental_holding_40016
                name: Experimental Holding 40016
              - entity: sensor.lg_therma_v_r290_experimental_holding_40017
                name: Experimental Holding 40017
              - entity: sensor.lg_therma_v_r290_experimental_holding_40018
                name: Experimental Holding 40018
              - entity: sensor.lg_therma_v_r290_experimental_holding_40019
                name: Experimental Holding 40019
              - entity: sensor.lg_therma_v_r290_experimental_holding_40020
                name: Experimental Holding 40020
              - entity: sensor.lg_therma_v_r290_experimental_holding_40021
                name: Experimental Holding 40021
              - entity: sensor.lg_therma_v_r290_experimental_holding_40022
                name: Experimental Holding 40022
              - entity: sensor.lg_therma_v_r290_experimental_holding_40023
                name: Experimental Holding 40023
              - entity: sensor.lg_therma_v_r290_experimental_holding_40063
                name: Experimental Holding 40063
              - entity: sensor.lg_therma_v_r290_experimental_holding_40064
                name: Experimental Holding 40064
```
