from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, PLATFORMS, CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN
from .api import AtmeexApi  # <— наш aiohttp-клиент

_LOGGER = logging.getLogger(__name__)
UPDATE_INTERVAL = timedelta(seconds=30)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    base_url = "https://api.iot.atmeex.com"
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    api = AtmeexApi(base_url)
    await api.async_init()
    try:
        await api.login(email, password)
        devices = await api.list_devices()
        _LOGGER.debug("Atmeex devices: %s", devices)
    except Exception as e:
        await api.async_close()
        raise ConfigEntryNotReady(str(e)) from e

    coordinator = AtmeexDataCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: AtmeexDataCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    try:
        await coordinator.api.async_close()
    except Exception:
        _LOGGER.debug("Error closing API session", exc_info=True)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

class AtmeexDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: AtmeexApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Atmeex Cloud coordinator",
            update_interval=UPDATE_INTERVAL,
        )
        self.hass = hass
        self.entry = entry
        self.api = api
        self.devices: list[dict[str, Any]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            self.devices = await self.api.list_devices()
            states: dict[str, Any] = {}
            for d in self.devices:
                did = str(d.get("id") or d.get("device_id"))
                if not did:
                    continue
                states[did] = await self.api.get_device_state(did)

            # Если API обновляет токены — обновим запись
            new_access = getattr(getattr(self.api, "auth", None), "_access_token", None)
            new_refresh = getattr(getattr(self.api, "auth", None), "_refresh_token", None)
            if new_access and new_refresh:
                data = dict(self.entry.data)
                if data.get(CONF_ACCESS_TOKEN) != new_access or data.get(CONF_REFRESH_TOKEN) != new_refresh:
                    data[CONF_ACCESS_TOKEN] = new_access
                    data[CONF_REFRESH_TOKEN] = new_refresh
                    await self.hass.config_entries.async_update_entry(self.entry, data=data)

            return {"devices": self.devices, "states": states}
        except Exception as err:
            raise UpdateFailed(str(err)) from err
