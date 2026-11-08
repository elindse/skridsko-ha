"""Oppsett, innstillinger og ny innlogging – alt i brukergrensesnittet."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import NotLoggedIn, SkridskoClient
from .const import (
    CONF_EMAIL_ENABLED, CONF_EMAIL_SERVICE, CONF_EMAIL_TO, CONF_IMAP_ENTRY,
    CONF_KEEPALIVE_MAX, CONF_KEEPALIVE_MIN, CONF_MAX_IMAGES, CONF_PHPSESSID,
    CONF_PUSH_ENABLED, CONF_PUSH_ONLY_SKATEABLE, CONF_PUSH_SERVICES, DEFAULT_OPTIONS, DOMAIN,
    BUILTIN_SMTP, CONF_SMTP_PASSWORD, CONF_SMTP_USER, CONF_INCLUDE_MAP, CONF_USE_EMAIL, effective_options,
)


async def _validate(hass: HomeAssistant, phpsessid: str) -> tuple[str | None, int]:
    """Returnerer (feilkode, antall observasjoner)."""
    import aiohttp
    client = SkridskoClient(async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar()),
                            phpsessid.strip())
    try:
        ids = await client.list_ids()
        return None, len(ids)
    except NotLoggedIn:
        return "invalid_auth", 0
    except Exception:
        return "cannot_connect", 0


def _imap_options(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    return [selector.SelectOptionDict(value=e.entry_id, label=e.title)
            for e in hass.config_entries.async_entries("imap")]


def _notify_services(hass: HomeAssistant, mobile: bool) -> list[selector.SelectOptionDict]:
    svcs = sorted(hass.services.async_services().get("notify", {}))
    return [selector.SelectOptionDict(value=f"notify.{s}", label=s)
            for s in svcs if s.startswith("mobile_app_") == mobile and s not in ("notify", "send_message", "persistent_notification")]


def _delivery_schema(hass: HomeAssistant, cur: Mapping[str, Any]) -> vol.Schema:
    c = {**DEFAULT_OPTIONS, **cur}
    email_opts = [selector.SelectOptionDict(value=BUILTIN_SMTP, label="Innebygd Gmail-sending (fyll inn under)")] + _notify_services(hass, mobile=False)
    push_opts = _notify_services(hass, mobile=True)
    imap_opts = _imap_options(hass)
    fields: dict[Any, Any] = {
        vol.Required(CONF_USE_EMAIL, default=c[CONF_USE_EMAIL]): selector.BooleanSelector(),
        vol.Optional(CONF_IMAP_ENTRY, description={"suggested_value": c[CONF_IMAP_ENTRY] or None}): selector.SelectSelector(
            selector.SelectSelectorConfig(options=imap_opts, mode=selector.SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_EMAIL_ENABLED, default=c[CONF_EMAIL_ENABLED]): selector.BooleanSelector(),
        vol.Optional(CONF_EMAIL_TO, description={"suggested_value": c[CONF_EMAIL_TO]}): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)),
        vol.Optional(CONF_EMAIL_SERVICE, description={"suggested_value": c[CONF_EMAIL_SERVICE] or None}): selector.SelectSelector(
            selector.SelectSelectorConfig(options=email_opts, mode=selector.SelectSelectorMode.DROPDOWN, custom_value=True)),
        vol.Optional(CONF_SMTP_USER, description={"suggested_value": c[CONF_SMTP_USER]}): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)),
        vol.Optional(CONF_SMTP_PASSWORD, description={"suggested_value": c[CONF_SMTP_PASSWORD]}): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        vol.Required(CONF_PUSH_ENABLED, default=c[CONF_PUSH_ENABLED]): selector.BooleanSelector(),
        vol.Optional(CONF_PUSH_SERVICES, default=list(c[CONF_PUSH_SERVICES])): selector.SelectSelector(
            selector.SelectSelectorConfig(options=push_opts, multiple=True, mode=selector.SelectSelectorMode.DROPDOWN, custom_value=True)),
        vol.Required(CONF_PUSH_ONLY_SKATEABLE, default=c[CONF_PUSH_ONLY_SKATEABLE]): selector.BooleanSelector(),
        vol.Required(CONF_MAX_IMAGES, default=c[CONF_MAX_IMAGES]): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=10, step=1, mode=selector.NumberSelectorMode.SLIDER)),
        vol.Required(CONF_INCLUDE_MAP, default=c[CONF_INCLUDE_MAP]): selector.BooleanSelector(),
        vol.Required(CONF_KEEPALIVE_MIN, default=c[CONF_KEEPALIVE_MIN]): selector.NumberSelector(
            selector.NumberSelectorConfig(min=3, max=60, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.SLIDER)),
        vol.Required(CONF_KEEPALIVE_MAX, default=c[CONF_KEEPALIVE_MAX]): selector.NumberSelector(
            selector.NumberSelectorConfig(min=3, max=90, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.SLIDER)),
    }
    return vol.Schema(fields)


def _check_delivery(data: Mapping[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if data.get(CONF_USE_EMAIL) and not data.get(CONF_IMAP_ENTRY):
        errors[CONF_IMAP_ENTRY] = "imap_required"
    if data.get(CONF_EMAIL_ENABLED) and not data.get(CONF_EMAIL_SERVICE):
        errors[CONF_EMAIL_SERVICE] = "email_service_required"
    if data.get(CONF_EMAIL_ENABLED) and data.get(CONF_EMAIL_SERVICE) == BUILTIN_SMTP and not (
            data.get(CONF_SMTP_USER) and data.get(CONF_SMTP_PASSWORD) and data.get(CONF_EMAIL_TO)):
        errors["base"] = "smtp_incomplete"
    if data.get(CONF_PUSH_ENABLED) and not data.get(CONF_PUSH_SERVICES):
        errors[CONF_PUSH_SERVICES] = "push_device_required"
    if float(data.get(CONF_KEEPALIVE_MIN, 0)) > float(data.get(CONF_KEEPALIVE_MAX, 0)):
        errors[CONF_KEEPALIVE_MAX] = "max_below_min"
    return errors


def _clean(data: Mapping[str, Any]) -> dict[str, Any]:
    d = {**DEFAULT_OPTIONS, **data}
    d[CONF_MAX_IMAGES] = int(d[CONF_MAX_IMAGES])
    d[CONF_IMAP_ENTRY] = d.get(CONF_IMAP_ENTRY) or ""
    d[CONF_KEEPALIVE_MIN] = int(d[CONF_KEEPALIVE_MIN])
    d[CONF_KEEPALIVE_MAX] = int(d[CONF_KEEPALIVE_MAX])
    d[CONF_EMAIL_TO] = (d.get(CONF_EMAIL_TO) or "").strip()
    d[CONF_EMAIL_SERVICE] = d.get(CONF_EMAIL_SERVICE) or ""
    d[CONF_SMTP_USER] = (d.get(CONF_SMTP_USER) or "").strip()
    d[CONF_SMTP_PASSWORD] = (d.get(CONF_SMTP_PASSWORD) or "").replace(" ", "")
    return d


class SkridskoConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            err, count = await _validate(self.hass, user_input[CONF_PHPSESSID])
            if err:
                errors["base"] = err
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                self._data = {CONF_PHPSESSID: user_input[CONF_PHPSESSID].strip()}
                self.context["title_placeholders"] = {"count": str(count)}
                return await self.async_step_delivery()
        schema = vol.Schema({
            vol.Required(CONF_PHPSESSID): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_delivery(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_delivery(user_input)
            if not errors:
                return self.async_create_entry(title="Skridsko isobservasjoner", data=self._data,
                                               options=_clean(user_input))
        return self.async_show_form(step_id="delivery",
                                    data_schema=_delivery_schema(self.hass, user_input or {}), errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            err, _ = await _validate(self.hass, user_input[CONF_PHPSESSID])
            if err:
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_PHPSESSID: user_input[CONF_PHPSESSID].strip()})
        hub = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        pending = len(hub.data.get("pending", [])) if hub else 0
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PHPSESSID): selector.TextSelector()}),
            description_placeholders={"pending": str(pending)}, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SkridskoOptionsFlow()


class SkridskoOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_delivery(user_input)
            if not errors:
                return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(
            step_id="init",
            data_schema=_delivery_schema(self.hass, user_input or effective_options(self.config_entry)),
            errors=errors)
