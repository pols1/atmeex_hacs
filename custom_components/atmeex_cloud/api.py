from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from aiohttp import ClientSession, ClientError

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://api.iot.atmeex.com"


class ApiError(Exception):
    """Generic API error for Atmeex integration."""


class AtmeexApi:
    """Low-level HTTP client for Atmeex Cloud API."""

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        token: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password

        self._access_token: Optional[str] = token
        self._refresh_token: Optional[str] = refresh_token

    # -------------------------------------------------------------------------
    # AUTH
    # -------------------------------------------------------------------------

    async def _login_basic(self) -> None:
        """Авторизация по email+password (grant_type=basic)."""
        url = f"{API_BASE_URL}/auth/signin"
        payload = {
            "grant_type": "basic",
            "email": self._email,
            "password": self._password,
        }

        _LOGGER.info("Atmeex: requesting new token via %s", url)

        async with self._session.post(url, json=payload) as resp:
            text = await resp.text()
            _LOGGER.debug(
                "Atmeex auth response: status=%s, body=%s",
                resp.status,
                text[:500],
            )
            if resp.status != 200:
                raise ApiError(f"auth/signin failed {resp.status}: {text[:500]}")

            # Если ответ JSON — распарсим
            try:
                data = await resp.json()
            except Exception:
                raise ApiError(
                    f"auth/signin: non-json response {resp.status}: {text[:500]}"
                )

        token = data.get("access_token")
        ref = data.get("refresh_token")

        if not token:
            raise ApiError("auth/signin: no access token in response")

        self._access_token = token
        self._refresh_token = ref

        _LOGGER.info(
            "Atmeex: authenticated, token_type=Bearer, expires_in=None "
            "(JWT exp is handled by server)"
        )

    async def _login_refresh(self) -> None:
        """Обновление токена по refresh_token (grant_type=refresh_token)."""
        if not self._refresh_token:
            raise ApiError("Cannot refresh token: refresh_token is not set")

        url = f"{API_BASE_URL}/auth/signin"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        _LOGGER.info("Atmeex: refreshing token via %s", url)

        async with self._session.post(url, json=payload) as resp:
            text = await resp.text()
            _LOGGER.debug(
                "Atmeex refresh response: status=%s, body=%s",
                resp.status,
                text[:500],
            )

            if resp.status != 200:
                raise ApiError(f"auth/refresh failed {resp.status}: {text[:500]}")

            try:
                data = await resp.json()
            except Exception:
                raise ApiError(
                    f"auth/refresh: non-json response {resp.status}: {text[:500]}"
                )

        token = data.get("access_token")
        ref = data.get("refresh_token")

        if not token:
            raise ApiError("auth/refresh: no access token in response")

        self._access_token = token
        self._refresh_token = ref

        _LOGGER.info("Atmeex: token refreshed successfully")

    async def _refresh_token_or_login(self) -> None:
        """Попытаться обновить токен, при неудаче — залогиниться заново."""
        try:
            await self._login_refresh()
        except Exception as err:
            _LOGGER.warning(
                "Atmeex: refresh_token failed (%s), falling back to basic login", err
            )
            await self._login_basic()

    async def _ensure_token(self) -> None:
        """Убедиться, что есть токен (логин при необходимости)."""
        if self._access_token:
            return
        await self._login_basic()

    # -------------------------------------------------------------------------
    # LOW-LEVEL REQUEST
    # -------------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        json: Any | None = None,
        params: Optional[Dict[str, Any]] = None,
        _retry: bool = True,
    ) -> Any:
        """Общий метод HTTP-запроса к Atmeex API (кроме /auth/signin)."""

        await self._ensure_token()

        url = f"{API_BASE_URL}{path}"
        headers: Dict[str, str] = {}

        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            _LOGGER.debug(
                "Atmeex API request: %s %s params=%s json=%s",
                method,
                url,
                params,
                json,
            )
            async with self._session.request(
                method,
                url,
                json=json,
                params=params,
                headers=headers,
            ) as resp:
                text = await resp.text()
                _LOGGER.debug(
                    "Atmeex API response: %s %s -> %s, body=%s",
                    method,
                    path,
                    resp.status,
                    text[:500],
                )

                # Если токен устарел — пробуем обновить и повторить один раз
                if resp.status in (401, 403) and _retry:
                    _LOGGER.info(
                        "Atmeex: got %s on %s %s, re-authenticating",
                        resp.status,
                        method,
                        path,
                    )
                    await self._refresh_token_or_login()
                    return await self._request(
                        method, path, json=json, params=params, _retry=False
                    )

                if resp.status >= 400:
                    raise ApiError(
                        f"{method} {path} failed {resp.status}: {text[:500]}"
                    )

                # Пытаемся вернуть JSON, если возможно
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type.lower():
                    try:
                        return await resp.json()
                    except Exception:
                        # если json сломан, вернём сырой текст
                        return text

                return text

        except ClientError as err:
            raise ApiError(f"HTTP error calling {method} {path}: {err}") from err

    # -------------------------------------------------------------------------
    # DEVICES
    # -------------------------------------------------------------------------

    async def get_devices(self) -> Dict[str, Any]:
        """
        Получить список устройств + (по возможности) condition.

        API: GET /devices?with_condition=1
        Возвращает:
          {
            "devices": [ {...}, ... ],
            "states": { "<id>": {condition}, ... }
          }
        """
        data = await self._request(
            "GET",
            "/devices",
            params={"with_condition": 1},
        )

        if not isinstance(data, list):
            raise ApiError(f"GET /devices expected list, got {type(data)}")

        states: Dict[str, Any] = {}
        for dev in data:
            if not isinstance(dev, dict):
                continue
            did = dev.get("id")
            cond = dev.get("condition")
            if did is not None and isinstance(cond, dict):
                states[str(did)] = cond

        return {
            "devices": data,
            "states": states,
        }

    async def async_get_devices(self) -> Dict[str, Any]:
        """Алиас под стиль Home Assistant (если где-то вызывается async_get_devices)."""
        return await self.get_devices()

    # -------------------------------------------------------------------------
    # SETTINGS / COMMANDS
    # -------------------------------------------------------------------------

    async def _update_settings(self, device_id: int | str, **params: Any) -> Any:
        """
        Обновить параметры устройства (мощность, скорость, заслонка, температура и т.п.).

        Согласно swagger, для изменения настроек используется:
          PUT /devices/{id}/params
        с телом SetDeviceParamsRequest:
          - u_pwr_on: bool
          - u_fan_speed: int
          - u_damp_pos: int
          - u_hum_stg: int
          - u_temp_room: int (в деци-градусах, 250 = 25.0 °C)
          - и прочие поля u_*
        """
        did = int(device_id)

        payload: Dict[str, Any] = {"device_id": did}
        payload.update(params)

        path = f"/devices/{did}/params"

        data = await self._request("PUT", path, json=payload)
        _LOGGER.debug("Atmeex: updated params for %s -> %s", did, payload)
        return data

    async def set_power(self, device_id: int | str, on: bool) -> None:
        """Вкл/выкл устройства (u_pwr_on)."""
        await self._update_settings(device_id, u_pwr_on=bool(on))

    async def set_fan_speed(self, device_id: int | str, speed: int) -> None:
        """Установить скорость вентилятора 1..7 (u_fan_speed)."""
        await self._update_settings(device_id, u_fan_speed=int(speed))

    async def set_target_temperature(self, device_id: int | str, value: float) -> None:
        """Установить целевую температуру (°C -> деци-°C в u_temp_room)."""
        temp_deci = int(round(float(value) * 10))
        await self._update_settings(device_id, u_temp_room=temp_deci)

    async def set_brizer_mode(self, device_id: int | str, idx: int) -> None:
        """Режим бризера (заслонка) — u_damp_pos: 0..3."""
        await self._update_settings(device_id, u_damp_pos=int(idx))

    async def set_humid_stage(self, device_id: int | str, stage: int) -> None:
        """
        Ступень увлажнения — u_hum_stg: 0..3.

        В climate мы мапим 0/33/66/100 → 0..3.
        """
        await self._update_settings(device_id, u_hum_stg=int(stage))