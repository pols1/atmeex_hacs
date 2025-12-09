from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.iot.atmeex.com"


class ApiError(Exception):
    """Raised when Atmeex API call fails."""


@dataclass
class AtmeexDevice:
    """Thin wrapper around device JSON for type hints."""

    id: int
    name: str
    model: str
    online: bool
    raw: Dict[str, Any]

    @property
    def settings(self) -> Dict[str, Any]:
        return self.raw.get("settings") or {}

    def to_ha_dict(self) -> Dict[str, Any]:
        """Return dict shape which coordinator will хранить в data."""
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "online": self.online,
            "settings": self.settings,
            "condition": self.raw.get("condition"),
        }


class AtmeexApi:
    """Работа с облаком Atmeex."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password

        self._access_token: Optional[str] = None
        self._token_type: str = "Bearer"
        self._token_expires_at: Optional[float] = None  # unix-time
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _token_is_valid(self) -> bool:
        """Проверка, что токен ещё живой."""
        if not self._access_token:
            return False
        if self._token_expires_at is None:
            # сервер не сказал срок жизни — считаем, что жив, пока не получим ошибку
            return True
        # Обновляем токен заранее, за минуту до истечения
        return time.time() < self._token_expires_at - 60

    @property
    def _auth_header(self) -> Dict[str, str]:
        if not self._access_token:
            return {}
        return {"Authorization": f"{self._token_type} {self._access_token}"}

    async def _login_if_needed(self) -> None:
        """Логинимся, если ещё нет токена или он протух."""
        if self._token_is_valid():
            return

        async with self._lock:
            if self._token_is_valid():
                return

            url = f"{API_BASE}/auth/signin"
            payload = {
                "email": self._email,
                "password": self._password,
                # ВАЖНО: для текущего API нужен grant_type="basic"
                "grant_type": "basic",
            }

            _LOGGER.info("Atmeex: requesting new token via %s", url)

            try:
                async with self._session.post(url, json=payload) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        raise ApiError(
                            f"auth/signin failed {resp.status}: {text[:300]}"
                        )

                    data = await resp.json()
            except aiohttp.ClientError as err:
                raise ApiError(f"auth/signin request error: {err}") from err

            self._access_token = data.get("access_token") or data.get("token")
            self._token_type = data.get("token_type") or "Bearer"

            # пробуем прочитать срок жизни токена
            expires_in = data.get("expires_in")
            if isinstance(expires_in, (int, float)):
                self._token_expires_at = time.time() + int(expires_in)
            else:
                self._token_expires_at = None

            if not self._access_token:
                raise ApiError("auth/signin: no access token in response")

            _LOGGER.info(
                "Atmeex: authenticated, token_type=%s, expires_in=%s",
                self._token_type,
                expires_in,
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        retry_on_auth_error: bool = True,
    ) -> Any:
        """
        Базовый запрос к API с авторизацией и обработкой ошибок.

        Логика:
        * перед запросом гарантируем валидный токен;
        * при 401 / 403 / 500 один раз сбрасываем токен и пытаемся перелогиниться;
        * если повторный запрос снова падает — выбрасываем ApiError.
        """
        await self._login_if_needed()

        url = f"{API_BASE}{path}"
        headers = {
            "Accept": "application/json",
            **self._auth_header,
        }

        _LOGGER.debug("Atmeex: %s %s json=%s", method, url, json)

        try:
            async with self._session.request(
                method, url, headers=headers, json=json
            ) as resp:
                text = await resp.text()

                # Многие их ошибки авторизации приходят как 500 вместо 401.
                if (
                    resp.status in (401, 403, 500)
                    and retry_on_auth_error
                ):
                    _LOGGER.warning(
                        "Atmeex: %s %s got %s, trying to refresh token",
                        method,
                        path,
                        resp.status,
                    )
                    # сбрасываем токен и пробуем ещё раз
                    self._access_token = None
                    self._token_expires_at = None
                    await self._login_if_needed()
                    return await self._request(
                        method,
                        path,
                        json=json,
                        retry_on_auth_error=False,
                    )

                if resp.status >= 400:
                    raise ApiError(
                        f"{method} {path} failed {resp.status}: {text[:500]}"
                    )

                if "application/json" in resp.headers.get("Content-Type", ""):
                    return await resp.json()

                return text
        except aiohttp.ClientError as err:
            raise ApiError(f"{method} {path} request error: {err}") from err

    # ------------------------------------------------------------------
    # Публичные методы API
    # ------------------------------------------------------------------

    async def get_devices(self) -> List[Dict[str, Any]]:
        """
        Возвращает список устройств текущего пользователя.
        """
        data = await self._request("GET", "/devices")

        if not isinstance(data, list):
            raise ApiError("GET /devices: unexpected response format")

        devices: List[Dict[str, Any]] = []
        for raw in data:
            dev = AtmeexDevice(
                id=int(raw["id"]),
                name=str(raw.get("name") or f"Device {raw['id']}"),
                model=str(raw.get("model") or "unknown"),
                online=bool(raw.get("online")),
                raw=raw,
            )
            devices.append(dev.to_ha_dict())

        return devices

    async def _update_settings(
        self,
        device_id: int,
        **fields: Any,
    ) -> Dict[str, Any]:
        """
        Обновление настроек устройства.
        """
        payload = {"device_id": device_id, **fields}
        path = f"/devices/{device_id}/settings"

        data = await self._request("POST", path, json=payload)
        return data

    # --- high-level операции, которые дергает climate.py ----------------

    async def set_power(self, device_id: int, on: bool) -> None:
        await self._update_settings(device_id, u_pwr_on=bool(on))

    async def set_fan_speed(self, device_id: int, speed: int) -> None:
        # 0..7, за пределами — подрежем
        spd = max(0, min(7, int(speed)))
        await self._update_settings(device_id, u_fan_speed=spd)

    async def set_target_temperature(
        self, device_id: int, temperature_c: float
    ) -> None:
        # API использует десятые доли градуса: 215 => 21.5 °C
        value = int(round(float(temperature_c) * 10))
        await self._update_settings(device_id, u_temp_room=value)

    async def set_humidifier_stage(self, device_id: int, stage: int) -> None:
        # 0..3 — четыре ступени увлажнения
        stg = max(0, min(3, int(stage)))
        await self._update_settings(device_id, u_hum_stg=stg)

    async def set_brizer_mode(self, device_id: int, mode_index: int) -> None:
        """
        Режим приточного блока:
        0 — приточная вентиляция
        1 — рециркуляция
        2 — смешанный
        3 — приточный клапан
        """
        idx = max(0, min(3, int(mode_index)))
        await self._update_settings(device_id, u_damp_pos=idx)
