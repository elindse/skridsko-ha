"""Sentral logikk: lytter på e-post, henter observasjoner, varsler og holder innloggingen i live."""
from __future__ import annotations

import asyncio
import html
import logging
import os
import random
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import SkridskoClient
from .const import (
    CONF_EMAIL_ENABLED, CONF_EMAIL_SERVICE, CONF_EMAIL_TO, CONF_IMAP_ENTRY,
    CONF_KEEPALIVE_MAX, CONF_KEEPALIVE_MIN, CONF_MAX_IMAGES, CONF_PHPSESSID,
    CONF_PUSH_ENABLED, CONF_PUSH_ONLY_SKATEABLE, CONF_PUSH_SERVICES, DEFAULT_OPTIONS,
    BUILTIN_SMTP, CONF_SMTP_PASSWORD, CONF_SMTP_USER, CONF_INCLUDE_MAP,
    DOMAIN, EVENT_OBSERVATION, HISTORY_LEN, IMAGE_DIR, JITTER_MAX_SECONDS, OBS_URL,
    SIGNAL_UPDATE, STORAGE_VERSION, CONF_USE_EMAIL, effective_options,
)
from .geo import KARTVERKET_TILE, OSM_TILE, compose_map, tiles_needed
from .parser import NotLoggedIn, Observation, ids_from_email

_LOGGER = logging.getLogger(__name__)
EVENT_LOGIN_CHECK = f"{DOMAIN}_login_check"


