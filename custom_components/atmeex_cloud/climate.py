from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    UnitOfTemperature,
    ATTR_TEMPERATURE,
    PRECISION_WHOLE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# 7 скоростей вентилятора
FAN_MODES = ["1", "2", "3", "4", "5", "6", "7"]

# Swing используем как "режим бризера" по condition.damp_pos (0..3)
BRIZER_SWING_MODES = [
    "приточная вентиляция",  # 0
    "рециркуляция",          # 1
    "смешанный режим",       # 2
    "приточный клапан",      # 3
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    entities: list[AtmeexClimateEntity] = []
    for dev in coordinator.data.get("devices", []):
        did = dev.get("id")
        if did is None:
            continue
        name = dev.get("name") or f"Device {did}"
        entities.append(AtmeexClimateEntity(coordinator, api, entry.entry_id, did, name))

    if entities:
        async_add_entities(entities)


class AtmeexClimateEntity(CoordinatorEntity, ClimateEntity):
    """
    Бризер "в одном устройстве":
    - Режимы HVAC: только ВЕНТИЛЯЦИЯ (FAN_ONLY) / ВЫКЛ.
    - Управление температурой (°C) и влажностью (%) — обе цели есть, на карточке будет переключатель.
    - 7 скоростей вентилятора.
    - Swing = режим бризера (damp_pos 0..3).
    - Статусы читаем всегда из coordinator (который берёт их из API).
    """

    # Режимы
    _attr_hvac_modes = [HVACMode.FAN_ONLY, HVACMode.OFF]

    # Температура
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 10
    _attr_max_temp = 30

    # Влажность (%)
    _attr_min_humidity = 0
    _attr_max_humidity = 100

    # Возможности
    _attr_fan_modes = FAN_MODES
    _attr_swing_modes = BRIZER_SWING_MODES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_HUMIDITY
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )
    _attr_icon = "mdi:air-purifier"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        api,
        entry_id: str,
        device_id: int | str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self.api = api
        self._entry_id = entry_id
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{device_id}_climate"

    # ---------- helpers ----------

    @property
    def _cond(self) -> dict[str, Any]:
        """Актуальный condition для устройства (после старта уже получен из API)."""
        return self.coordinator.data.get("states", {}).get(str(self._device_id), {}) or {}

    @staticmethod
    def _speed_to_mode(speed: int | None) -> str | None:
        if speed is None:
            return None
        s = max(1, min(7, int(speed)))
        return FAN_MODES[s - 1]

    @staticmethod
    def _stage_to_target_humidity(stage: int | None) -> int | None:
        """
        Маппинг ступени увлажнения (0..3) -> целевая влажность (%),
        т.к. API оперирует ступенями, а UI — процентом.
        """
        if stage is None:
            return None
        stage = max(0, min(3, int(stage)))
        return [0, 33, 66, 100][stage]

    @staticmethod
    def _humidity_to_stage(percent: int | float | None) -> int:
        """Обратный маппинг из процента влажности к ступени 0..3."""
        if percent is None:
            return 0
        try:
            p = float(percent)
        except (TypeError, ValueError):
            return 0
        if p <= 0:
            return 0
        if p <= 33:
            return 1
        if p <= 66:
            return 2
        return 3

    @property
    def _refresh_device_cb(self) -> Optional[Callable[[int | str], Any]]:
        """Колбэк, который дочитывает одно устройство из API и мгновенно обновляет coordinator."""
        data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        cb = data.get("refresh_device")
        return cb if callable(cb) else None

    async def _instant_refresh(self) -> None:
        """Если доступен колбэк — мгновенно дочитаем состояние одного устройства."""
        cb = self._refresh_device_cb
        if cb:
            await cb(self._device_id)

    # ---------- HVAC (только FAN_ONLY / OFF) ----------

    @property
    def hvac_mode(self) -> HVACMode:
        # Режим не зависит от наличия целевой температуры — только по питанию
        return HVACMode.FAN_ONLY if bool(self._cond.get("pwr_on")) else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.api.set_power(self._device_id, hvac_mode != HVACMode.OFF)
        await self._instant_refresh()

    # ---------- Температура ----------

    @property
    def current_temperature(self):
        # temp_room в deci°C (напр. 250 = 25.0°C)
        val = self._cond.get("temp_room")
        return (val / 10) if isinstance(val, (int, float)) else None

    @property
    def target_temperature(self):
        # u_temp_room в deci°C
        val = self._cond.get("u_temp_room")
        return (val / 10) if isinstance(val, (int, float)) else None

    async def async_set_temperature(self, **kwargs) -> None:
        t = kwargs.get(ATTR_TEMPERATURE)
        if t is None:
            return
        # Если устройство выключено — включим «Вентиляцию», затем установим цель.
        if not bool(self._cond.get("pwr_on")):
            await self.api.set_power(self._device_id, True)
        await self.api.set_target_temperature(self._device_id, float(t))
        await self._instant_refresh()

    # ---------- Влажность ----------

    @property
    def current_humidity(self) -> int | None:
        # Фактическая влажность помещения, %, если отдается
        val = self._cond.get("hum_room")
        if isinstance(val, (int, float)):
            return int(val)
        return None

    @property
    def target_humidity(self) -> int | None:
        # Цель строим по ступени hum_stg (0..3) → 0/33/66/100
        stage = self._cond.get("hum_stg")
        if isinstance(stage, (int, float)):
            return self._stage_to_target_humidity(int(stage))
        # Fallback: если знаем только факт работы насоса испарителя
        pump = self._cond.get("eva_pump_on")
        if isinstance(pump, bool):
            return 33 if pump else 0
        return 0

    async def async_set_humidity(self, humidity: int) -> None:
        stage = self._humidity_to_stage(humidity)
        await self.api.set_humid_stage(self._device_id, stage)
        await self._instant_refresh()

    # ---------- Вентилятор ----------

    @property
    def fan_mode(self) -> str | None:
        speed = self._cond.get("fan_speed")
        return self._speed_to_mode(speed)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        try:
            speed = int(fan_mode)
        except (TypeError, ValueError):
            _LOGGER.warning("Unsupported fan_mode %s", fan_mode)
            return
        if not 1 <= speed <= 7:
            _LOGGER.warning("Unsupported fan_mode %s", fan_mode)
            return
        await self.api.set_fan_speed(self._device_id, speed)
        await self._instant_refresh()

    # ---------- Swing = режим бризера ----------

    @property
    def swing_mode(self) -> str | None:
        pos = self._cond.get("damp_pos")
        if isinstance(pos, int) and 0 <= pos <= 3:
            return BRIZER_SWING_MODES[pos]
        return None

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if swing_mode not in BRIZER_SWING_MODES:
            _LOGGER.warning("Unsupported swing_mode %s", swing_mode)
            return
        await self.api.set_brizer_mode(self._device_id, BRIZER_SWING_MODES.index(swing_mode))
        await self._instant_refresh()

    # ---------- Доп. флаг ----------

    @property
    def is_on(self) -> bool:
        return bool(self._cond.get("pwr_on"))
