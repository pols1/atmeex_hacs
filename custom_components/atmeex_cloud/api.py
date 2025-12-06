from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientSession, ClientResponseError

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://api.iot.atmeex.com"


@dataclass
class ApiError(Exception):
    message: str
    status: int | None = None

    def __str__(self) -> str:
        return f"{self.message} (status={self.status})"


class AtmeexApi:
    """Simple client for Atmeex Cloud API."""

    def __init__(self, session: ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._access_token: str | None = None
        self._token_type: str = "Bearer"

    @property
    def _auth_header(self) -> dict[str, str]:
        if not self._access_token:
            return {}
        return {"Authorization": f"{self._token_type} {self._access_token}"}

    async def sign_in(self) -> None:
        """Authenticate and store access token."""
        url = f"{API_BASE_URL}/auth/signin"
        payload = {
            "grant_type": "basic",
            "email": self._email,
            "password": self._password,
        }

        _LOGGER.debug("Atmeex: sign_in POST %s", url)

        try:
            async with self._session.post(url, json=payload) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise ApiError(
                        f"auth/signin failed: {resp.status}: {text[:300]}",
                        status=resp.status,
                    )
                data = await resp.json()
        except ClientResponseError as err:
            raise ApiError(f"auth/signin HTTP error: {err}", status=err.status) from err
        except Exception as err:  # noqa: BLE001
            raise ApiError(f"auth/signin unexpected error: {err}") from err

        token = data.get("access_token")
        token_type = data.get("token_type", "Bearer")

        if not token:
            raise ApiError("auth/signin: no access token in response")

        self._access_token = token
        self._token_type = token_type
        _LOGGER.debug("Atmeex: sign_in OK, token_type=%s", token_type)

    async def _ensure_token(self) -> None:
        if not self._access_token:
            await self.sign_in()

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return list of devices for current user."""
        await self._ensure_token()

        url = f"{API_BASE_URL}/user/devices"
        headers = {
            "Accept": "application/json",
            **self._auth_header,
        }

        _LOGGER.debug("Atmeex: GET %s", url)

        try:
            async with self._session.get(url, headers=headers) as resp:
                text = await resp.text()
                if resp.status == 401:
                    # токен протух — пробуем перелогиниться один раз
                    _LOGGER.warning("Atmeex: token expired, re-auth")
                    self._access_token = None
                    await self._ensure_token()
                    return await self.get_devices()

                if resp.status != 200:
                    raise ApiError(
                        f"GET /user/devices failed {resp.status}: {text[:300]}",
                        status=resp.status,
                    )

                data = await resp.json()
        except ClientResponseError as err:
            raise ApiError(f"GET /user/devices HTTP error: {err}", status=err.status) from err
        except Exception as err:  # noqa: BLE001
            raise ApiError(f"GET /user/devices unexpected error: {err}") from err

        if not isinstance(data, list):
            _LOGGER.warning("Atmeex: unexpected devices payload: %s", type(data))
            return []

        return data

    async def set_fan_speed(self, device_id: int, speed: int) -> None:
        """Set fan speed (0..7)."""
        await self._ensure_token()
        url = f"{API_BASE_URL}/device/{device_id}/settings"
        payload = {
            "u_fan_speed": speed,
        }

        _LOGGER.debug("Atmeex: set_fan_speed %s -> %s", device_id, speed)

        async with self._session.post(url, json=payload, headers=self._auth_header) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise ApiError(f"set_fan_speed {resp.status}: {text[:300]}", status=resp.status)

    async def set_power(self, device_id: int, on: bool) -> None:
        """Turn device on/off (u_pwr_on)."""
        await self._ensure_token()
        url = f"{API_BASE_URL}/device/{device_id}/settings"
        payload = {
            "u_pwr_on": on,
        }

        _LOGGER.debug("Atmeex: set_power %s -> %s", device_id, on)

        async with self._session.post(url, json=payload, headers=self._auth_header) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise ApiError(f"set_power {resp.status}: {text[:300]}", status=resp.status)

    async def set_target_temperature(self, device_id: int, temp_c: float) -> None:
        """Set target room temperature (u_temp_room, *10)."""
        await self._ensure_token()
        url = f"{API_BASE_URL}/device/{device_id}/settings"
        payload = {
            "u_temp_room": int(round(temp_c * 10)),
        }

        _LOGGER.debug("Atmeex: set_target_temperature %s -> %s", device_id, temp_c)

        async with self._session.post(url, json=payload, headers=self._auth_header) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise ApiError(f"set_target_temperature {resp.status}: {text[:300]}", status=resp.status)

    async def set_humidity_stage(self, device_id: int, stage: int) -> None:
        """Set humidifier stage 0..3 (u_hum_stg)."""
        await self._ensure_token()
        url = f"{API_BASE_URL}/device/{device_id}/settings"
        payload = {
            "u_hum_stg": stage,
        }

        _LOGGER.debug("Atmeex: set_humidity_stage %s -> %s", device_id, stage)

        async with self._session.post(url, json=payload, headers=self._auth_header) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise ApiError(f"set_humidity_stage {resp.status}: {text[:300]}", status=resp.status)
