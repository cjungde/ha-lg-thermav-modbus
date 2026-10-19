"""The fix behind a "never answered" notice: switch the option off (issues.py)."""

from __future__ import annotations

from typing import Any

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant


class SwitchOptionOffFlow(RepairsFlow):
    """Confirm, then switch the option off; the entry reloads without it."""

    def __init__(self, entry_id: str, group: str) -> None:
        self._entry_id = entry_id
        self._group = group

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            # Removed in the meantime; nothing left to switch off.
            return self.async_abort(reason="entry_removed")
        if user_input is not None:
            # The update listener reloads the entry, which removes the
            # option's entities and this notice.
            self.hass.config_entries.async_update_entry(
                entry, options={**entry.options, self._group: False}
            )
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm", description_placeholders={"entry": entry.title}
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    assert data is not None
    return SwitchOptionOffFlow(str(data["entry_id"]), str(data["group"]))
