# Shadow install — build, compare, remove

A change to the Modbus layer cannot be judged from a test suite alone. The
register map, the block planning and the framing only prove themselves against
the actual heat pump, and the only honest comparison is against the version
that is already running, on the same hardware, at the same time.

That is what these two files are for.

## What the shadow is

`make_shadow.py` copies the integration into a second domain,
`lg_thermav_r290_test`, which Home Assistant then treats as an unrelated
integration: its own config entry, its own device, its own entities. The live
entry cannot see it and nothing that feeds off the live entry — the COP chain,
the DHW automations, the adaptive control in pyscript — can reach it.

Three properties make it safe to leave running next to production:

**It cannot command the heat pump.** The `switch`, `button`, `number` and
`select` platforms are *deleted* from the copy, not merely left unregistered.
There is no file in the shadow that could write a coil or a holding register,
and the script refuses to produce a copy where one survives. A heat pump is not
a meter: a duplicated DHW-target `number` or a second "start disinfection"
button would be a live control onto real hardware.

**Its entities do not share the production prefix.** The device is named
`ThermaV Testkopie`, so the entities are `sensor.thermav_testkopie_*`. This is
not cosmetic. `/config/influxdb.yaml` selects what to export with the glob
`sensor.lg_thermav_r290*`; a shadow named "… Test" would match it and write a
second, five-minute-stale copy of every reading into the time series database.
Renaming out of the prefix also protects against any future pattern written
against the production name.

**It barely touches the bus.** Production polls every 10 s; the shadow polls
every 300 s. It also opens no socket of its own — its connection parameters
equal those of any other entry pointing at the same gateway, so
`async_get_unit` hands it a unit on the existing shared connection and its
requests queue behind that connection's lock.

## Build and install

```bash
python3 tools/make_shadow.py /config/custom_components
```

Then restart Home Assistant and add **LG ThermaV R290 (Testkopie, nur lesend)**
from Settings → Devices & Services, with the same host, port and slave id as
the live entry.

Re-run the script after every code change rather than keeping two copies that
drift apart. It replaces the shadow in place, and it aborts — deleting the
half-written copy — if any of its substitutions no longer matches exactly once.

## Compare

Paste `compare_shadow.jinja` into Developer Tools → Template. It walks the
shadow entities, looks up each production twin, and prints both values with the
delta and a per-quantity tolerance.

Run it at least twice: once while the compressor is idle, where everything must
agree, and once during a compressor run, where the fast-moving quantities may
differ from the 300 s sampling skew alone but the slow ones still may not.

## Remove

Nothing about the shadow is load-bearing, and removing it is three steps:

1. **Delete the config entry.** Settings → Devices & Services →
   "LG ThermaV R290 (Testkopie, nur lesend)" → ⋮ → Delete. Home Assistant
   removes the device and all its entities with it.
2. **Delete the files.**
   ```bash
   rm -rf /config/custom_components/lg_thermav_r290_test
   ```
3. **Restart Home Assistant.**

What is left afterwards is the recorded history: states, which the recorder
purges on its normal schedule, and long-term statistics for the numeric
sensors, which it does not. Those show up under Developer Tools → Statistics as
entries with no matching entity and can be deleted there in one pass.

The live integration is untouched by all of this. It kept its own domain, its
own entities and its own pymodbus connection throughout.
