"""Felles grunnklasse for Skridsko-entiteter."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import BASE_URL, DOMAIN
from .hub import SkridskoHub


class SkridskoEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: SkridskoHub, key: str) -> None:
        self.hub = hub
        self._attr_translation_key = key
        self._attr_unique_id = f"{hub.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.entry.entry_id)},
            name="Skridsko isobservasjoner",
            manufacturer="Skridskonätet",
            model="tur.skridsko.net",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=BASE_URL + "/skridskonet/isobservationer/",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, self.hub.signal, self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self._on_update()
        self.async_write_ha_state()

    def _on_update(self) -> None:
        """Overstyres ved behov."""
