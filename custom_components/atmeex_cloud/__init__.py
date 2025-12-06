"""Low-level client for Atmeex Cloud API."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.iot.atmeex.com"


class ApiError(Exception):
    """Raised when Atmeex API returns error or unexpected response."""


class AtmeexApi:
    """Async client for Atmeex Cloud REST API."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password

        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None  # epoch seconds, если появится expires_in

        # Чтобы избежать гонок при обновлении токена
        self._auth_lock = asyncio.Lock()

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНОЕ
    # -------------------------------------------------------------------------

    async def _ensure_token(self) -> None:
        """Гарантирует, что у нас есть валидный access_token."""

        # Простой вариант: если токен есть – верим ему.
        # При 401 на запросах он будет сброшен и получим новый.
        if self._access_token:
            return

        async with self._auth_lock:
            # Пока ждали lock, кто-то мог уже залогиниться
            if self._access_token:
                return
            await self._authenticate()

    async def _authenticate(self) -> None:
        """Выполнить auth/signin и сохранить access_token."""

        url = f"{API_BASE}/auth/signin?format=json"

        payload = {
            # В Thunder у тебя логин работал – там, как правило, используется "password".
            # Если вдруг у тебя в ответе другой grant_type – можно поменять здесь.
            "grant_type": "password",
            "email": self._email,
            "password": self._password,
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        _LOGGER.debug("Atmeex auth: POST %s payload=%s", url, {**payload, "password": "***"})

        try:
            async with self._session.post(url, json=payload, headers=headers) as resp:
                text = await resp.text()
                _LOGGER.debug(
                    "Atmeex auth response: status=%s, body=%s",
                    resp.status,
                    text[:500],
                )

                if resp.status != 200:
                    raise ApiError(f"auth/signin failed {resp.status}: {text[:300]}")

                # Пытаемся разобрать JSON
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    raise ApiError(f"auth/signin: invalid JSON in response: {text[:200]}")

        except aiohttp.ClientError as err:
            raise ApiError(f"Error talking to Atmeex auth/signin: {err}") from err

        # ---- Поиск токена в разных местах ----
        access_token = (
            data.get("access_token")
            or data.get("token")
            or (data.get("data") or {}).get("access_token")
        )

        if not access_token:
            # Логируем полностью, чтобы ты в логах сразу увидел реальную структуру
            _LOGGER.error(
                "Atmeex auth/signin: no access token in response JSON: %s",
                data,
            )
            raise ApiError(f"auth/signin: no access token in response")

        self._access_token = access_token

        # Если есть expires_in – сохраним его (на будущее, если решим предобновлять)
        expires_in = (
            data.get("expires_in")
            or (data.get("data") or {}).get("expires_in")
        )
        if isinstance(expires_in, (int, float)):
            self._token_expires_at = asyncio.get_event_loop().time() + float(expires_in)
        else:
            self._token_expires_at = None

        _LOGGER.info("Atmeex auth: got access token; expires_in=%s", expires_in)

    def _auth_headers(self) -> Dict[str, str]:
        if not self._access_token:
            return {}
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Выполнить запрос к API с автоматической авторизацией и ретраем при 401.

        Возвращает либо разобранный JSON, либо None если тела нет.
        """

        await self._ensure_token()

        url = f"{API_BASE}{path}"
        headers: Dict[str, str] = {
            "Accept": "application/json",
            **self._auth_headers(),
        }

        if json_data is not None:
            headers.setdefault("Content-Type", "application/json")

        _LOGGER.debug(
            "Atmeex API request: %s %s json=%s",
            method,
            url,
            json_data,
        )

        async def do_call() -> aiohttp.ClientResponse:
            try:
                return await self._session.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                )
            except aiohttp.ClientError as err:
                raise ApiError(f"{method} {path} client error: {err}") from err

        # Первый вызов
        resp = await do_call()
        text = await resp.text()

        # Если токен протух – один раз попробуем перелогиниться и повторить запрос
        if resp.status == 401:
            _LOGGER.warning("Atmeex API got 401 on %s %s – will re-auth and retry", method, path)
            self._access_token = None
            await self._ensure_token()
            headers.update(self._auth_headers())

            resp = await do_call()
            text = await resp.text()

        _LOGGER.debug(
            "Atmeex API response: %s %s -> %s, body=%s",
            method,
            path,
            resp.status,
            text[:500],
        )

        if resp.status >= 400:
            raise ApiError(f"{method} {path} failed {resp.status}: {text[:300]}")

        if not text:
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.error(
                "Atmeex API %s %s: invalid JSON, raw body=%s",
                method,
                path,
                text[:500],
            )
            raise ApiError(f"{method} {path} returned invalid JSON")

    # -------------------------------------------------------------------------
    # ПУБЛИЧНЫЕ МЕТОДЫ, КОТОРЫЕ ИСПОЛЬЗУЕТ ИНТЕГРАЦИЯ
    # -------------------------------------------------------------------------

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Вернуть список устройств (как в Thunder)."""
        data = await self._request("GET", "/devices?format=json")
        # API возвращает список устройств — просто отдаём дальше.
        if isinstance(data, list):
            return data
        # На всякий случай – если обёрнуто в {"data":[...]}
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        _LOGGER.error("Unexpected /devices payload: %s", data)
        raise ApiError("Unexpected /devices response format")

    async def set_power(self, device_id: int, on: bool) -> None:
        """Включить / выключить бризер."""
        payload = {
            "device_id": device_id,
            "u_pwr_on": bool(on),
        }
        await self._request("POST", "/set", json_data=payload)

    async def set_fan_speed(self, device_id: int, speed: int) -> None:
        """Установить скорость вентилятора (0..7)."""
        payload = {
            "device_id": device_id,
            "u_fan_speed": int(speed),
        }
        await self._request("POST", "/set", json_data=payload)

    async def set_brizer_mode(self, device_id: int, mode: int) -> None:
        """
        Установить режим работы бризера (положение клапана).

        mode – индекс, который мы маппим в интеграции на:
        0 – приточная вентиляция
        1 – рециркуляция
        2 – смешанный режим
        3 – приточный клапан
        """
        payload = {
            "device_id": device_id,
            "u_damp_pos": int(mode),
        }
        await self._request("POST", "/set", json_data=payload)

    async def set_hum_stage(self, device_id: int, stage: int) -> None:
        """
        Установить ступень увлажнителя.

        stage: 0..3 (0 – выкл, 1..3 – ступени).
        """
        payload = {
            "device_id": device_id,
            "u_hum_stg": int(stage),
        }
        await self._request("POST", "/set", json_data=payload)

    async def set_target_temperature(self, device_id: int, temp_c: float) -> None:
        """
        Установить целевую температуру (в °C).

        В API значение передаётся как сотые доли градуса (100 = 1.00°C),
        поэтому умножаем на 10 или 100 в зависимости от того,
        как ты видел в ответах (/devices settings.u_temp_room).
        """
        # У тебя в примерах в settings было 100, 150 и т.п.
        # Значит это, скорее всего, "десятые доли" (100 = 10.0°C)
        value = int(round(temp_c * 10))

        payload = {
            "device_id": device_id,
            "u_temp_room": value,
        }
        await self._request("POST", "/set", json_data=payload)
