from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import ATTR_HVAC_MODE
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import AtmeexApi
from .const import (
    DOMAIN,
    LOGGER as _INTEGRATION_LOGGER,
)

_LOGGER = logging.getLogger(__name__)

# 7 скоростей вентилятора
FAN_SPEEDS = ["0", "1", "2", "3", "4", "5", "6", "7"]

# Режимы работы заслонки / приточного блока
BRIZER_SWING_MODES = [
    "supply",          # приточная вентиляция
    "recirculation",   # рециркуляция
    "mixed",           # смешанный режим
    "valve",           # приточный клапан
]

# Ступени увлажнения и соответствующие значения ползунка
HUMIDITY_LEVELS = [0, 33, 66, 100]  # slider %
HUMIDITY_STAGES = [0, 1, 2, 3]      # значения u_hum_stg


async def async_setup_entry(hass, entry, async_add_entities):
    """Создаём климат-сущности для каждого бризера."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api: AtmeexApi = hass.data[DOMAIN][entry.entry_id]["api"]

    entities: list[AtmeexClimateEntity] = []

    for device_id, device in coordinator.data.items():
        entities.append(
            AtmeexClimateEntity(
                coordinator=coordinator,
                api=api,
                device_id=device_id,
            )
        )

    async_add_entities(entities)


class AtmeexClimateEntity(CoordinatorEntity, ClimateEntity):
    """Климат-устройство для бризера Atmeex."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_fan_modes = FAN_SPEEDS
    _attr_min_temp = 10
    _attr_max_temp = 30
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_precision = 0.5

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: AtmeexApi,
        device_id: int,
    ) -> None:
        super().__init__(coordinator)
        self.api = api
        self._device_id = int(device_id)

        dev = self._device
        self._attr_unique_id = f"atmeex_{self._device_id}"
        self._attr_name = dev.get("name") or f"Atmeex {self._device_id}"
        self._attr_icon = "mdi:air-purifier"

        # определяем, есть ли увлажнитель — если поле u_hum_stg присутствует
        settings = self._settings
        self._has_humidifier = "u_hum_stg" in settings and settings["u_hum_stg"] is not None

        supported = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
        # swing_mode используем под режим работы бризера (приточная / рецирк / ...)
        supported |= ClimateEntityFeature.SWING_MODE
        if self._has_humidifier:
            supported |= ClimateEntityFeature.TARGET_HUMIDITY
        self._attr_supported_features = supported

    # ------------------------------------------------------------------
    # Вспомогательные свойства
    # ------------------------------------------------------------------

    @property
    def _device(self) -> Dict[str, Any]:
        return self.coordinator.data.get(self._device_id, {}) or {}

    @property
    def _settings(self) -> Dict[str, Any]:
        return self._device.get("settings") or {}

    # ------------------------------------------------------------------
    # Основные свойства HA
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        online = bool(self._device.get("online", True))
        return online and super().available

    @property
    def hvac_mode(self) -> HVACMode:
        """OFF / HEAT (подписываем как 'Вентиляция')."""
        settings = self._settings
        on = bool(settings.get("u_pwr_on"))
        return HVACMode.HEAT if on else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.api.set_power(self._device_id, False)
        else:
            await self.api.set_power(self._device_id, True)

        await self.coordinator.async_request_refresh()

    @property
    def fan_mode(self) -> Optional[str]:
        speed = int(self._settings.get("u_fan_speed", 0))
        speed = max(0, min(7, speed))
        return FAN_SPEEDS[speed]

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        try:
            speed = int(fan_mode)
        except (TypeError, ValueError):
            _LOGGER.warning("Invalid fan_mode %s", fan_mode)
            return

        await self.api.set_fan_speed(self._device_id, speed)
        await self.coordinator.async_request_refresh()

    @property
    def target_temperature(self) -> Optional[float]:
        value = self._settings.get("u_temp_room")
        if value is None:
            # если сервер ничего не прислал — просто не показываем
            return None
        try:
            return float(value) / 10.0
        except (TypeError, ValueError):
            return None

    @property
    def current_temperature(self) -> Optional[float]:
        # Сейчас API по /devices не отдаёт фактическую температуру,
        # поэтому используем целевую как приближение.
        return self.target_temperature

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if ATTR_TEMPERATURE not in kwargs:
            return
        temperature = float(kwargs[ATTR_TEMPERATURE])
        await self.api.set_target_temperature(self._device_id, temperature)
        await self.coordinator.async_request_refresh()

    # ------------------------------------------------------------------
    # Увлажнитель — ползунок с 0 / 33 / 66 / 100 %
    # ------------------------------------------------------------------

    @property
    def min_humidity(self) -> int:
        return 0 if self._has_humidifier else None

    @property
    def max_humidity(self) -> int:
        return 100 if self._has_humidifier else None

    @property
    def target_humidity(self) -> Optional[int]:
        if not self._has_humidifier:
            return None
        stage = int(self._settings.get("u_hum_stg", 0))
        stage = max(0, min(3, stage))
        return HUMIDITY_LEVELS[stage]

    async def async_set_humidity(self, humidity: int) -> None:
        """Домкатываем ползунок до ближайшего из 0/33/66/100 и шлём 0..3."""
        if not self._has_humidifier:
            return

        # ищем ближайший элемент HUMIDITY_LEVELS
        target = int(humidity)
        diffs = [abs(target - lvl) for lvl in HUMIDITY_LEVELS]
        stage_index = diffs.index(min(diffs))
        stage = HUMIDITY_STAGES[stage_index]

        await self.api.set_humidifier_stage(self._device_id, stage)
        await self.coordinator.async_request_refresh()

    # ------------------------------------------------------------------
    # Режим работы бризера — используем swing_mode
    # ------------------------------------------------------------------

    @property
    def swing_mode(self) -> Optional[str]:
        idx = int(self._settings.get("u_damp_pos", 0))
        if idx < 0 or idx >= len(BRIZER_SWING_MODES):
            idx = 0
        return BRIZER_SWING_MODES[idx]

    @property
    def swing_modes(self) -> list[str]:
        return BRIZER_SWING_MODES

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if swing_mode not in BRIZER_SWING_MODES:
            _LOGGER.warning("Unknown swing_mode %s", swing_mode)
            return

        idx = BRIZER_SWING_MODES.index(swing_mode)
        await self.api.set_brizer_mode(self._device_id, idx)
        await self.coordinator.async_request_refresh()

    # ------------------------------------------------------------------
    # Доп. атрибуты
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        attrs: Dict[str, Any] = {}
        dev = self._device
        settings = self._settings

        attrs["online"] = dev.get("online", True)
        attrs["device_id"] = self._device_id
        attrs["model"] = dev.get("model")

        attrs["u_pwr_on"] = settings.get("u_pwr_on")
        attrs["u_fan_speed"] = settings.get("u_fan_speed")
        attrs["u_temp_room"] = settings.get("u_temp_room")
        attrs["u_hum_stg"] = settings.get("u_hum_stg")
        attrs["u_damp_pos"] = settings.get("u_damp_pos")

        return attrs
