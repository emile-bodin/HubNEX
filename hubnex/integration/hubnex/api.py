"""Talking to the HubNEX add-on."""

from __future__ import annotations

import asyncio

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import REQUEST_TIMEOUT


class HubNEXError(Exception):
    """HubNEX unreachable or refused the request."""


class InvalidAuth(HubNEXError):
    """Wrong token."""


class HubNEXClient:
    def __init__(self, hass: HomeAssistant, url: str, token: str) -> None:
        self._session = async_get_clientsession(hass)
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _post(self, path: str, payload: dict | None = None, timeout: int = 15, lang: str | None = None) -> dict:
        try:
            async with self._session.request(
                "POST" if payload is not None else "GET",
                f"{self._url}{path}",
                json=payload,
                headers={**self._headers, **({"X-HubNEX-Lang": lang} if lang else {})},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 401:
                    raise InvalidAuth
                if resp.status >= 400:
                    raise HubNEXError(f"HTTP {resp.status}: {(await resp.text())[:200]}")
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HubNEXError(str(err) or type(err).__name__) from err

    async def ping(self) -> dict:
        return await self._post("/api/ping")

    async def ask(self, text: str, language: str | None = None) -> str:
        """Jarvis' answer in English."""
        data = await self._post(
            "/api/chat",
            {"text": text, "channel": "assist", "voice": True},
            timeout=REQUEST_TIMEOUT,
            lang=language,
        )
        return data.get("reply", "")
