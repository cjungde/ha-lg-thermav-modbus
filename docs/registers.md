# Modbus register map

The four tables of the R290 installation manual (*Modbus-Speicherzuordnung*), each register with the manual's wording (German, as printed) and what the integration makes of it. Registers the manual does not list, but the integration reads, follow each table. Addresses in code are 0-based: manual register 30003 is input address 2, 40001 is holding address 0, 00001 is coil 0, 10001 is discrete input 0. Entity ids are given without the `lg_therma_v_r290_` prefix.

Marks: ⚠ the unit behaves differently from the manual (measured) · ⚙ only with an option (*Configure*) · ⛔ disabled by default · ✗ not read or written

### Coils (FC01 / write FC05)

| Register | Manual: Beschreibung | Manual: Werte | Integration |
|---|---|---|---|
| 00001 | Aktivieren / Deaktivieren (Heizung / Kühlung) | 0: Betrieb AUS / 1: Betrieb EIN | `switch.heating_cooling` — space heating/cooling only; DHW is 00002 |
| 00002 | Aktivieren / Deaktivieren (ECS) | 0: Betrieb AUS / 1: Betrieb EIN | `switch.dhw` |
| 00003 | Einstellung Ruhemodus | 0: Ruhemodus AUS / 1: Ruhemodus EIN | `switch.silent_mode` |
| 00004 | Auslösung Desinfektionsbetrieb | 0: Status halten / 1: Betriebsstart | `button.start_disinfection` — a trigger, the unit clears it; status in 10007 |
| 00005 | Notaus | 0: Normaler Betrieb / 1: Notaus | `switch.emergency_stop` |
| 00006 | Auslöser Notaus-Betrieb | 0: Status halten / 1: Betriebsstart | ⚙ `button.start_emergency_operation` — *Emergency operation button* option; writable only then |
| 00007 | Wirkleistungsbegrenzung | 0: Nicht verwendet / 1: Begrenzen Sie die Leistung gemäß der Vorschrift 40025 | ⚙ `switch.power_limit` — *Power limit* option; writable only then; no answer on the scanned 9 kW |

### Discrete inputs (FC02)

