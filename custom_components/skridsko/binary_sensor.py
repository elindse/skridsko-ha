from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SkridskoEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([LoggedInSensor(hass.data[DOMAIN][entry.entry_id], "logged_in")])


class LoggedInSensor(SkridskoEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool | None:
        return self.hub.logged_in

    @property
    def icon(self) -> str:
        return "mdi:lock-check" if self.hub.logged_in else "mdi:lock-alert"

    @property
    def extra_state_attributes(self) -> dict:
        return {"pending": list(self.hub.data.get("pending", []))}
