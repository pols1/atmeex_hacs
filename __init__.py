from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import AtmeexApi, ApiError
from .const import DOMAIN, LOGGER as _INTEGRATION_LOGGER, PLATFORMS


CoordinatorData = Dict[str, Any]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Atmeex Cloud from a config entry."""
    session = async_get_clientsession(hass)

    # В config_flow мы кладём именно такие ключи
    email: str = entry.data["email"]
    password: str = entry.data["password"]

    api = AtmeexApi(session, email=email, password=password)

    async def async_update_data() -> CoordinatorData:
        """Fetch devices + conditions from API."""
        try:
            raw = await api.get_devices()
        except ApiError as err:
            _INTEGRATION_LOGGER.error("Atmeex: error fetching devices: %s", err)
            raise

        devices_list = []
        states: Dict[str, Any] = {}

        # Наш api.get_devices() возвращает dict {"devices": [...], "states": {...}}
        if isinstance(raw, dict):
            devices_list = raw.get("devices") or []
            if not isinstance(devices_list, list):
                devices_list = []
            states_raw = raw.get("states") or {}
            if isinstance(states_raw, dict):
                states = states_raw
        elif isinstance(raw, list):
            # запасной вариант, если вдруг вернёмся к старому формату
            devices_list = raw

        ids: list[int] = []
        for dev in devices_list:
            if not isinstance(dev, dict):
                continue
            did = dev.get("id")
            try:
                did_int = int(did)
            except (TypeError, ValueError):
                continue
            ids.append(did_int)

        _INTEGRATION_LOGGER.debug("Atmeex: coordinator devices = %s", ids)

        return {
            "devices": devices_list,
            "states": states,
        }

    coordinator = DataUpdateCoordinator(
        hass,
        _INTEGRATION_LOGGER,
        name="Atmeex Cloud devices",
        update_method=async_update_data,
        update_interval=timedelta(seconds=30),
    )

    # Первый запрос к API
    await coordinator.async_config_entry_first_refresh()

    async def refresh_device(device_id: int | str) -> None:
        """Принудительно обновить данные (пока общий рефреш)."""
        await coordinator.async_request_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "refresh_device": refresh_device,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _INTEGRATION_LOGGER.info(
        "Atmeex Cloud: setup complete for %s, devices will be loaded by platforms",
        email,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Atmeex Cloud config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data.get(DOMAIN, {})
        entry_data.pop(entry.entry_id, None)
        if not entry_data:
            hass.data.pop(DOMAIN, None)
    return unload_ok