class SkridskoHub:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.client = SkridskoClient(
            async_create_clientsession(hass, cookie_jar=_dummy_jar()),
            entry.data[CONF_PHPSESSID],
        )
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.data: dict[str, Any] = {}
        self.logged_in: bool | None = None
        self.next_check: datetime | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._keepalive_unsub: CALLBACK_TYPE | None = None
        self._lock = asyncio.Lock()
        self._image_dir = hass.config.path("www", IMAGE_DIR)

    # ---------- livssyklus ----------
    @property
    def opts(self) -> dict[str, Any]:
        return effective_options(self.entry)

    @property
    def signal(self) -> str:
        return SIGNAL_UPDATE.format(self.entry.entry_id)

    async def async_start(self) -> None:
        self.data = await self._store.async_load() or {}
        self.data.setdefault("seen", [])
        self.data.setdefault("history", [])
        self.data.setdefault("pending", [])
        self.data.setdefault("sent_log", [])
        self.data.setdefault("notifications_enabled", True)
        self.data.setdefault("login_warned", False)
        self._unsubs.append(self.hass.bus.async_listen("imap_content", self._on_imap))
        # første sjekk kort tid etter oppstart, deretter tilfeldig
        self._schedule_keepalive(first=True)
        if self.data["pending"]:
            self.hass.async_create_task(self._process_pending())

    async def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        if self._keepalive_unsub:
            self._keepalive_unsub()
            self._keepalive_unsub = None

    async def _save(self) -> None:
        await self._store.async_save(self.data)

    def _update(self) -> None:
        async_dispatcher_send(self.hass, self.signal)

    # ---------- egenskaper for entiteter ----------
    @property
    def last(self) -> dict[str, Any] | None:
        return self.data["history"][0] if self.data.get("history") else None

    @property
    def notifications_enabled(self) -> bool:
        return self.data.get("notifications_enabled", True)

    async def async_set_notifications(self, enabled: bool) -> None:
        self.data["notifications_enabled"] = enabled
        await self._save()
        self._update()

    @property
    def sent_today(self) -> int:
        today = dt_util.now().date()
        return sum(1 for ts in self.data.get("sent_log", [])
                   if (d := dt_util.parse_datetime(ts)) and dt_util.as_local(d).date() == today)

    # ---------- innloggingssjekk ----------
    def _schedule_keepalive(self, first: bool = False) -> None:
        if self._keepalive_unsub:
            self._keepalive_unsub()
        o = self.opts
        lo, hi = sorted((float(o[CONF_KEEPALIVE_MIN]), float(o[CONF_KEEPALIVE_MAX])))
        delay = random.uniform(20, 90) if first else random.uniform(lo, hi) * 60 + random.uniform(0, JITTER_MAX_SECONDS)
        self.next_check = dt_util.utcnow() + timedelta(seconds=delay)
        self._keepalive_unsub = async_call_later(self.hass, delay, self._keepalive_cb)
        _LOGGER.debug("Skridsko: neste sjekk om %.0f s", delay)
        self._update()

    @callback
    def _keepalive_cb(self, _now: datetime) -> None:
        self._keepalive_unsub = None
        self.hass.async_create_task(self.async_poll())

    async def async_check_login(self) -> bool:
        """Brukes av knappen «Se etter nye observasjoner nå»."""
        return await self.async_poll()

    async def async_poll(self) -> bool:
        """Én sidevisning: henter lista (holder innloggingen i live) og behandler nye observasjoner."""
        try:
            ids = await self.client.list_ids()
        except NotLoggedIn:
            if self.logged_in is not False:
                self.hass.bus.async_fire(EVENT_LOGIN_CHECK, {"ok": False, "entry_id": self.entry.entry_id})
            await self._set_logged_in(False)
            self._schedule_keepalive()
            return False
        except Exception as err:  # nettverksfeil: ikke anta utlogget
            _LOGGER.warning("Skridsko: henting av lista feilet: %s", err)
            self._schedule_keepalive()
            return bool(self.logged_in)
        if self.logged_in is False:
            self.hass.bus.async_fire(EVENT_LOGIN_CHECK, {"ok": True, "entry_id": self.entry.entry_id})
        await self._set_logged_in(True)
        seen = set(self.data["seen"])
        if not self.data.get("list_initialized"):
            # Første gang: det som ligger der nå regnes som sett – ingen flom av gamle varsler
            self.data["seen"] = (self.data["seen"] + [i for i in ids if i not in seen])[-2000:]
            self.data["list_initialized"] = True
            await self._save()
            _LOGGER.info("Skridsko: lista lest første gang – %d observasjoner markert som sett", len(ids))
        else:
            new = [i for i in ids if i not in seen]
            if new:
                _LOGGER.info("Skridsko: %d nye observasjoner i lista: %s", len(new), ", ".join(new))
            for obs_id in reversed(new):  # eldste først
                await self.async_process(obs_id)
        self._schedule_keepalive()
        return True

    async def _set_logged_in(self, ok: bool) -> None:
        was = self.logged_in
        self.logged_in = ok
        if ok:
            self.data["login_warned"] = False
            if was is False and self.data.get("pending"):
                self.hass.async_create_task(self._process_pending())
        elif not self.data.get("login_warned"):
            self.data["login_warned"] = True
            self.entry.async_start_reauth(self.hass)
            await self._notify_text(
                "⚠️ Skridsko: innloggingen har gått ut",
                "Logg inn på tur.skridsko.net på nytt og lim inn ny nøkkel under "
                "Innstillinger → Reparasjoner i Home Assistant.",
            )
        if was != ok:
            await self._save()
        self._update()

    # ---------- e-post inn ----------
    @callback
    def _on_imap(self, event: Event) -> None:
        if not self.opts[CONF_USE_EMAIL]:
            return
        d = event.data
        imap_id = self.opts[CONF_IMAP_ENTRY]
        sender = str(d.get("sender") or "").lower()
        text = str(d.get("text") or "")
        _LOGGER.info("Skridsko: imap_content mottatt – konto=%s fra=%s emne=%r tekst=%d tegn",
                     d.get("entry_id") or d.get("username"), sender, d.get("subject"), len(text))
        # Riktig IMAP-konto? Eldre/andre versjoner har ikke entry_id i hendelsen – sammenlign da brukernavn.
        if d.get("entry_id"):
            if d["entry_id"] != imap_id:
                _LOGGER.info("Skridsko: ignorert – annen IMAP-konto")
                return
        else:
            imap = self.hass.config_entries.async_get_entry(imap_id)
            if imap and d.get("username") and d["username"] != imap.data.get("username"):
                _LOGGER.info("Skridsko: ignorert – annen IMAP-konto (%s)", d.get("username"))
                return
        # Direkte fra Skridsko, eller videresendt for hånd (originalavsenderen står i teksten)
        if "skridsko.net" not in sender and "webadmin@skridsko.net" not in text.lower():
            _LOGGER.info("Skridsko: ignorert – verken fra skridsko.net eller videresendt Skridsko-varsel")
            return
        ids = ids_from_email(text)
        if not ids:
            _LOGGER.warning(
                "Skridsko: fant ikke observasjonsnummer i e-posten (%d tegn tekst). Sjekk at IMAP-integrasjonen "
                "tar med «text» i hendelsen (IMAP → Konfigurer → Meldingsdata).", len(text))
            return
        _LOGGER.info("Skridsko: behandler observasjon %s", ", ".join(ids))
        for obs_id in ids:
            self.hass.async_create_task(self.async_process(obs_id, uid=d.get("uid")))

    async def _mark_imap_seen(self, uid: str | None) -> None:
        if not uid or not self.hass.services.has_service("imap", "seen"):
            return
        try:
            await self.hass.services.async_call(
                "imap", "seen", {"entry": self.opts[CONF_IMAP_ENTRY], "uid": uid}, blocking=True)
        except Exception as err:
            _LOGGER.debug("Kunne ikke markere e-post som lest: %s", err)

    # ---------- behandling ----------
    async def async_process(self, obs_id: str, uid: str | None = None, force: bool = False) -> None:
        async with self._lock:
            if not force and obs_id in self.data["seen"]:
                await self._mark_imap_seen(uid)
                return
            try:
                obs = await self.client.observation(obs_id)
            except NotLoggedIn:
                _LOGGER.warning("Skridsko: ikke innlogget – observasjon %s lagt i kø", obs_id)
                if obs_id not in self.data["pending"]:
                    self.data["pending"].append(obs_id)
                await self._set_logged_in(False)
                await self._save()
                return
            except Exception as err:
                _LOGGER.error("Skridsko: kunne ikke hente observasjon %s: %s", obs_id, err)
                return
            await self._set_logged_in(True)
            files = await self._download_images(obs)
            map_file = await self._make_map(obs)
            channels = await self._deliver(obs, files, map_file)
            _LOGGER.info("Skridsko: %s %s – %d bilder – sendt via: %s", obs.id, obs.name, len(files),
                         ", ".join(channels) or "ingenting (varsler av eller ingen kanal valgt)")
            entry = obs.as_dict() | {
                "received": dt_util.utcnow().isoformat(),
                "local_images": [f"/local/{IMAGE_DIR}/{os.path.basename(f)}" for f in files],
                "map_image": f"/local/{IMAGE_DIR}/{os.path.basename(map_file)}" if map_file else None,
                "channels": channels,
            }
            self.data["history"] = [entry] + [h for h in self.data["history"] if h["id"] != obs_id]
            self.data["history"] = self.data["history"][:HISTORY_LEN]
            if obs_id not in self.data["seen"]:
                self.data["seen"] = (self.data["seen"] + [obs_id])[-2000:]
            self.data["pending"] = [p for p in self.data["pending"] if p != obs_id]
            self.data["last_id"] = obs_id
            if channels:
                self.data["sent_log"] = (self.data["sent_log"] + [dt_util.utcnow().isoformat()])[-100:]
            await self._save()
            await self._mark_imap_seen(uid)
            self.hass.bus.async_fire(EVENT_OBSERVATION, {
                "entry_id": self.entry.entry_id, "id": obs.id, "name": obs.name,
                "status": obs.short_status, "level": obs.level, "skateable": obs.skateable,
                "images": len(obs.images), "channels": channels, "url": obs.url,
            })
            self._update()

    async def _process_pending(self) -> None:
        for obs_id in list(self.data.get("pending", [])):
            await self.async_process(obs_id)

    async def async_resend_last(self) -> None:
        if self.last:
            await self.async_process(self.last["id"], force=True)

    # ---------- bilder ----------
    async def _download_images(self, obs: Observation) -> list[str]:
        paths: list[str] = []
        for n, url in enumerate(obs.images[: int(self.opts[CONF_MAX_IMAGES])]):
            try:
                data = await self.client.image(url)
            except Exception as err:
                _LOGGER.warning("Skridsko: bilde feilet %s: %s", url, err)
                continue
            path = os.path.join(self._image_dir, f"{obs.id}_{n}.jpg")
            await self.hass.async_add_executor_job(_write_file, path, data)
            paths.append(path)
        await self.hass.async_add_executor_job(_cleanup, self._image_dir, 80)
        return paths

    # ---------- varsling ----------
    async def _make_map(self, obs: Observation) -> str | None:
        """Kartbilde (Kartverket topo, OSM som reserve) med markør. Hoppes over uten Pillow/koordinater."""
        if obs.lat is None or not self.opts[CONF_INCLUDE_MAP]:
            return None
        try:
            import PIL  # noqa: F401
        except ImportError:
            _LOGGER.info("Skridsko: Pillow mangler – sender uten kartbilde")
            return None
        w, h, z = 600, 320, 13
        tiles, origin = tiles_needed(obs.lat, obs.lon, z, w, h)
        for template, attribution in ((KARTVERKET_TILE, "© Kartverket"), (OSM_TILE, "© OpenStreetMap")):
            got: dict[tuple[int, int], bytes] = {}
            for tx, ty in tiles:
                try:
                    got[(tx, ty)] = await self.client.image(template.format(z=z, x=tx, y=ty))
                except Exception as err:
                    _LOGGER.debug("Skridsko: kartflis feilet (%s): %s", template, err)
                    break
            if len(got) == len(tiles):
                data = await self.hass.async_add_executor_job(compose_map, got, origin, w, h, attribution)
                path = os.path.join(self._image_dir, f"{obs.id}_map.jpg")
                await self.hass.async_add_executor_job(_write_file, path, data)
                return path
        _LOGGER.warning("Skridsko: klarte ikke å lage kartbilde for %s", obs.id)
        return None

    async def _deliver(self, obs: Observation, files: list[str], map_file: str | None = None) -> list[str]:
        if not self.notifications_enabled:
            return []
        o, sent = self.opts, []
        if o[CONF_EMAIL_ENABLED] and o[CONF_EMAIL_SERVICE]:
            try:
                await self._send_email(obs, files, map_file)
                sent.append("e-post")
            except Exception as err:
                _LOGGER.error("Skridsko: e-post feilet: %s", err)
        if o[CONF_PUSH_ENABLED] and o[CONF_PUSH_SERVICES] and (obs.skateable or not o[CONF_PUSH_ONLY_SKATEABLE]):
            for svc in o[CONF_PUSH_SERVICES]:
                try:
                    await self._send_push(svc, obs)
                    if "push" not in sent:
                        sent.append("push")
                except Exception as err:
                    _LOGGER.error("Skridsko: push til %s feilet: %s", svc, err)
        return sent

    async def _send_email(self, obs: Observation, files: list[str], map_file: str | None = None) -> None:
        o = self.opts
        svc = o[CONF_EMAIL_SERVICE].removeprefix("notify.")
        esc = lambda s: html.escape(s).replace("\n", "<br>")  # noqa: E731
        imgs = "".join(
            f'<p><a href="{html.escape(u)}"><img src="cid:{os.path.basename(f)}" '
            f'style="max-width:100%;border-radius:6px"></a></p>'
            for f, u in zip(files, obs.images)
        ) or '<p style="color:#888">(ingen bilder)</p>'
        links = obs.links
        map_html = ""
        if links:
            pic = (f'<a href="{links["norgeskart"]}"><img src="cid:{os.path.basename(map_file)}" '
                   f'style="max-width:100%;border-radius:6px;border:1px solid #ddd"></a>') if map_file else ""
            map_html = (f'<p style="margin:12px 0 4px">{pic}</p><p style="margin:0 0 12px;font-size:14px">'
                        f'<a href="{links["norgeskart"]}">Åpne i Norgeskart</a> · '
                        f'<a href="{links["google"]}">Google Maps</a></p>')
        body = f"""<div style="font-family:Arial,sans-serif;max-width:640px">
<h2 style="margin:0 0 6px">{esc(obs.name)} <span style="font-weight:normal;color:#666">[{esc(obs.region)}]</span></h2>
<p style="margin:0 0 12px"><span style="background:{obs.color};color:#fff;padding:2px 8px;border-radius:4px">{esc(obs.short_status)}</span> &nbsp;{esc(obs.method)}</p>
{f"<p style='margin:0 0 6px'><b>Isinfo:</b> {esc(obs.isinfo)}</p>" if obs.isinfo else ""}
{f"<p style='margin:0 0 12px'><b>Kommentar:</b> {esc(obs.comment)}</p>" if obs.comment else ""}
{imgs}
{map_html}
<p style="color:#666;font-size:13px">{esc(obs.reporter)} · {esc(obs.time)} · nr. {obs.id}</p>
<p><a href="{obs.url}">Åpne observasjonen på Skridskonätet</a></p></div>"""
        text = "\n".join(x for x in [
            obs.title, obs.status, f"Isinfo: {obs.isinfo}" if obs.isinfo else "",
            f"Kommentar: {obs.comment}" if obs.comment else "", f"{obs.reporter} – {obs.time}", obs.url] if x)
        subject = f"❄️ {obs.title}: {obs.short_status}"
        if o[CONF_EMAIL_SERVICE] == BUILTIN_SMTP:
            await self.hass.async_add_executor_job(
                _smtp_send, o[CONF_SMTP_USER], o[CONF_SMTP_PASSWORD], o[CONF_EMAIL_TO], subject, text, body,
                files + ([map_file] if map_file else []))
            return
        data: dict[str, Any] = {
            "title": subject,
            "message": text,
            "data": {"html": body, "images": files + ([map_file] if map_file else [])},
        }
        if o[CONF_EMAIL_TO]:
            data["target"] = [o[CONF_EMAIL_TO]]
        await self.hass.services.async_call("notify", svc, data, blocking=True)

    async def _send_push(self, service: str, obs: Observation) -> None:
        svc = service.removeprefix("notify.")
        msg = ". ".join(x for x in [obs.isinfo, obs.comment] if x) or obs.method
        data: dict[str, Any] = {"url": obs.url, "clickAction": obs.url,
                                "actions": [{"action": "URI", "title": "Åpne observasjon", "uri": obs.url}]
                                + ([{"action": "URI", "title": "Kart", "uri": obs.links["google"]}] if obs.links else []),
                                "group": DOMAIN, "tag": f"{DOMAIN}_{obs.id}"}
        if obs.images:
            data["image"] = obs.images[0]
        await self.hass.services.async_call(
            "notify", svc, {"title": f"{obs.name}: {obs.short_status}", "message": msg[:300], "data": data},
            blocking=True)

    async def _notify_text(self, title: str, message: str) -> None:
        o = self.opts
        calls = []
        if o[CONF_EMAIL_ENABLED] and o[CONF_EMAIL_SERVICE] == BUILTIN_SMTP:
            try:
                await self.hass.async_add_executor_job(
                    _smtp_send, o[CONF_SMTP_USER], o[CONF_SMTP_PASSWORD], o[CONF_EMAIL_TO], title, message, None, [])
            except Exception as err:
                _LOGGER.warning("Skridsko: e-postvarsel feilet: %s", err)
        elif o[CONF_EMAIL_ENABLED] and o[CONF_EMAIL_SERVICE]:
            d: dict[str, Any] = {"title": title, "message": message}
            if o[CONF_EMAIL_TO]:
                d["target"] = [o[CONF_EMAIL_TO]]
            calls.append((o[CONF_EMAIL_SERVICE], d))
        if o[CONF_PUSH_ENABLED]:
            calls += [(s, {"title": title, "message": message}) for s in o[CONF_PUSH_SERVICES]]
        for svc, d in calls:
            try:
                await self.hass.services.async_call("notify", svc.removeprefix("notify."), d, blocking=True)
            except Exception as err:
                _LOGGER.warning("Skridsko: varsel via %s feilet: %s", svc, err)


def _smtp_send(user: str, password: str, to: str, subject: str, text: str,
               html_body: str | None, files: list[str]) -> None:
    """Send via Gmail SMTP med bildene innebygd (cid = filnavn)."""
    import smtplib
    import ssl
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
        part = msg.get_payload()[1]
        for path in files:
            with open(path, "rb") as f:
                part.add_related(f.read(), "image", "jpeg", cid=f"<{os.path.basename(path)}>",
                                 filename=os.path.basename(path))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)


def _dummy_jar():
    import aiohttp
    return aiohttp.DummyCookieJar()


def _write_file(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _cleanup(folder: str, keep: int) -> None:
    try:
        files = sorted((os.path.join(folder, f) for f in os.listdir(folder)), key=os.path.getmtime, reverse=True)
    except FileNotFoundError:
        return
    for f in files[keep:]:
        try:
            os.remove(f)
        except OSError:
            pass


__all__ = ["SkridskoHub", "EVENT_LOGIN_CHECK", "OBS_URL"]
