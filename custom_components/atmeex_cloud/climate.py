from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.update_coordinator import CoordinatorEntity

class AtmeexClimate(CoordinatorEntity, ClimateEntity):
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = TEMP_CELSIUS
    _attr_min_temp = 10
    _attr_max_temp = 30

    def __init__(self, coordinator, api, device):
        super().__init__(coordinator)
        self.api = api
        self._device_id = device["id"]
        self._attr_name = device["name"]

    @property
    def condition(self):
        return self.coordinator.data["states"].get(str(self._device_id), {})

    @property
    def hvac_mode(self):
        return HVACMode.HEAT if self.condition.get("pwr_on") else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode):
        await self.api.set_power(self._device_id, hvac_mode != HVACMode.OFF)
        await self.coordinator.async_request_refresh()

    @property
    def current_temperature(self):
        t = self.condition.get("temp_room")
        return t / 10 if t else None

    @property
    def target_temperature(self):
        t = self.condition.get("u_temp_room")
        return t / 10 if t else None

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get("temperature")
        if temp is not None:
            await self.api.set_target_temperature(self._device_id, temp)
            await self.coordinator.async_request_refresh()
