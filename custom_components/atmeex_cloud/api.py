from __future__ import annotations
from typing import Any, Optional
import aiohttp
import async_timeout

class ApiError(Exception):
    pass

class AtmeexApi:
    def __init__(self, base_url: str = "https://api.iot.atmeex.com"):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._token: Optional[str] = None

    async def async_init(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def async_close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def login(self, email: str, password: str) -> None:
        assert self._session is not None
        # Попробуем несколько типовых путей авторизации:
        for path in ("/auth/jwt/create", "/api-token-auth/", "/auth/login"):
            try:
                async with async_timeout.timeout(20):
                    async with self._session.post(
                        f"{self.base_url}{path}",
                        json={"username": email, "password": password},
                    ) as resp:
                        if resp.status >= 400:
                            continue
                        data = await resp.json(content_type=None)
                token = data.get("access") or data.get("access_token") or data.get("token")
                if token:
                    self._token = token
                    # Некоторые бекенды ждут "Token", другие — "Bearer"
                    self._session.headers.update({"Authorization": f"Bearer {token}"})
                    return
            except Exception:
                continue
        raise ApiError("Auth failed")

    async def get_devices(self) -> list[dict[str, Any]]:
        assert self._session is not None
        for path in ("/devices", "/api/devices", "/v1/devices"):
            async with async_timeout.timeout(20):
                async with self._session.get(f"{self.base_url}{path}") as resp:
                    if resp.status == 404:
                        continue
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
            if isinstance(data, dict) and "items" in data:
                return list(data["items"])
            if isinstance(data, dict) and "results" in data:
                return list(data["results"])
            if isinstance(data, list):
                return data
        return []

    async def get_device_state(self, device_id: str) -> dict[str, Any]:
        assert self._session is not None
        for tpl in ("/devices/{id}/state", "/api/devices/{id}/state"):
            path = tpl.format(id=device_id)
            async with async_timeout.timeout(20):
                async with self._session.get(f"{self.base_url}{path}") as resp:
                    if resp.status == 404:
                        continue
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
        return {}

    async def set_power(self, device_id: str, on: bool) -> None:
        assert self._session is not None
        for tpl in ("/devices/{id}/commands/power", "/api/devices/{id}/commands/power"):
            path = tpl.format(id=device_id)
            async with async_timeout.timeout(20):
                async with self._session.post(
                    f"{self.base_url}{path}", json={"on": bool(on)}
                ) as resp:
                    if resp.status == 404:
                        continue
                    resp.raise_for_status()
                    return
        raise ApiError("Power command endpoint not found")
