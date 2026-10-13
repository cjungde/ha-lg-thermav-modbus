# Naming

How entities, unique ids and coordinator data are named, so that a new
entity fits without a second look, and a name always says where its value
comes from. Applies from 1.3.0; installations set up earlier are migrated
automatically (see [Migration from 1.2.0 and earlier](#migration-from-120-and-earlier)).

## Entity names

- **English, title case, no abbreviations**: *Outdoor Temperature*, not
  *outside_temp*; *Heating/Cooling*, not *Hauptschalter*. Name what the
  register does per the manual: coil 0 switches space heating/cooling, not the
  whole heat pump.
- **The thing first, the qualifier after**: *Thermal Power DHW*, *COP System*,
  *Electrical Energy Space Heating*. All COP sensors start with *COP*, all
  thermal power sensors with *Thermal Power*, all electrical ones with
  *Electrical*.
- **Where the value comes from**, when there is more than one source for the
  same quantity, as a suffix in parentheses:

  | Suffix | Meaning | Examples |
  |---|---|---|
  | *(Reported)* | the heat pump's own figure, read from its registers | Thermal Power (Reported), COP (Reported), COP System (Reported), Energy State (Reported) |
  | *(Calculated)* | computed by the integration from flow rate × ΔT | Thermal Power (Calculated), Thermal Power DHW (Calculated), COP (Calculated) |
  | *(Cumulative)* | a ratio of the unit's lifetime counters, not a value of the moment | COP Heating (Cumulative) |

  A quantity with only one source carries no suffix (*Flow Rate*, *Outdoor
  Temperature*).
- **Undocumented registers** are named by their number in the manual's
  notation: *Experimental Input 30015*, *Experimental Holding 40011*.

## Unique ids and entity ids

Every unique id is

```
<config entry id>_<key>
```

and the **key is the entity name as Home Assistant slugifies it** (lower case,
everything that is not a letter or digit becomes `_`). With the default device
name *LG ThermaV R290*, the entity id is then `<platform>.lg_thermav_r290_<key>`:

| Name | Key | Entity id |
|---|---|---|
| Outdoor Temperature | `outdoor_temperature` | `sensor.lg_thermav_r290_outdoor_temperature` |
| COP System (Reported) | `cop_system_reported` | `sensor.lg_thermav_r290_cop_system_reported` |
| Energy State: Normal Operation | `energy_state_normal_operation` | `binary_sensor.lg_thermav_r290_energy_state_normal_operation` |
| Experimental Input 30015 | `experimental_input_30015` | `sensor.lg_thermav_r290_experimental_input_30015` |

So key, unique id and entity id can be read off the name, and
`tests/test_migration.py` checks that every key is the slug of its name.
All entities derive from `LGEntity` (`entity.py`), which builds the unique id
and the device info in one place.

A renamed entity keeps its key (and so its unique id and history) unless the
key is renamed deliberately with a migration step.

## Coordinator data keys

The coordinator returns one flat dict per poll. Its keys say which kind of
register a value comes from, followed by the key of the entity that shows it:

| Prefix | Register type | Example |
|---|---|---|
| `input_` | input register (FC04) | `input_outdoor_temperature` |
| `holding_` | holding register (FC03) | `holding_dhw_target_temperature` |
| `coil_` | coil (FC01) | `coil_heating_cooling` |
| `discrete_` | discrete input (FC02) | `discrete_compressor` |

Two entities that show the same register share its data key: *Energy Control
Signal* and *Energy State (Reported)* both read `input_energy_control_signal`.
Values are scaled in the coordinator; entities do not scale again. The one exception are the experimental registers, which are kept raw on purpose: what they mean is the open question.

The optional groups use the same prefixes: `energy.py` (`input_<key>` per
32-bit register, e.g. `input_electrical_power_heat_pump`), `limits.py`
(`holding_max_compressor_modulation`), and `experimental.py`, which has no
meaningful name to use and keys by register number instead (`input_30015`,
`holding_40011`).

## Module constants

- `KEY_…` — an entity key, e.g. `KEY_MAX_COMPRESSOR_MODULATION`.
- `DATA_KEY_…` — a coordinator data key, e.g. `DATA_KEY_THERMAL_POWER_REPORTED`.
- `CONF_…` — a config entry option or setting.
- Register addresses are 0-based in code, with the manual's 5-digit number in
  a comment (`# 40024`).

## Migration of older installations

Up to 1.2.0 the unique ids had grown one by one: abbreviations
(`inlet_temp`), German (`hauptschalter`), typos (`dhw_desinfection_start`,
`flow_temp_circle_2`, `temp_before_vaporiser`) and prefixes that no longer
said anything (`energy_reg_`, `exp_`, `di_`).

On the first start of 1.3.0, the config entry migration in `__init__.py`
rewrites the unique ids in the entity registry using the table in
`migration.py` (config entry minor version 1 → 2). The registry entries are
changed in place, so **entity ids, history, statistics and automations stay
exactly as they are**; only the unique id behind them changes. An id that is
already taken is left alone and logged, not failed.

Later renames are added as further steps in `MIGRATION_STEPS`, each raising
the config entry minor version by one:

| Minor version | Step |
|---|---|
| 1 → 2 | the 1.3.0 table (`UNIQUE_KEY_RENAMES`) |
| 2 → 3 | coil 0 switch `heat_pump` → `heating_cooling` (*Heat Pump* → *Heating/Cooling*) |
| 3 → 4 | holding 40004/40007 sensors `room_air_temperature_circuit_1_holding` / `_2_holding` → `target_room_air_temperature_circuit_1` / `_2` (they hold the room temperature target, not the measured value) |

An entry runs every step above its minor version, in order, so an
installation from before 1.3.0 goes `hauptschalter` → `heat_pump` →
`heating_cooling` in one start. Each step runs once per installation, at
setup, never per poll.

Entity ids are never changed by the integration: an installation from before
1.3.0 keeps its entity ids even where the entity's name has changed since
(see the table in the README's *Notes*). Renaming them is up to the user,
in *Settings → Entities*.
