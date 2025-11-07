# было:
# import aiohttp
# class AtmeexApi:
#     async def async_init(self):
#         self._session = aiohttp.ClientSession()

from typing import Any, Dict, Optional
from aiohttp import ClientSession

API_BASE = "https://api.iot.atmeex.com"

class ApiError(Exception):
    pass

class AtmeexApi:
    def __init__(self, session: ClientSession):
        self._session = session
        self._token: Optional[str] = None

    async def async_init(self) -> None:
        """Ничего не создаём — сессию даёт HA."""
        return

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def login(self, email: str, password: str) -> None:
        payload = {"grant_type": "basic", "email": email, "password": password}
        async with self._session.post(f"{API_BASE}/auth/signin", json=payload) as resp:
            if resp.status != 200:
                txt = await resp.text()
                raise ApiError(f"Auth failed {resp.status}: {txt[:300]}")
            data = await resp.json()
            self._token = data.get("access_token")

    async def get_devices(self, fallback: bool = False):
        # основной список
        url = f"{API_BASE}/devices"
        async with self._session.get(url, headers=self._headers()) as resp:
            if resp.status == 200:
                return await resp.json()
            if not fallback:
                txt = await resp.text()
                raise ApiError(f"GET /devices failed {resp.status}: {txt[:300]}")
            return []

    async def get_device(self, device_id: int | str):
        async with self._session.get(f"{API_BASE}/devices/{device_id}", headers=self._headers()) as resp:
            if resp.status != 200:
                txt = await resp.text()
                raise ApiError(f"GET /devices/{device_id} {resp.status}: {txt[:300]}")
            return await resp.json()

    async def set_power(self, device_id: int | str, on: bool):
        body = {"u_pwr_on": bool(on)}
        async with self._session.put(f"{API_BASE}/devices/{device_id}/params",
                                     json=body, headers=self._headers()) as resp:
            if resp.status != 200:
                raise ApiError(f"set_power {resp.status}")

    async def set_target_temperature(self, device_id: int | str, temp_c: float):
        body = {"u_temp_room": int(round(temp_c * 10))}
        async with self._session.put(f"{API_BASE}/devices/{device_id}/params",
                                     json=body, headers=self._headers()) as resp:
            if resp.status != 200:
                raise ApiError(f"set_target_temperature {resp.status}")

    async def set_fan_speed(self, device_id: int | str, speed: int):
        body = {"u_fan_speed": int(speed)}
        async with self._session.put(f"{API_BASE}/devices/{device_id}/params",
                                     json=body, headers=self._headers()) as resp:
            if resp.status != 200:
                raise ApiError(f"set_fan_speed {resp.status}")

    async def set_brizer_mode(self, device_id: int | str, damp_pos: int):
        body = {"u_damp_pos": int(damp_pos)}
        async with self._session.put(f"{API_BASE}/devices/{device_id}/params",
                                     json=body, headers=self._headers()) as resp:
            if resp.status != 200:
                raise ApiError(f"set_brizer_mode {resp.status}")

    async def set_humid_stage(self, device_id: int | str, stage: int):
        body = {"u_hum_stg": int(stage)}
        async with self._session.put(f"{API_BASE}/devices/{device_id}/params",
                                     json=body, headers=self._headers()) as resp:
            if resp.status != 200:
                raise ApiError(f"set_humid_stage {resp.status}")
