"""HTTP-klient mot tur.skridsko.net."""
from __future__ import annotations

import aiohttp

from .const import LIST_URL, OBS_URL, USER_AGENT
from .parser import NotLoggedIn, Observation, is_logged_out, parse_list, parse_observation


class SkridskoClient:
    """Henter sider med brukerens sesjonsnøkkel. Bilder hentes uten innlogging."""

    def __init__(self, session: aiohttp.ClientSession, phpsessid: str) -> None:
        self._session = session
        self.phpsessid = phpsessid

    def _headers(self, with_cookie: bool = True) -> dict[str, str]:
        h = {"User-Agent": USER_AGENT, "Accept-Language": "nb-NO,nb;q=0.9"}
        if with_cookie:
            h["Cookie"] = f"PHPSESSID={self.phpsessid}"
        return h

    async def _get_text(self, url: str) -> str:
        async with self._session.get(url, headers=self._headers(),
                                     timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            text = await resp.text(errors="replace")
            # Utlogget: Skridsko sender til /admin/errors/authreq.htm («Tillatelse mangler»)
            if "authreq" in str(resp.url) or "Tillatelse mangler" in text:
                raise NotLoggedIn
            return text

    async def list_ids(self) -> list[str]:
        """Observasjoner i interesseområdet, nyeste først. Kaster NotLoggedIn hvis utlogget."""
        return parse_list(await self._get_text(LIST_URL))

    async def observation(self, obs_id: str) -> Observation:
        return parse_observation(await self._get_text(OBS_URL.format(id=obs_id)), obs_id)

    async def check_login(self, probe_id: str | None = None) -> tuple[bool, str | None]:
        """Én forespørsel hvis probe_id er kjent, ellers to. Returnerer (innlogget, siste id)."""
        if not probe_id:
            try:
                ids = await self.list_ids()
            except NotLoggedIn:
                return False, None
            if not ids:
                return True, None  # tom liste: kan ikke avgjøre, anta OK
            probe_id = ids[0]
        try:
            page = await self._get_text(OBS_URL.format(id=probe_id))
        except NotLoggedIn:
            return False, probe_id
        return not is_logged_out(page), probe_id

    async def image(self, url: str) -> bytes:
        async with self._session.get(url, headers=self._headers(with_cookie=False),
                                     timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.read()


__all__ = ["SkridskoClient", "NotLoggedIn"]
