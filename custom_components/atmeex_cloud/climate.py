from __future__ import annotations
import logging

from homeassistant.components.climate import ClimateEntity, HVACMode, ClimateEntityFeature
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AtmeexDataCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator: AtmeexDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [AtmeexClimateEntity(coordinator, dev) for dev in coordinator.devices]
    async_add_entities(entities)

class AtmeexClimateEntity(CoordinatorEntity, ClimateEntity):
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]  # пример
    _attr_has_entity_name = True

    def __init__(self, coordinator: AtmeexDataCoordinator, device: dict):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.api = coordinator.api
        self._device = device
        self._device_id = str(device.get("id") or device.get("device_id"))
        name = device.get("name") or self._device_id
        self._attr_name = f"{name} climate"
        self._attr_unique_id = f"{self._device_id}_climate"

    @property
    def hvac_mode(self):
        st = self.coordinator.data.get("states", {}).get(self._device_id, {})
        # TODO: сопоставить реальный ключ состояния питания/режима
        return HVACMode.HEAT if st.get("power") else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        on = hvac_mode != HVACMode.OFF
        await self.api.set_power(self._device_id, on)
        await self.coordinator.async_request_refresh()

    @property
    def current_temperature(self):
        st = self.coordinator.data.get("states", {}).get(self._device_id, {})
        return st.get("temperature")  # TODO: реальный ключ

    @property
    def target_temperature(self):
        st = self.coordinator.data.get("states", {}).get(self._device_id, {})
        return st.get("target_temperature")  # TODO

    async def async_set_temperature(self, **kwargs):
        target = kwargs.get(ATTR_TEMPERATURE)
        if target is None:
            return
        # TODO: реализовать вызов API на установку температуры, если поддерживается:
        # await self.api.set_target_temperature(self._device_id, target)
        await self.coordinator.async_request_refresh()
