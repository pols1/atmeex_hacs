from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import AtmeexApi, ApiError
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.FAN,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Atmeex Cloud from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    email: str = entry.data["email"]
    password: str = entry.data["password"]

    session: ClientSession = aiohttp_client.async_get_clientsession(hass)
    api = AtmeexApi(session=session, email=email, password=password)

    async def _async_update_data() -> list[dict[str, Any]]:
        """Fetch devices list from Atmeex."""
        try:
            # здесь внутри sign_in сам обновит токен при необходимости
            devices = await api.get_devices()
            _LOGGER.debug("Atmeex: fetched %d devices", len(devices))
            return devices
        except ApiError as err:
            # если токен протух / проблемы с авторизацией — кидаем специальное исключение
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(f"Atmeex auth error: {err}") from err
            raise UpdateFailed(f"Error communicating with Atmeex: {err}") from err

    coordinator = DataUpdateCoordinator[
        list[dict[str, Any]]
    ](
        hass,
        _LOGGER,
        name="Atmeex Cloud",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
    )

    # первая синхронизация — если тут всё ок, значит авторизация прошла и устройства пришли
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
