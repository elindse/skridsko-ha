from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SkridskoEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([NotificationsSwitch(hass.data[DOMAIN][entry.entry_id], "notifications")])


class NotificationsSwitch(SkridskoEntity, SwitchEntity):
    _attr_icon = "mdi:bell-ring"

    @property
    def is_on(self) -> bool:
        return self.hub.notifications_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hub.async_set_notifications(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hub.async_set_notifications(False)
