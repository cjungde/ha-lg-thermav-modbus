"""Repairs notices for optional registers the unit never answered.

When an option is on but its registers have not answered once since the
integration started, the read is given up (energy.RetryBackoff) and a notice
appears under Settings → Repairs, with a button that switches the option off
(repairs.py). The notice is not persistent: it belongs to one run, and goes
away when the entry unloads -- on a reload after the option changed, on
removal, or with Home Assistant. If the unit still does not answer after a
restart, the next run raises it again.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .register_status import BACKOFF_GROUPS


def issue_id(entry_id: str, group: str) -> str:
    return f"{entry_id}_{group}_never_answered"


def raise_never_answered(hass: HomeAssistant, entry: ConfigEntry, group: str) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(entry.entry_id, group),
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=f"{group}_never_answered",
        translation_placeholders={"entry": entry.title},
        data={"entry_id": entry.entry_id, "group": group},
    )


def clear_never_answered(hass: HomeAssistant, entry_id: str) -> None:
    for group in BACKOFF_GROUPS:
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry_id, group))
