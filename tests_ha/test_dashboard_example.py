"""Every entity of the integration in the example dashboards exists, with all options on.

The compact view is inline in docs/dashboard.md, the full view is its own file,
docs/dashboard-full.yaml.
"""

from __future__ import annotations

from pathlib import Path
import re

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
import yaml

from .test_config_flow import DOMAIN, RTU

DOCS = Path(__file__).resolve().parent.parent / "docs"
DASHBOARD = DOCS / "dashboard.md"
FULL_VIEW = DOCS / "dashboard-full.yaml"


def _entity_ids() -> set[str]:
    text = DASHBOARD.read_text()
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "entity":
                    found.add(value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    blocks = re.findall(r"```yaml\n(.*?)```", text, re.S)
    assert blocks, "the compact view is no longer inline in dashboard.md"
    blocks.append(FULL_VIEW.read_text())
    assert "dashboard-full.yaml" in text, "dashboard.md does not link the full view"
    for block in blocks:
        walk(yaml.safe_load(block))
    # Only the integration's own entities; e.g. the weather card is the user's.
    return {i for i in found if ".lg_therma_v_r290_" in i}


async def test_every_dashboard_entity_exists(hass, unit) -> None:
    hass.states.async_set("sensor.meter_power", "1", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.meter_energy", "1", {"unit_of_measurement": "kWh"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options={
            "energy_registers": True,
            "compressor_modulation_limit": True,
            "power_limit": True,
            "emergency_operation_button": True,
            "experimental_registers": True,
            "compressor_statistics": True,
            "poll_statistics": True,
            "external_power_sensor": "sensor.meter_power",
            "external_energy_sensor": "sensor.meter_energy",
        },
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    ids = _entity_ids()
    assert len(ids) > 20
    missing = sorted(i for i in ids if registry.async_get(i) is None)
    assert missing == []
