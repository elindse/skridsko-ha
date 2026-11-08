"""Beskrivelser i loggboken (aktivitetslisten på enhetssiden)."""
from __future__ import annotations

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_OBSERVATION
from .hub import EVENT_LOGIN_CHECK


@callback
def async_describe_events(hass: HomeAssistant, async_describe_event) -> None:
    @callback
    def describe_obs(event: Event) -> dict[str, str]:
        d = event.data
        ch = " og ".join(d.get("channels") or []) or "ikke sendt"
        n = d.get("images", 0)
        return {LOGBOOK_ENTRY_NAME: "Skridsko",
                LOGBOOK_ENTRY_MESSAGE: f"varsel {d.get('name')}: {d.get('status')} · {ch} · {n} bilde{'r' if n != 1 else ''}"}

    @callback
    def describe_login(event: Event) -> dict[str, str]:
        ok = event.data.get("ok")
        return {LOGBOOK_ENTRY_NAME: "Skridsko",
                LOGBOOK_ENTRY_MESSAGE: "innloggingen virker igjen" if ok else "innloggingen har gått ut"}

    async_describe_event(DOMAIN, EVENT_OBSERVATION, describe_obs)
    async_describe_event(DOMAIN, EVENT_LOGIN_CHECK, describe_login)
