from __future__ import annotations

from typing import Any

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_STEP,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

HVAC_MODES = [HVACMode.HEAT, HVACMode.OFF]

# 0..3 -> 0/33/66/100
HUM_STAGES = {
    0: 0,
    1: 33,
    2: 66,
    3: 100,
}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up Atmeex climate entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DataUpdateCoordinator[list[dict[str, Any]]] = data["coordinator"]

    entities: list[AtmeexClimateEntity] = []

    for dev in coordinator.data:
        # НЕ фильтруем по condition, используем settings + online
        settings = dev.get("settings") or {}
        name = dev.get("name", f"Atmeex {dev.get('id')}")
        device_id = dev.get("id")

        if device_id is None:
            continue

        entities.append(
            AtmeexClimateEntity(
                coordinator=coordinator,
                device=dev,
                device_id=device_id,
                name=name,
            )
        )

    if not entities:
        _LOGGER.warning("Atmeex: no devices found for climate platform")

    async_add_entities(entities)


class AtmeexClimateEntity(CoordinatorEntity, ClimateEntity):
    """Representation of an Atmeex brizer as climate device."""

    _attr_hvac_modes = HVAC_MODES
    _attr_min_temp = 10
    _attr_max_temp = 30
    _attr_precision = 0.5
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
    )

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[list[dict[str, Any]]],
        device: dict[str, Any],
        device_id: int,
        name: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"atmeex_climate_{device_id}"

        self._update_from_device(device)

    # --- HA helpers ---

    @property
    def device_info(self) -> DeviceInfo:
        dev = self._device_from_coordinator()
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_id))},
            name=dev.get("name", f"Atmeex {self._device_id}"),
            manufacturer="Atmeex",
            model=dev.get("model") or "Brizer",
        )

    def _device_from_coordinator(self) -> dict[str, Any]:
        for d in self.coordinator.data:
            if d.get("id") == self._device_id:
                return d
        return {}

    def _update_from_device(self, dev: dict[str, Any]) -> None:
        settings = dev.get("settings") or {}
        condition = dev.get("condition") or {}

        # температура в API *10
        temp_room_raw = condition.get("temp_room") or settings.get("u_temp_room")
        if isinstance(temp_room_raw, (int, float)):
            self._attr_target_temperature = temp_room_raw / 10.0
        else:
            self._attr_target_temperature = 22.0

        # текущая температура (если есть)
        temp_in_raw = condition.get("temp_in")
        if isinstance(temp_in_raw, (int, float)):
            self._attr_current_temperature = temp_in_raw / 10.0

        # режим включен/выключен
        pwr_on = settings.get("u_pwr_on")
        if pwr_on is None:
            pwr_on = condition.get("pwr_on", 0)

        self._attr_hvac_mode = HVACMode.HEAT if pwr_on else HVACMode.OFF

        # скорость вентилятора 0..7 → строка
        fan_speed = settings.get("u_fan_speed", 0)
        self._attr_fan_mode = str(int(fan_speed))

        # режимы вентилятора: 0..7
        self._attr_fan_modes = [str(i) for i in range(0, 8)]

        # влажность (текущая)
        hum_room = condition.get("hum_room")
        if isinstance(hum_room, (int, float)):
            self._attr_current_humidity = int(hum_room)

        # наличие увлажнителя — если прибор его поддерживает
        hum_stage = settings.get("u_hum_stg")
        self._has_humidifier = hum_stage is not None

        if self._has_humidifier:
            # отображаем как "Влажность" с шагами 0/33/66/100
            stage = int(hum_stage)
            self._attr_target_humidity = HUM_STAGES.get(stage, 0)

    async def async_update(self) -> None:
        """Update from coordinator data."""
        await super().async_update()
        self._update_from_device(self._device_from_coordinator())

    # --- Свойства, которые HA читает ---

    @property
    def available(self) -> bool:
        dev = self._device_from_coordinator()
        return bool(dev.get("online", True)) and super().available

    # --- Управление температурой ---

    async def async_set_temperature(self, **kwargs: Any) -> None:
        from .api import AtmeexApi  # локальный импорт, чтобы избежать циклов

        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return

        data = self.hass.data[DOMAIN]
        # берём api для текущего entry
        api: AtmeexApi | None = None
        for entry_id, info in data.items():
            if info.get("coordinator") is self.coordinator:
                api = info["api"]
                break

        if api is None:
            _LOGGER.error("Atmeex: api not found for climate entity")
            return

        await api.set_target_temperature(self._device_id, float(temp))
        await self.coordinator.async_request_refresh()

    # --- Управление включением / выключением ---

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        from .api import AtmeexApi

        data = self.hass.data[DOMAIN]
        api: AtmeexApi | None = None
        for entry_id, info in data.items():
            if info.get("coordinator") is self.coordinator:
                api = info["api"]
                break

        if api is None:
            _LOGGER.error("Atmeex: api not found for climate entity")
            return

        on = hvac_mode == HVACMode.HEAT
        await api.set_power(self._device_id, on)
        await self.coordinator.async_request_refresh()

    # --- Управление скоростью вентилятора ---

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        from .api import AtmeexApi

        try:
            speed = int(fan_mode)
        except ValueError:
            _LOGGER.warning("Atmeex: invalid fan_mode %s", fan_mode)
            return

        data = self.hass.data[DOMAIN]
        api: AtmeexApi | None = None
        for entry_id, info in data.items():
            if info.get("coordinator") is self.coordinator:
                api = info["api"]
                break

        if api is None:
            _LOGGER.error("Atmeex: api not found for climate entity")
            return

        await api.set_fan_speed(self._device_id, speed)
        await self.coordinator.async_request_refresh()
