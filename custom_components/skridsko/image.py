from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import SkridskoEntity
from .hub import SkridskoHub


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([LastImage(hass, hass.data[DOMAIN][entry.entry_id], "last_image")])


class LastImage(SkridskoEntity, ImageEntity):
    """Første bilde fra siste observasjon. Bildene på bild.skridsko.net er offentlige."""

    def __init__(self, hass: HomeAssistant, hub: SkridskoHub, key: str) -> None:
        SkridskoEntity.__init__(self, hub, key)
        ImageEntity.__init__(self, hass)
        self._set_from_hub()

    def _set_from_hub(self) -> None:
        last = self.hub.last or {}
        url = (last.get("images") or [None])[0]
        if url != self._attr_image_url:
            self._attr_image_url = url
            self._cached_image = None
            received = dt_util.parse_datetime(last.get("received") or "") if last else None
            self._attr_image_last_updated = received or dt_util.utcnow()

    def _on_update(self) -> None:
        self._set_from_hub()

    @property
    def available(self) -> bool:
        return self._attr_image_url is not None
