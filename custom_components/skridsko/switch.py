from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SkridskoEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    # fjern den gamle felles bryteren «Varsler aktivert» fra før 0.5.0
    reg = er.async_get(hass)
    if old := reg.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_notifications"):
        reg.async_remove(old)
    hub = hass.data[DOMAIN][entry.entry_id]
    add([ChannelSwitch(hub, "email", "mdi:email-fast"), ChannelSwitch(hub, "push", "mdi:cellphone-message")])


class ChannelSwitch(SkridskoEntity, SwitchEntity):
    """Slår e-post eller push av/på uten å endre oppsettet."""

    def __init__(self, hub, channel: str, icon: str) -> None:
        super().__init__(hub, f"{channel}_notifications")
        self._channel = channel
        self._attr_icon = icon

    @property
    def available(self) -> bool:
        # bare tilgjengelig når kanalen er satt opp under Konfigurer
        return self.hub.email_configured if self._channel == "email" else self.hub.push_configured

    @property
    def is_on(self) -> bool:
        return self.hub.channel_on(self._channel)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hub.async_set_channel(self._channel, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hub.async_set_channel(self._channel, False)