| Register | Manual: Beschreibung | Manual: Werte | Integration (`binary_sensor.…`) |
|---|---|---|---|
| 10001 | Status Wasserdurchfluss | 0: Durchflussrate OK / 1: Durchflussrate zu niedrig | ⚠ `water_flow` — on the R290 **1 means water is flowing**, the opposite of the manual; device class *running* (see [Binary sensors](../README.md#binary-sensors)) |
| 10002 | Wasserpumpenstatus | 0: Wasserpumpen AUS / 1: Wasserpumpen EIN | `water_pump` |
| 10003 | Ext. Wasserpumpenstatus | 0: Wasserpumpen AUS / 1: Wasserpumpen EIN | `external_water_pump` |
| 10004 | Kompressorstatus | 0: Kompressor AUS / 1: Kompressor EIN | `compressor` |
| 10005 | Abtaustatus | 0: Abtauen AUS / 1: Abtauen EIN | `defrost` |
| 10006 | WW-Heizstatus (WW Thermisch Ein/Aus) | 0: WW inaktiv / 1: WW aktiv | `dhw_heating` — also splits the calculated thermal power into heating circuit / DHW |
| 10007 | Desinfektionsstatus WW-Speicher | 0: Desinfektion inaktiv / 1: Desinfektion aktiv | `dhw_disinfection` |
| 10008 | Status Ruhemodus | 0: Ruhemodus inaktiv / 1: Ruhemodus aktiv | `silent_mode` |
| 10009 | Kühlstatus | 0: Keine Kühlung / 1: Kühlbetrieb | ⚠ `cooling_active` — measured **1 during heating**; not usable on the R290 (see [Binary sensors](../README.md#binary-sensors)) |
| 10010 | Status der Solarpumpe | 0: Solarpumpe AUS / 1: Solarpumpe EIN | `solar_pump` |
| 10011 | Status Zusatzheizung (Schritte 1) | 0: AUS / 1: EIN | `backup_heater_step_1` |
| 10012 | Status Zusatzheizung (Schritte 2) | 0: AUS / 1: EIN | `backup_heater_step_2` |
| 10013 | Status WW-Verstärkerheizung | 0: AUS / 1: EIN | `dhw_boost_heater` |
| 10014 | Fehlermeldung | 0: Kein Fehler / 1: Fehlerstatus | `fault` |
| 10015 | Notbetrieb verfügbar (Raumheizung/-Kühlung) | 0: Nicht verfügbar / 1: Verfügbar | `emergency_heating_cooling_available` |
| 10016 | Notbetrieb verfügbar (WW) | 0: Nicht verfügbar / 1: Verfügbar | `emergency_dhw_available` |
| 10017 | Status Mischpumpe | 0: Mischpumpe AUS / 1: Mischpumpe EIN | `mixing_pump` |

### Input registers (FC04)

| Register | Manual: Beschreibung | Manual: Werte | Integration (`sensor.…`) |
|---|---|---|---|
| 30001 | Fehlerkennung | Fehlerkennung | `error_code` |
| 30002 | ODU-Betriebszyklus | 0: Standby (AUS) / 1: Kühlung / 2: Heizung | `operation_cycle_odu` (raw) and `operation_state_odu` (label) |
| 30003 | Wassereinlasstemp. | [0.1 °C ×10] | `inlet_temperature` |
| 30004 | Wasserauslasstemp. | [0.1 °C ×10] | `outlet_temperature` |
| 30005 | Auslasstemp. Ersatzheizgerät | [0.1 °C ×10] | `backup_heater_outlet_temperature` |
| 30006 | Wassertemp. Warmwasserbehälter | [0.1 °C ×10] | `dhw_temperature` |
| 30007 | Sonnenkollektortemp. | [0.1 °C ×10] | `solar_collector_temperature` |
| 30008 | Raumlufttemp. (Kreislauf 1) | [0.1 °C ×10] | `room_air_temperature_circuit_1` — measured at the wired remote controller; without one, the indoor unit's own sensor |
| 30009 | Aktuelle Durchflussrate | [0.1 LPM ×10] | `flow_rate` |
| 30010 | Durchflusstemp. (Kreislauf 2) | [0.1 °C ×10] | `flow_temperature_circuit_2` |
| 30011 | Raumlufttemp. (Kreislauf 2) | [0.1 °C ×10] | `room_air_temperature_circuit_2` |
| 30012 | Energiezustand-Eingang | 0 : Energiezustand 0; 1 : Energiezustand 1… | `energy_control_signal` (raw) and `energy_state_reported` (label, same 0–8 table as 40010) |
| 30013 | Außenlufttemp. | [0.1 °C ×10] | `outdoor_temperature` |
| 30014 | Wasserdruck | [0.1 bar ×10] | `water_pressure` |
| 39998 | Gerätegruppe | 0x8X (0x80, 0x83, 0x88, 0x89) | `device_group` — read once per start, not per poll |
| 39999 | Geräteinfo | Split: 0 / Monoblock: 3 / Hochtemp. : 4 / Mittlere Temp. : 5 / System-Boiler: 6 | `product_information` — the raw number, read once per start; the scanned 9 kW reads 8208 (0x2010), not in this list |

**Not in the manual**, read by the integration (meaning and scale from community projects and measurement, see [register-scan.md](register-scan.md)):

| Register | Integration (`sensor.…`) | Scale |
|---|---|---|
| 30015 | ⚙ `experimental_input_30015` (*Experimental registers*) | raw |
| 30016 | ✗ — no answer; a block read that includes it fails | — |
| 30017 | `liquid_gas_temperature` | 0.1 °C |
| 30018 | ⚙ `experimental_input_30018` — constant 12000, not a temperature | raw |
| 30019 / 30020 | `suction_temperature` / `hot_gas_temperature` | 0.1 °C |
| 30021 / 30022 | `temperature_before_evaporator` / `temperature_after_evaporator` | 0.1 °C |
| 30023 / 30024 | `high_pressure_condenser` / `low_pressure_evaporator` | 0.01 bar |
| 30025 | `compressor_speed` | Hz × 60 = rpm |
| 30035–30052 | ⚙ *Energy registers*: `electrical_power_total_system`, `electrical_power_heat_pump`, `electrical_energy_total`, `electrical_energy_space_heating`, `electrical_energy_space_cooling`, `electrical_energy_dhw`, `demand_vs_supply`, `thermal_power_reported`, `thermal_energy_space_heating` — no answer on the scanned 9 kW | 32-bit, W / Wh |
| 30053–30056 | ✗ — no answer on a 12 kW | — |
| 30064 | ⚙ `experimental_input_30064` | raw |

### Holding registers (FC03 / write FC06)

| Register | Manual: Beschreibung | Manual: Werte | Integration |
|---|---|---|---|
| 40001 | Betriebsmodus | 0: Kühlung / 4: Heizung / 3: Auto | `select.operation_mode` + `sensor.operation_mode` |
| 40002 | Steuermethode (Kreis 1/2) | 0: Wasserauslasstemp. Steuerung / 1: Wassereinlasstemp. Steuerung / 2: Raumluftsteuerung | `select.control_method` + `sensor.control_method` |
| 40003 | Zieltemp. (Heizung / Kühlung) Kreislauf 1 | [0.1 °C ×10] | `number.target_temperature_circuit_1_radiators` (20–60 °C) |
| 40004 | Raumlufttemp. Kreislauf 1 | [0.1 °C ×10] | ⛔ `sensor.target_room_air_temperature_circuit_1` — read only, disabled by default; as a holding register this is the room temperature *target* (the measured value is input 30008) |
| 40005 | Schaltwert (Ziel) im Auto-Modus Kreislauf 1 | 1K | `number.setpoint_shift_circuit_1` (−5…+5 K) |
| 40006 | Zieltemp. (Heizung / Kühlung) Kreislauf 2 | [0.1 °C ×10] | `number.target_temperature_circuit_2_underfloor` (20–40 °C) |
| 40007 | Raumlufttemp. Kreislauf 2 | [0.1 °C ×10] | ⛔ `sensor.target_room_air_temperature_circuit_2` — read only, disabled by default; the room temperature *target* (the measured value is input 30011) |
| 40008 | Schaltwert (Ziel) im Auto-Modus Kreislauf 2 | 1K | `number.setpoint_shift_circuit_2` (−5…+5 K) |
| 40009 | WW-Ziel Temp. | [0.1 °C ×10] | `number.dhw_target_temperature` (35–65 °C) |
| 40010 | Energiezustand-Eingang | see below | `sensor.energy_state` (label) + `binary_sensor.energy_state_*` (one per value) — read only |
| 40025 | Leistungsbegrenzungswert | 0.1 kW ~ 25.0 kW | ⚙ `number.max_electrical_power` (0.1–25.0 kW) — *Power limit* option; writable only then; applied while coil 00007 is on; no answer on the scanned 9 kW |

40010 *Energiezustand-Eingang*, with the SG-Ready terminal states the manual gives as equivalent:

| Value | Manual | Integration label |
|---|---|---|
| 0 | Nicht verwenden | `0 – Not Used` |
| 1 | Erzwungen Aus (gleich TB_SG1=schließen / TB_SG2=öffnen) | `1 – Forced Off` |
| 2 | Normalbetrieb (gleich TB_SG1=öffnen / TB_SG2=schließen) | `2 – Normal Operation` |
| 3 | Ein-Empfehlung (gleich TB_SG1=öffnen / TB_SG2=schließen) | `3 – On Recommendation` |
| 4 | Ein-Befehl (gleich TB_SG1=schließen / TB_SG2=öffnen) | `4 – On Command` |
| 5 | Ein-Befehl Schritt 2 (++ Stromverbrauch verglichen mit Normal) | `5 – On Command Step 2` |
| 6 | Ein-Empfehlung Schritt 1 (+ Stromverbrauch verglichen mit Normal) | `6 – On Recommendation Step 1` |
| 7 | Energiesparmodus (Stromverbrauch verglichen mit Normal) | `7 – Energy Saving Mode` |
| 8 | Superenergiesparmodus (--Stromverbrauch verglichen mit Normal) | `8 – Super Energy Saving Mode` |

(The terminal states for 1/4 and 2/3 are printed identically in the manual.)

**Not in the manual**, read by the integration:

| Register | Integration | Notes |
|---|---|---|
| 40011–40023 | ⚙ `sensor.experimental_holding_40011` … `_40023` (*Experimental registers*) | raw; all 0 on the scanned 9 kW |
| 40024 | ⚙ `number.max_compressor_modulation` (*Compressor modulation limit*) | 40–100 %, 0 = no limit; writable only with the option; no answer on the scanned 9 kW |
| 40063 / 40064 | ⚙ `sensor.experimental_holding_40063` / `_40064` | raw |

The integration only ever writes coils 00001–00005 and holding 40001, 40002, 40003, 40005, 40006, 40008, 40009, plus 40024, 40025, 00006 and 00007 while their options are on. Every other write is refused before it reaches the bus.
