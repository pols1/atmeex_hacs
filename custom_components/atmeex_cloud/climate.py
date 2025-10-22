from __future__ import annotations
import logging

from homeassistant.components.climate import ClimateEntity, HVACMode, ClimateEntityFeature
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AtmeexCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator: AtmeexCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[AtmeexClimate] = []
    for dev in coordinator.devices:
        did = str(dev.get("id") or dev.get("device_id") or "")
        if not did:
            continue
        name = dev.get("name") or did
        entities.append(AtmeexClimate(coordinator, did, name))
    async_add_entities(entities)

class AtmeexClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]  # при необходимости дополним
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: AtmeexCoordinator, device_id: str, name: str):
        super().__init__(coordinator)
        self.api = coordinator.api
        self._device_id = device_id
        self._attr_name = f"{name} climate"
        self._attr_unique_id = f"{device_id}_climate"

    @property
    def hvac_mode(self):
        st = self.coordinator.data.get("states", {}).get(self._device_id, {})
        return HVACMode.HEAT if st.get("power") else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        await self.api.set_power(self._device_id, hvac_mode != HVACMode.OFF)
        await self.coordinator.async_request_refresh()

    @property
    def current_temperature(self):
        st = self.coordinator.data.get("states", {}).get(self._device_id, {})
        return st.get("temperature")

    @property
    def target_temperature(self):
        st = self.coordinator.data.get("states", {}).get(self._device_id, {})
        return st.get("target_temperature")

    async def async_set_temperature(self, **kwargs):
        target = kwargs.get(ATTR_TEMPERATURE)
        if target is None:
            return
        # TODO: реализовать вызов API на установку цели, если поддерживается
        await self.coordinator.async_request_refresh()
