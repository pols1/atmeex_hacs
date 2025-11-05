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
        """Общий помощник: всегда парсим JSON, даже если сервер отдаёт text/html."""
        assert self._session is not None
        async with async_timeout.timeout(30):
            async with self._session.request(method, url, **kwargs) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise ApiError(f"{method} {url} failed {resp.status}: {text[:300]}")
                # Бывает, сервер присылает JSON с неправильным content-type → разбираем вручную
                try:
                    return await resp.json(content_type=None)
                except Exception:
                    _LOGGER.debug("Non-JSON content-type, trying manual parse for %s", url)
                    import json as _json
                    return _json.loads(text)

    # ---------- READ ----------

    async def get_devices(self) -> list[dict[str, Any]]:
        """
        Сначала пытаемся с with_condition=1.
        Если 500 – падаем на простой /devices и подтягиваем condition через /devices/{id}.
        """
        url1 = f"{self.base_url}/devices?with_condition=1"
        try:
            data = await self._fetch_json("GET", url1)
            return data if isinstance(data, list) else []
        except ApiError as err:
            # 500 (и прочие серверные) – фолбэк
            msg = str(err)
            if "failed 500" in msg or "failed 502" in msg or "failed 503" in msg:
                _LOGGER.warning("with_condition endpoint failed, fallback to /devices: %s", msg)
                url2 = f"{self.base_url}/devices"
                devices = await self._fetch_json("GET", url2)
                if not isinstance(devices, list):
                    return []
                # добираем condition точечно
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
                        _LOGGER.warning("Failed to fetch condition for device %s: %s", did, e)
                        d.setdefault("condition", {})
                    enriched.append(d)
                return enriched
            # не серверная – пробрасываем дальше
            raise

    async def get_device(self, device_id: int | str) -> dict[str, Any]:
        url = f"{self.base_url}/devices/{device_id}"
        data = await self._fetch_json("GET", url)
        return data if isinstance(data, dict) else {}

    # ------------------- WRITE (params) -------------------

    async def set_params(self, device_id: int | str, params: dict) -> None:
        """PUT /devices/{id}/params с полями из SetDeviceParamsRequest."""
        assert self._session is not None
        url = f"{self.base_url}/devices/{device_id}/params"
        async with async_timeout.timeout(20):
            async with self._session.put(url, json=params) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise ApiError(f"PUT /devices/{device_id}/params failed {resp.status}: {text[:300]}")

    async def set_power(self, device_id: int | str, on: bool) -> None:
        await self.set_params(device_id, {"u_pwr_on": bool(on)})

    async def set_fan_speed(self, device_id: int | str, speed: int) -> None:
        await self.set_params(device_id, {"u_fan_speed": int(speed)})

    async def set_target_temperature(self, device_id: int | str, temperature_c: float) -> None:
        # API ждёт deci°C
        await self.set_params(device_id, {"u_temp_room": int(round(temperature_c * 10))})

    # --------- presets / humidification / brizer ---------

    async def set_preset_auto(self, device_id: int | str, enabled: bool) -> None:
        await self.set_params(device_id, {"u_auto": bool(enabled)})

    async def set_preset_night(self, device_id: int | str, enabled: bool) -> None:
        await self.set_params(device_id, {"u_night": bool(enabled)})

    async def set_preset_cool(self, device_id: int | str, enabled: bool) -> None:
        await self.set_params(device_id, {"u_cool_mode": bool(enabled)})

    async def set_humid_stage(self, device_id: int | str, stage: int) -> None:
        """0 = off, 1..3 = ступени увлажнения."""
        st = max(0, min(3, int(stage)))
        await self.set_params(device_id, {"u_hum_stg": st})

    async def set_brizer_mode(self, device_id: int | str, damp_pos: int) -> None:
        """
        0 = приточная вентиляция
        1 = рециркуляция
        2 = смешанный режим
        3 = приточный клапан
        """
        pos = max(0, min(3, int(damp_pos)))
        await self.set_params(device_id, {"u_damp_pos": pos})
