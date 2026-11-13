"""Thin async client for the Home Assistant REST API (long-lived access token)."""

from __future__ import annotations

from typing import Any

import httpx
from hubnex.i18n import tr


class HomeAssistantError(Exception):
    pass


class HomeAssistant:
    def __init__(self, url: str, token: str, blocked_services: set[str] | None = None):
        self.url = url.rstrip("/")
        self.blocked = blocked_services or set()
        self._client = httpx.AsyncClient(
            base_url=f"{self.url}/api",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=20,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kw) -> Any:
        try:
            r = await self._client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise HomeAssistantError(tr("Home Assistant non raggiungibile: {a}", a=exc)) from exc
        if r.status_code == 404:
            raise HomeAssistantError(f"Non trovato: {path}")
        if r.status_code >= 400:
            raise HomeAssistantError(f"HA {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    async def ping(self) -> bool:
        try:
            await self._request("GET", "/")
            return True
        except HomeAssistantError:
            return False

    async def get_state(self, entity_id: str) -> dict:
        s = await self._request("GET", f"/states/{entity_id}")
        return {
            "entity_id": s["entity_id"],
            "state": s["state"],
            "attributes": s.get("attributes", {}),
            "last_changed": s.get("last_changed"),
        }

    async def history(self, entity_ids: list[str], hours: int = 24) -> dict[str, list[tuple[str, str]]]:
        """State changes of the last `hours` per entity: [(time, state), ...]."""
        from datetime import datetime, timedelta, timezone

        start = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = await self._request("GET", f"/history/period/{start}", params={
            "filter_entity_id": ",".join(entity_ids), "minimal_response": "", "no_attributes": "",
        }) or []
        out: dict[str, list[tuple[str, str]]] = {}
        for series in rows:
            if not series:
                continue
            eid = series[0].get("entity_id")
            out[eid] = [(p.get("last_changed") or p.get("last_updated") or "", p.get("state")) for p in series]
        return out

    async def history_period(
        self, entity_ids: list[str], start: str, end: str, attributes: bool = False, timeout: float = 45
    ) -> list[list[dict]]:
        """Raw recorder history between two ISO times, one series per entity (read-only)."""
        params = {"filter_entity_id": ",".join(entity_ids), "end_time": end, "significant_changes_only": ""}
        if not attributes:
            params.update(minimal_response="", no_attributes="")
        return await self._request("GET", f"/history/period/{start}", params=params, timeout=timeout) or []

    async def logbook(self, start: str, end: str, entity_id: str | None = None, timeout: float = 45) -> list[dict]:
        """Logbook entries between two ISO times, optionally for one entity (read-only)."""
        params = {"end_time": end}
        if entity_id:
            params["entity"] = entity_id
        return await self._request("GET", f"/logbook/{start}", params=params, timeout=timeout) or []

    async def list_entities(self, domain: str | None = None, search: str | None = None) -> list[dict]:
        states = await self._request("GET", "/states")
        out = []
        for s in states:
            eid = s["entity_id"]
            name = s.get("attributes", {}).get("friendly_name", "")
            if domain and not eid.startswith(f"{domain}."):
                continue
            if search and search.lower() not in f"{eid} {name}".lower():
                continue
            out.append({"entity_id": eid, "name": name, "state": s["state"]})
        return out

    async def tts(
        self, engine: str, text: str, language: str | None = None, options: dict | None = None
    ) -> tuple[bytes, str]:
        """Speech from one of Home Assistant's TTS engines (e.g. tts.piper): audio and its type.
        `options` are the engine's own, e.g. {"voice": "RinaldoNeural"}."""
        body = {"engine_id": engine, "message": text, "cache": True}
        if language:
            body["language"] = language
        if options:
            body["options"] = options
        info = await self._request("POST", "/tts_get_url", json=body)
        path = (info or {}).get("path") or ""
        if not path:
            raise HomeAssistantError(tr("sintesi vocale {a}: nessun audio", a=engine))
        try:
            r = await self._client.get(path[4:] if path.startswith("/api/") else path, timeout=60)
        except httpx.HTTPError as exc:
            raise HomeAssistantError(tr("Home Assistant non raggiungibile: {a}", a=exc)) from exc
        if r.status_code >= 400:
            raise HomeAssistantError(tr("sintesi vocale {a}: HA {b}", a=engine, b=r.status_code))
        return r.content, r.headers.get("content-type", "audio/mpeg")

    async def conversation(self, text: str, agent_id: str = "conversation.home_assistant") -> dict:
        """Home Assistant's own conversation agent (the sentences Assist understands locally)."""
        return await self._request("POST", "/conversation/process", json={"text": text, "agent_id": agent_id}, timeout=10)

    async def camera_image(self, entity_id: str) -> tuple[bytes, str]:
        """A still frame of a camera (JPEG, usually) and its content type."""
        try:
            proxy = "image_proxy" if entity_id.startswith("image.") else "camera_proxy"
            r = await self._client.get(f"/{proxy}/{entity_id}", timeout=15)
        except httpx.HTTPError as exc:
            raise HomeAssistantError(tr("Home Assistant non raggiungibile: {a}", a=exc)) from exc
        if r.status_code >= 400:
            raise HomeAssistantError(f"telecamera {entity_id}: HA {r.status_code}")
        return r.content, r.headers.get("content-type", "image/jpeg")

    async def camera_stream(self, entity_id: str):
        """The camera as MJPEG (what HA serves at camera_proxy_stream): (content type, chunks)."""
        req = self._client.build_request("GET", f"/camera_proxy_stream/{entity_id}", timeout=httpx.Timeout(15, read=None))
        try:
            r = await self._client.send(req, stream=True)
        except httpx.HTTPError as exc:
            raise HomeAssistantError(tr("Home Assistant non raggiungibile: {a}", a=exc)) from exc
        if r.status_code >= 400:
            await r.aclose()
            raise HomeAssistantError(f"telecamera {entity_id}: HA {r.status_code}")

        async def chunks():
            try:
                async for chunk in r.aiter_raw():
                    yield chunk
            finally:
                await r.aclose()  # the dashboard closed the view: stop pulling from HA

        return r.headers.get("content-type", "multipart/x-mixed-replace"), chunks()

    async def forecast(self, entity_id: str) -> list[dict]:
        """The daily forecast of a weather entity (Home Assistant's weather.get_forecasts)."""
        res = await self._request(
            "POST", "/services/weather/get_forecasts?return_response",
            json={"entity_id": entity_id, "type": "daily"},
        )
        return (((res or {}).get("service_response") or {}).get(entity_id) or {}).get("forecast") or []

    async def call_service(self, domain: str, service: str, data: dict | None = None, by_owner: bool = False) -> list[dict]:
        """`by_owner`: pressed by the owner in the dashboard, so the services Jarvis may not
        call on his own (unlocking, disarming) are allowed too."""
        if f"{domain}.{service}" in self.blocked and not by_owner:
            raise HomeAssistantError(
                f"Il servizio {domain}.{service} è bloccato per sicurezza: chiedi all'utente di farlo a mano."
            )
        changed = await self._request("POST", f"/services/{domain}/{service}", json=data or {})
        return [{"entity_id": s["entity_id"], "state": s["state"]} for s in (changed or [])]
