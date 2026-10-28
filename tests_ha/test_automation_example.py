"""The example automations in docs/automations.md are valid and use real entities.

AutoTemp is its own file, docs/autotemp-heat-circuit-1.yaml; the start and stop
automations are inline in docs/automations.md.
"""

from __future__ import annotations

from pathlib import Path
import re

from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import yaml

from custom_components.lg_therma_v_r290.const import CONTROL_METHOD_OPTIONS

from .test_config_flow import DOMAIN, RTU

DOCS = Path(__file__).resolve().parent.parent / "docs"
AUTOMATIONS = DOCS / "automations.md"
AUTOTEMP = DOCS / "autotemp-heat-circuit-1.yaml"


def _configs() -> list[dict]:
    text = AUTOMATIONS.read_text()
    assert AUTOTEMP.name in text, "automations.md does not link the AutoTemp file"
    blocks = re.findall(r"```yaml\n(.*?)```", text, re.S)
    assert len(blocks) == 2, "expected the start and stop automations inline"
    return [yaml.safe_load(b) for b in blocks] + [yaml.safe_load(AUTOTEMP.read_text())]


def _texts() -> str:
    return AUTOMATIONS.read_text() + AUTOTEMP.read_text()


def test_control_method_options_exist() -> None:
    used = set(re.findall(r"(\w+ Water Temp Control|Room Air Control)", _texts()))
    assert used
    assert used <= set(CONTROL_METHOD_OPTIONS)


async def test_every_automation_entity_exists(hass, unit) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"connection_type": "rtu", **RTU},
        options={"compressor_modulation_limit": True},
        version=1,
        minor_version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    ids = set(re.findall(r"\b\w+\.lg_therma_v_r290_\w+", _texts()))
    assert len(ids) > 5
    missing = sorted(i for i in ids if registry.async_get(i) is None)
    assert missing == []


# The time and time_pattern triggers schedule timers that outlive the test.
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_automations_load(hass) -> None:
    configs = _configs()
    for i, config in enumerate(configs):
        config["id"] = f"example_{i}"
    assert await async_setup_component(hass, "automation", {"automation": configs})
    await hass.async_block_till_done()

    states = hass.states.async_all("automation")
    assert len(states) == len(configs)
    # An automation Home Assistant rejects is created unavailable.
    assert sorted(s.state for s in states) == ["on"] * len(configs)
