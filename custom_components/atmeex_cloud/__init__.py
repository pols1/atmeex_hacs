from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import AtmeexApi
from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = AtmeexApi()
    await api.async_init()
    await api.login(entry.data["email"], entry.data["password"])

    async def _async_update_data() -> dict[str, Any]:
        devices = await api.get_devices()
        # condition сразу внутри списка устройств
        states = {str(d.get("id")): (d.get("condition") or {}) for d in devices if d.get("id") is not None}
        return {"devices": devices, "states": states}

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Atmeex Cloud",
        update_method=_async_update_data,
        update_interval=timedelta(minutes=2),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {"api": api, "coordinator": coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        stored = hass.data[DOMAIN].pop(entry.entry_id, None)
        if stored and (api := stored.get("api")):
            try:
                await api.async_close()
            except Exception:
                _LOGGER.debug("Error closing API session", exc_info=True)
    return unload_ok
