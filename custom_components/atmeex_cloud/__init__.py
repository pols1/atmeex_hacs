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

    last_ok: dict[str, Any] = {"devices": [], "states": {}}

    async def _async_update_data() -> dict[str, Any]:
        nonlocal last_ok
        try:
            devices = await api.get_devices()
            states = {str(d.get("id")): (d.get("condition") or {}) for d in devices if d.get("id") is not None}
            last_ok = {"devices": devices, "states": states}
            return last_ok
        except Exception as err:
            _LOGGER.warning("Atmeex Cloud update failed, using last known state: %s", err)
            return last_ok

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Atmeex Cloud",
        update_method=_async_update_data,
        update_interval=timedelta(minutes=2),
    )
    await coordinator.async_config_entry_first_refresh()

    async def refresh_device(device_id: int | str) -> None:
        """Принудительно дочитать один девайс и сразу обновить coordinator."""
        try:
            full = await api.get_device(device_id)
        except Exception as e:
            _LOGGER.warning("Failed to refresh device %s: %s", device_id, e)
            return
        # Текущее состояние в координаторе
        cur = coordinator.data or {"devices": [], "states": {}}
        devices = list(cur.get("devices", []))
        states = dict(cur.get("states", {}))

        # Обновим devices (заменим элемент по id, либо добавим)
        replaced = False
        for i, d in enumerate(devices):
            if d.get("id") == full.get("id"):
                devices[i] = full
                replaced = True
                break
        if not replaced:
            devices.append(full)

        # Обновим states
        states[str(full.get("id"))] = full.get("condition") or {}

        # Мгновенно протолкнём в UI
        coordinator.async_set_updated_data({"devices": devices, "states": states})

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "refresh_device": refresh_device,
    }
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
