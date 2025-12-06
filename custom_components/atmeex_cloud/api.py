import time
import logging
import asyncio
from typing import Any, Dict, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.iot.atmeex.com"


class ApiError(Exception):
    """Ошибки API Atmeex."""


class AtmeexApi:
    """Клиент облака Atmeex — авторизация + API устройств."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str):
        self._session = session
        self._email = email
        self._password = password

        self._access_token: Optional[str] = None
        self._token_type: str = "Bearer"
        self._token_expires_at: Optional[float] = None

        # защита от одновременного логина
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------------
    # Вспомогательное
    # ---------------------------------------------------------------------

    def _token_is_valid(self) -> bool:
        """Проверяем — токен жив или протух."""
        if not self._access_token:
            return False
        if not self._token_expires_at:
            return True
        # с запасом в 30 секунд
        return time.time() < self._token_expires_at - 30

    # ---------------------------------------------------------------------
    # AUTH
    # ---------------------------------------------------------------------

    async def _login_if_needed(self) -> None:
        """Логинимся, если токена нет или он протух."""
        if self._token_is_valid():
            return

        async with self._lock:
            # второй поток мог уже обновить токен пока мы ждали лок
            if self._token_is_valid():
                return

            url = f"{API_BASE}/auth/signin"

            # ВАЖНО: strict как в документации
            payload = {
                "grant_type": "basic",
                "email": self._email,
                "password": self._password,
            }

            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            _LOGGER.info("Atmeex API: requesting new token from %s", url)
            _LOGGER.debug("Atmeex auth payload: %s", payload)

            try:
                async with self._session.post(
                    url, json=payload, headers=headers
                ) as resp:
                    text = await resp.text()

                    if resp.status != 200:
                        raise ApiError(
                            f"auth/signin failed {resp.status}: {text[:300]}"
                        )

                    try:
                        data = await resp.json()
                    except Exception:
                        _LOGGER.error("Atmeex auth: invalid JSON: %s", text[:500])
                        raise ApiError("auth/signin: invalid JSON in response")

            except aiohttp.ClientError as err:
                raise ApiError(f"auth/signin request error: {err}") from err

            _LOGGER.debug("Atmeex auth/signin JSON response: %s", data)

            nested = data.get("data") or {}

            # ищем токен в разных вариантах
            access_token = (
                data.get("access_token")
                or data.get("token")
                or data.get("accessToken")
                or nested.get("access_token")
                or nested.get("token")
                or nested.get("accessToken")
            )

            if not access_token:
                _LOGGER.error(
                    "Atmeex auth error — no access token found in JSON: %s", data
                )
                raise ApiError("auth/signin: no access token in response")

            self._access_token = access_token
            self._token_type = data.get("token_type") or nested.get("token_type") or "Bearer"

            expires_in = data.get("expires_in") or nested.get("expires_in")
            if isinstance(expires_in, (int, float)):
                self._token_expires_at = time.time() + int(expires_in)
            else:
                # если сервер не прислал срок — считаем «бессрочный» и живём до 401
                self._token_expires_at = None

            _LOGGER.info(
                "Atmeex: authenticated successfully, expires_in=%s", expires_in
            )

    # ---------------------------------------------------------------------
    # ОБЩИЙ ВРАППЕР ДЛЯ ЗАПРОСОВ
    # ---------------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Общий метод: подтянули токен, сходили в API, разобрали JSON."""
        await self._login_if_needed()

        url = f"{API_BASE}{path}"

        headers = kwargs.pop("headers", {})
        headers.setdefault("Accept", "application/json")
        headers.setdefault("Content-Type", "application/json")
        headers["Authorization"] = f"{self._token_type} {self._access_token}"

        _LOGGER.debug("Atmeex API request %s %s, headers=%s, kwargs=%s", method, url, headers, kwargs)

        try:
            async with self._session.request(
                method, url, headers=headers, **kwargs
            ) as resp:
                text = await resp.text()

                if resp.status >= 400:
                    raise ApiError(f"{method} {path} failed {resp.status}: {text[:300]}")

                try:
                    data = await resp.json()
                except Exception:
                    _LOGGER.error("Invalid JSON from %s: %s", path, text[:500])
                    raise ApiError("invalid JSON in API response")

                _LOGGER.debug("Atmeex API response %s %s: %s", method, path, data)
                return data

        except aiohttp.ClientError as err:
            raise ApiError(f"Network error calling {path}: {err}") from err

    # ---------------------------------------------------------------------
    # PUBLIC API METHODS
    # ---------------------------------------------------------------------

    async def get_devices(self) -> Any:
        """Получаем список устройств."""
        return await self._request("GET", "/devices")

    async def set_power(self, device_id: int, state: bool) -> Any:
        payload = {"u_pwr_on": state}
        return await self._request(
            "POST", f"/devices/{device_id}/settings", json=payload
        )

    async def set_fan_speed(self, device_id: int, speed: int) -> Any:
        payload = {"u_fan_speed": speed}
        return await self._request(
            "POST", f"/devices/{device_id}/settings", json=payload
        )

    async def set_temp(self, device_id: int, temp: int) -> Any:
        # сервер ожидает целое, у тебя в примерах 100/150 → значит, шаг 0.5 либо просто *10
        payload = {"u_temp_room": int(temp)}
        return await self._request(
            "POST", f"/devices/{device_id}/settings", json=payload
        )

    async def set_humidifier_stage(self, device_id: int, stage: int) -> Any:
        payload = {"u_hum_stg": int(stage)}
        return await self._request(
            "POST", f"/devices/{device_id}/settings", json=payload
        )

    async def set_damper(self, device_id: int, pos: int) -> Any:
        payload = {"u_damp_pos": int(pos)}
        return await self._request(
            "POST", f"/devices/{device_id}/settings", json=payload
        )
