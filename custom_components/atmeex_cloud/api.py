from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)


class ApiError(Exception):
    pass


class AtmeexApi:
    def __init__(self, base_url: str = "https://api.iot.atmeex.com") -> None:
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._token: Optional[str] = None

    async def async_init(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession(headers={"Accept": "application/json"})

    async def async_close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def login(self, email: str, password: str) -> None:
        assert self._session is not None
        url = f"{self.base_url}/auth/signin"
        payload = {"grant_type": "basic", "email": email, "password": password}
        async with async_timeout.timeout(20):
            async with self._session.post(url, json=payload) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    _LOGGER.error("Signin failed %s: %s", resp.status, text[:300])
                    raise ApiError(f"Signin failed: {resp.status}")
                data = await resp.json(content_type=None)
        token = data.get("access_token")
        if not token:
            raise ApiError("Auth response missing access_token")
        self._token = token
        self._session.headers.update({"Authorization": f"Bearer {token}"})
        _LOGGER.info("Signed in")

    # ---------- helpers ----------

    async def _fetch_json(self, method: str, url: str, **kwargs) -> Any:
        """Всегда пробуем разобрать JSON, даже если content-type кривой."""
        assert self._session is not None
        async with async_timeout.timeout(30):
            async with self._session.request(method, url, **kwargs) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise ApiError(f"{method} {url} failed {resp.status}: {text[:300]}")
                try:
                    return await resp.json(content_type=None)
                except Exception:
                    import json as _json
                    return _json.loads(text)

    # ---------- READ ----------

    async def get_devices(self) -> list[dict[str, Any]]:
        """
        Сначала /devices?with_condition=1.
        На 5xx — фоллбэк: /devices + точечные /devices/{id}.
        """
        url1 = f"{self.base_url}/devices?with_condition=1"
        try:
            data = await self._fetch_json("GET", url1)
            return data if isinstance(data, list) else []
        except ApiError as err:
            msg = str(err)
            if any(code in msg for code in ("failed 500", "failed 502", "failed 503")):
                _LOGGER.warning("with_condition failed, fallback to /devices: %s", msg)
                url2 = f"{self.base_url}/devices"
                devices = await self._fetch_json("GET", url2)
                if not isinstance(devices, list):
                    return []
                enriched: list[dict[str, Any]] = []
                for d in devices:
                    did = d.get("id")
                    if did is None:
                        enriched.append(d)
                        continue
                    try:
                        full = await self.get_device(did)
                        d["condition"] = full.get("condition") or {}
                    except Exception as e:
                        _LOGGER.warning("Failed fetch condition for %s: %s", did, e)
                        d.setdefault("condition", {})
                    enriched.append(d)
                return enriched
            raise

    async def get_device(self, device_id: int | str) -> dict[str, Any]:
        url = f"{self.base_url}/devices/{device_id}"
        data = await self._fetch_json("GET", url)
        return data if isinstance(data, dict) else {}

    # ---------- WRITE (используются климатом) ----------

    async def set_params(self, device_id: int | str, params: dict) -> None:
        url = f"{self.base_url}/devices/{device_id}/params"
        await self._fetch_json("PUT", url, json=params)

    async def set_power(self, device_id: int | str, on: bool) -> None:
        await self.set_params(device_id, {"u_pwr_on": bool(on)})

    async def set_fan_speed(self, device_id: int | str, speed: int) -> None:
        speed = max(1, min(7, int(speed)))
        await self.set_params(device_id, {"u_fan_speed": speed})

    async def set_target_temperature(self, device_id: int | str, temperature_c: float) -> None:
        # API ждёт deci°C
        deci = int(round(float(temperature_c) * 10))
        await self.set_params(device_id, {"u_temp_room": deci})

    async def set_humid_stage(self, device_id: int | str, stage: int) -> None:
        stage = max(0, min(3, int(stage)))
        await self.set_params(device_id, {"u_hum_stg": stage})

    async def set_brizer_mode(self, device_id: int | str, damp_pos: int) -> None:
        pos = max(0, min(3, int(damp_pos)))
        await self.set_params(device_id, {"u_damp_pos": pos})
