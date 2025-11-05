from __future__ import annotations

import logging
from typing import Any

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

FAN_MODES = ["1", "2", "3", "4", "5", "6", "7"]

# режим бризера (по condition.damp_pos 0..3)
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
        entities.append(AtmeexClimateEntity(coordinator, api, did, name))

    if entities:
        async_add_entities(entities)


class AtmeexClimateEntity(CoordinatorEntity, ClimateEntity):
    """
    Бризер в одном устройстве:
    - Режимы HVAC: OFF / FAN_ONLY / HEAT (вентиляция и нагрев)
    - 7 скоростей вентилятора
    - Цель по температуре (°C) И цель по влажности (%), чтобы в UI был переключатель
    - Swing-mode = режим бризера (damp_pos 0..3)
    """

    # HVAC
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY, HVACMode.HEAT]

    # Температура
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 10
    _attr_max_temp = 30

    # Влажность (%)
    _attr_min_humidity = 0
    _attr_max_humidity = 100

    # Остальные возможности
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

    def __init__(self, coordinator, api, device_id: int | str, name: str) -> None:
        super().__init__(coordinator)
        self.api = api
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{device_id}_climate"

    # ---------- helpers ----------

    @property
    def _cond(self) -> dict[str, Any]:
        """Актуальное состояние из координатора (обновляется с API)."""
        return self.coordinator.data.get("states", {}).get(str(self._device_id), {}) or {}

    @staticmethod
    def _speed_to_mode(speed: int | None) -> str | None:
        if speed is None:
            return None
        s = max(1, min(7, int(speed)))
        return FAN_MODES[s - 1]

    # Маппинг «ступень увлажнения (0..3) ↔ целевая влажность (%)» для UI.
    # Цели в процентах у API нет, поэтому привязываем проценты к ступеням:
    #   0 → 0%, 1 → 33%, 2 → 66%, 3 → 100%  (и при установке берём ближайшую ступень)
    @staticmethod
    def _stage_to_target_humidity(stage: int | None) -> int | None:
        if stage is None:
            return None
        stage = max(0, min(3, int(stage)))
        return [0, 33, 66, 100][stage]

    @staticmethod
    def _humidity_to_stage(percent: int | float | None) -> int:
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

    # ---------- HVAC ----------

    @property
    def hvac_mode(self) -> HVACMode:
        # включён/выключен берём из condition.pwr_on
        if not bool(self._cond.get("pwr_on")):
            return HVACMode.OFF
        # если есть целевая температура — считаем, что режим HEAT,
        # иначе просто вентиляция (FAN_ONLY)
        return HVACMode.HEAT if self._cond.get("u_temp_room") is not None else HVACMode.FAN_ONLY

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.api.set_power(self._device_id, hvac_mode != HVACMode.OFF)
        await self.coordinator.async_request_refresh()

    # ---------- температура ----------

    @property
    def current_temperature(self):
        # temp_room приходит как deci°C (например 250 = 25.0°C)
        val = self._cond.get("temp_room")
        return (val / 10) if isinstance(val, (int, float)) else None

    @property
    def target_temperature(self):
        # u_temp_room (deci°C) — целевая температура
        val = self._cond.get("u_temp_room")
        return (val / 10) if isinstance(val, (int, float)) else None

    async def async_set_temperature(self, **kwargs) -> None:
        t = kwargs.get(ATTR_TEMPERATURE)
        if t is None:
            return
        await self.api.set_target_temperature(self._device_id, float(t))
        await self.coordinator.async_request_refresh()

    # ---------- влажность ----------

    @property
    def current_humidity(self) -> int | None:
        # фактическая влажность в помещении (проценты)
        val = self._cond.get("hum_room")
        if isinstance(val, (int, float)):
            return int(val)
        return None

    @property
    def target_humidity(self) -> int | None:
        # целевая «в процентах» строится по ступени увлажнения
        stage = self._cond.get("hum_stg")
        if isinstance(stage, (int, float)):
            return self._stage_to_target_humidity(int(stage))
        # если сервер не отдаёт hum_stg, попробуем по факту работы насоса (on → 33%)
        pump = self._cond.get("eva_pump_on")
        if isinstance(pump, bool):
            return 33 if pump else 0
        return 0

    async def async_set_humidity(self, humidity: int) -> None:
        # переводим процент в ближайшую «ступень» 0..3 и отправляем в API как u_hum_stg
        stage = self._humidity_to_stage(humidity)
        await self.api.set_humid_stage(self._device_id, stage)
        await self.coordinator.async_request_refresh()

    # ---------- вентилятор ----------

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
        await self.coordinator.async_request_refresh()

    # ---------- swing = режим бризера ----------

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
        await self.coordinator.async_request_refresh()

    # ---------- удобный флаг ----------

    @property
    def is_on(self) -> bool:
        return bool(self._cond.get("pwr_on"))
