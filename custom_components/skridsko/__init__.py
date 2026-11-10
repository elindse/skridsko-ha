"""Skridsko isobservasjoner for Home Assistant."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .hub import SkridskoHub

_LOGGER = logging.getLogger(__name__)
CARD_URL = "/skridsko_static/skridsko-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Gjør dashbordkortet tilgjengelig (custom:skridsko-card)."""
    hass.data.setdefault(DOMAIN, {})
    path = Path(__file__).parent / "www" / "skridsko-card.js"
    try:
        from homeassistant.components.http import StaticPathConfig
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(path), False)])
    except ImportError:  # eldre Home Assistant
        hass.http.register_static_path(CARD_URL, str(path), False)
    try:
        from homeassistant.components.frontend import add_extra_js_url
        add_extra_js_url(hass, f"{CARD_URL}?v=0.4.0")
    except Exception as err:  # frontend ikke lastet
        _LOGGER.debug("Kunne ikke registrere kortet automatisk: %s", err)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = SkridskoHub(hass, entry)
    await hub.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hub: SkridskoHub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.async_stop()
    return ok


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
