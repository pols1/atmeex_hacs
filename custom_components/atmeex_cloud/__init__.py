"""Atmeex Cloud integration for Home Assistant."""
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.const import Platform, CONF_EMAIL, CONF_PASSWORD

from .api import AtmeexApi, ApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Какие платформы поднимаем. Если у тебя есть fan.py/select.py – их тоже можно включить.
PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    # Platform.FAN,
    # Platform.SELECT,
]


class AtmeexDataUpdateCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
    """Координатор обновления данных с облака Atmeex."""

    def __init__(self, hass: HomeAssistant, api: AtmeexApi) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Atmeex Cloud",
            update_interval=timedelta(seconds=30),
        )
        self.api = api

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        """Fetch data from Atmeex API."""
        try:
            devices = await self.api.get_devices()
        except ApiError as err:
            # Здесь уже внутри ApiError может быть и 401, и 500 – просто пробрасываем в лог
            raise UpdateFailed(f"Error communicating with Atmeex API: {err}") from err
        except Exception as err:  # на всякий случай, чтобы не валить весь HA
            raise UpdateFailed(f"Unexpected error from Atmeex API: {err}") from err

        # Ожидаем, что get_devices вернёт список словарей устройств
        data: dict[int, dict[str, Any]] = {}
        for dev in devices:
            dev_id = dev.get("id")
            if dev_id is None:
                continue
            data[int(dev_id)] = dev
        return data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Atmeex Cloud from a config entry."""
    _LOGGER.debug("Setting up Atmeex Cloud entry %s", entry.entry_id)

    # Достаём логин/пароль из config_flow (email и password)
    email: str | None = entry.data.get(CONF_EMAIL)
    password: str | None = entry.data.get(CONF_PASSWORD)

    if not email or not password:
        raise ConfigEntryError("Atmeex Cloud: missing email or password in config entry")

    session = async_get_clientsession(hass)

    try:
        api = AtmeexApi(session, email, password)
    except Exception as err:
        # Если даже конструктор упадёт, не даём стартануть HA-сессию
        raise ConfigEntryNotReady(
            f"Cannot initialize Atmeex API client: {err}"
        ) from err

    coordinator = AtmeexDataUpdateCoordinator(hass, api)

    # Первый запрос к API (получаем список устройств и проверяем доступность)
    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as err:
        # Не смогли получить устройства – интеграцию помечаем как "пока не готово"
        raise ConfigEntryNotReady(
            f"Atmeex Cloud: first refresh failed: {err}"
        ) from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Atmeex Cloud integration set up for %s", email)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Atmeex Cloud config entry."""
    _LOGGER.debug("Unloading Atmeex Cloud entry %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(entry.entry_id, None)
        if not domain_data:
            hass.data.pop(DOMAIN, None)

    return unload_ok
