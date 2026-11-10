from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN
from .entity import SkridskoEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    add([LastObservation(hub, "last_observation"), StatusSensor(hub, "status"),
         NextCheck(hub, "next_check"), SentToday(hub, "sent_today")])


class LastObservation(SkridskoEntity, SensorEntity):
    _attr_icon = "mdi:snowflake"

    @property
    def native_value(self) -> str | None:
        return self.hub.last["name"] if self.hub.last else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self.hub.last or {}
        keys = ("id", "title", "region", "kommune", "place", "label", "short_status", "method", "level", "color", "skateable",
                "isinfo", "comment", "reporter", "time", "url", "images", "local_images", "map_image", "map_links",
                "received", "channels")
        attrs = {k: last.get(k) for k in keys}
        if last.get("lat") is not None:  # gjør at observasjonen vises på kartkort i HA
            attrs["latitude"], attrs["longitude"] = last["lat"], last["lon"]
        attrs["history"] = [
            {k: h.get(k) for k in ("id", "name", "place", "short_status", "color", "time", "received", "url")}
            for h in self.hub.data.get("history", [])[1:]
        ]
        return attrs


class StatusSensor(SkridskoEntity, SensorEntity):
    _attr_icon = "mdi:skate"

    @property
    def native_value(self) -> str | None:
        return self.hub.last["short_status"] if self.hub.last else None


class NextCheck(SkridskoEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-sand"

    @property
    def native_value(self) -> datetime | None:
        return self.hub.next_check


class SentToday(SkridskoEntity, SensorEntity):
    _attr_icon = "mdi:email-fast"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        return self.hub.sent_today

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # nullstill ved midnatt
        self.async_on_remove(async_track_time_change(self.hass, self._midnight, hour=0, minute=0, second=5))

    @callback
    def _midnight(self, _now: datetime) -> None:
        self.async_write_ha_state()
