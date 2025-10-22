from __future__ import annotations

import logging
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up climate entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    entities: list[AtmeexClimate] = []
    for dev in coordinator.data.get("devices", []):
        did = dev.get("id")
        if did is None:
            continue
        name = dev.get("name") or f"Device {did}"
        entities.append(AtmeexClimate(coordinator, api, did, name))

    if entities:
        async_add_entities(entities)


class AtmeexClimate(CoordinatorEntity, ClimateEntity):
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 10
    _attr_max_temp = 30
    _attr_has_entity_name = True

    def __init__(self, coordinator, api, device_id: int | str, name: str) -> None:
        super().__init__(coordinator)
        self.api = api
        self._device_id = device_id
        self._attr_name = f"{name} climate"
        self._attr_unique_id = f"{device_id}_climate"

    # удобный доступ к состоянию
    @property
    def _cond(self) -> dict:
        return self.coordinator.data.get("states", {}).get(str(self._device_id), {}) or {}

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self._cond.get("pwr_on") else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.api.set_power(self._device_id, hvac_mode != HVACMode.OFF)
        await self.coordinator.async_request_refresh()

    @property
    def current_temperature(self):
        # в API temp_room приходит как deci°C (например, 250 = 25.0°C)
        val = self._cond.get("temp_room")
        return (val / 10) if isinstance(val, (int, float)) else None

    @property
    def target_temperature(self):
        # целевая уходит/приходит как u_temp_room (deci°C)
        val = self._cond.get("u_temp_room")
        return (val / 10) if isinstance(val, (int, float)) else None

    async def async_set_temperature(self, **kwargs) -> None:
        t = kwargs.get(ATTR_TEMPERATURE)
        if t is None:
            return
        await self.api.set_target_temperature(self._device_id, float(t))
        await self.coordinator.async_request_refresh()
