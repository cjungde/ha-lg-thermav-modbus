#!/usr/bin/env python3
"""Build a read-only shadow copy of the integration to run beside the live one.

The point is to prove the rewritten Modbus layer against the same physical heat
pump, at the same time, without the live entry noticing. The shadow declares
its own domain, so Home Assistant treats it as an unrelated integration: its
own config entry, its own device, its own entities. Nothing the production
entry feeds -- the COP chain, the DHW automations, the adaptive control -- can
see it.

**The shadow cannot command the heat pump.** The switch, button, number and
select platforms are deleted from the copy rather than merely unregistered, so
there is no file left that could write a coil or a holding register. A heat
pump is not a meter: a duplicated `number` for the DHW target or a duplicated
"start disinfection" button would be a live control onto real hardware, one
mis-click or one careless automation pattern away from changing how the house
is heated. What the migration actually has to prove is the read path -- 25
input registers, 10 holding registers, 6 coils, 17 discrete inputs, all of it
re-planned by a different backend -- and that is fully covered without a single
write. The write path is four lines that go through the same unit object, the
same lock and the same exception type as the reads.

Two further things follow from the shared connection and are worth knowing
before running this:

* The shadow does not open a socket of its own. Its parameters are equal to
  those of any other entry pointing at the same gateway the same way, so
  `async_get_unit` hands it a unit on the connection that already exists and
  its requests serialize behind that connection's lock.
* The production entry, still on pymodbus, keeps its own socket. During the
  comparison the RS485 line therefore carries both -- which is exactly the
  contention the migration is meant to end, so the scan interval below is
  slackened to keep the shadow's share of it small.

Usage:

    python3 tools/make_shadow.py <target-dir>

where <target-dir> is the Home Assistant ``custom_components`` directory, e.g.

    python3 tools/make_shadow.py /config/custom_components

Re-running replaces the shadow, so regenerate it after every code change rather
than maintaining two copies that drift apart.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

SOURCE_DOMAIN = "lg_thermav_r290"
SHADOW_DOMAIN = "lg_thermav_r290_test"

# Everything that can write to the heat pump. Deleted, not disabled.
WRITING_PLATFORMS = ("switch.py", "button.py", "number.py", "select.py")

READ_ONLY_PLATFORMS = '["sensor", "binary_sensor"]'

# The device name, and with it the entity id prefix: sensor.thermav_testkopie_*.
# Chosen so that no existing glob written against the production entities can
# match the shadow -- see the note on the substitutions below.
SHADOW_DEVICE_NAME = "ThermaV Testkopie"
SHADOW_ENTITY_PREFIX = "thermav_testkopie"

# (relative path, exact text to find, replacement). Every one of these must
# match exactly once; a miss means the component moved on and this script is
# stale, which is worth failing over rather than shipping a half-renamed copy
# -- or, worse, a copy that still carries a control surface.
SUBSTITUTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "manifest.json",
        f'"domain": "{SOURCE_DOMAIN}"',
        f'"domain": "{SHADOW_DOMAIN}"',
    ),
    (
        "manifest.json",
        '"name": "LG ThermaV R290"',
        '"name": "LG ThermaV R290 (Testkopie, nur lesend)"',
    ),
    (
        "const.py",
        f'DOMAIN = "{SOURCE_DOMAIN}"',
        f'DOMAIN = "{SHADOW_DOMAIN}"',
    ),
    # Production polls every 10 s. The comparison needs nothing like that, and
    # every request the shadow skips is one the live entry does not queue behind.
    (
        "const.py",
        "DEFAULT_SCAN_INTERVAL = 30",
        "DEFAULT_SCAN_INTERVAL = 300",
    ),
    (
        "__init__.py",
        'PLATFORMS = ["sensor", "binary_sensor", "switch", "button", "number", "select"]',
        f"PLATFORMS = {READ_ONLY_PLATFORMS}  # shadow: read-only, cannot command the heat pump",
    ),
    # The entities set _attr_has_entity_name, so the device name is what the
    # entity ids are derived from. The shadow deliberately does NOT keep the
    # production prefix: /config/influxdb.yaml selects what to export with the
    # glob 'sensor.lg_thermav_r290*', and a shadow named "LG ThermaV R290 Test"
    # would match it and start writing a second, five-minute-stale copy of every
    # reading into the time series database. Renaming the device out of the
    # prefix is a surer fix than adding an exclusion, because it also protects
    # against any future pattern written against the production name.
    (
        "sensor.py",
        'name="LG ThermaV R290",',
        f'name="{SHADOW_DEVICE_NAME}",',
    ),
    (
        "binary_sensor.py",
        'name="LG ThermaV R290",',
        f'name="{SHADOW_DEVICE_NAME}",',
    ),
)

IGNORE = shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc")


def build(source: Path, target_parent: Path) -> Path:
    """Copy the component, strip its controls, and rewrite it into the shadow domain."""
    target = target_parent / SHADOW_DOMAIN
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=IGNORE)

    for name in WRITING_PLATFORMS:
        path = target / name
        if not path.is_file():
            shutil.rmtree(target)
            raise SystemExit(
                f"{name} is missing from the component. Either it was renamed or "
                "the platform moved; check WRITING_PLATFORMS before going on, "
                "because a shadow that still ships a control is the one thing "
                "this script must not produce."
            )
        path.unlink()

    for filename, old, new in SUBSTITUTIONS:
        path = target / filename
        text = path.read_text()
        count = text.count(old)
        if count != 1:
            shutil.rmtree(target)
            raise SystemExit(
                f"{filename}: expected exactly one occurrence of {old!r}, "
                f"found {count}. The component changed; update SUBSTITUTIONS."
            )
        path.write_text(text.replace(old, new))

    # A leftover reference means a substitution was forgotten, not that the
    # copy is merely cosmetic: two components claiming one domain break both.
    stale = [
        p.relative_to(target)
        for p in target.rglob("*")
        if p.is_file()
        and p.suffix in {".py", ".json"}
        and SOURCE_DOMAIN in p.read_text()
        and SHADOW_DOMAIN not in p.read_text()
    ]
    if stale:
        shutil.rmtree(target)
        raise SystemExit(f"stale references to {SOURCE_DOMAIN} in: {stale}")

    # Belt and braces: nothing in the shadow may reach a write function.
    writes = sorted(
        f"{p.relative_to(target)}: {call}"
        for p in target.rglob("*.py")
        for call in ("async_write_coil", "async_write_register")
        if f"{call}(" in p.read_text() and p.name != "coordinator.py"
    )
    if writes:
        shutil.rmtree(target)
        raise SystemExit(f"the shadow can still write to the device: {writes}")

    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        type=Path,
        help="Home Assistant custom_components directory",
    )
    args = parser.parse_args()

    source = (
        Path(__file__).resolve().parent.parent / "custom_components" / SOURCE_DOMAIN
    )
    if not source.is_dir():
        raise SystemExit(f"component not found at {source}")
    if not args.target.is_dir():
        raise SystemExit(f"not a directory: {args.target}")

    target = build(source, args.target)
    print(f"shadow written to {target}")
    print("Restart Home Assistant, then add 'LG ThermaV R290 (Testkopie, nur lesend)'.")
    print(f"Entities appear as sensor.{SHADOW_ENTITY_PREFIX}_* and")
    print(f"binary_sensor.{SHADOW_ENTITY_PREFIX}_*, polled every 300 s.")
    print("No switch, button, number or select entity is created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
