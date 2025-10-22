import aiohttp
import async_timeout
import logging

_LOGGER = logging.getLogger(__name__)

class ApiError(Exception):
    pass


class AtmeexApi:
    def __init__(self, base_url="https://api.iot.atmeex.com"):
        self.base_url = base_url.rstrip("/")
        self._session = None
        self._token = None

    async def async_init(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def async_close(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def login(self, email: str, password: str) -> None:
        """POST /auth/signin — авторизация"""
        url = f"{self.base_url}/auth/signin"
        payload = {"grant_type": "basic", "email": email, "password": password}
        async with async_timeout.timeout(20):
            async with self._session.post(url, json=payload) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    _LOGGER.error("Login failed %s: %s", resp.status, text[:200])
                    raise ApiError(f"Login failed: {resp.status}")
                data = await resp.json(content_type=None)
        token = data.get("access_token")
        if not token:
            raise ApiError("Auth response missing access_token")
        self._token = token
        self._session.headers.update({"Authorization": f"Bearer {token}"})
        _LOGGER.info("Login successful")

    async def get_devices(self):
        """GET /devices?with_condition=1"""
        url = f"{self.base_url}/devices?with_condition=1"
        async with async_timeout.timeout(20):
            async with self._session.get(url) as resp:
                txt = await resp.text()
                if resp.status >= 400:
                    raise ApiError(f"GET /devices failed {resp.status}: {txt[:200]}")
                return await resp.json(content_type=None)

    async def get_device(self, device_id):
        url = f"{self.base_url}/devices/{device_id}"
        async with async_timeout.timeout(20):
            async with self._session.get(url) as resp:
                if resp.status >= 400:
                    raise ApiError(f"Device {device_id} not found")
                return await resp.json(content_type=None)

    async def get_device_state(self, device_id):
        """возвращает condition"""
        dev = await self.get_device(device_id)
        return dev.get("condition", {})

    async def set_params(self, device_id, params: dict):
        url = f"{self.base_url}/devices/{device_id}/params"
        async with async_timeout.timeout(20):
            async with self._session.put(url, json=params) as resp:
                txt = await resp.text()
                if resp.status >= 400:
                    raise ApiError(f"PUT /devices/{device_id}/params failed {resp.status}: {txt[:200]}")

    async def set_power(self, device_id, on: bool):
        await self.set_params(device_id, {"u_pwr_on": bool(on)})

    async def set_fan_speed(self, device_id, speed: int):
        await self.set_params(device_id, {"u_fan_speed": int(speed)})

    async def set_target_temperature(self, device_id, temperature_c: float):
        """принимает градусы, конвертирует в deci°C"""
        await self.set_params(device_id, {"u_temp_room": int(round(temperature_c * 10))})
