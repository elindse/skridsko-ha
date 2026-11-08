from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SkridskoEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    add([CheckLogin(hub, "check_login"), ResendLast(hub, "resend_last")])


class CheckLogin(SkridskoEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    async def async_press(self) -> None:
        await self.hub.async_check_login()


class ResendLast(SkridskoEntity, ButtonEntity):
    _attr_icon = "mdi:send"

    async def async_press(self) -> None:
        await self.hub.async_resend_last()
