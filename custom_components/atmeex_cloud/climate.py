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

FAN_MODES = ["1", "2", "3", "4", "5", "6", "7"]
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
    """Бризер как ClimateEntity с температурой, влажностью и скоростью вентилятора."""

    _attr_hvac_modes = [HVACMode.FAN_ONLY, HVACMode.OFF]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 10
    _attr_max_temp = 30
    _attr_min_humidity = 0
    _attr_max_humidity = 100
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
        """Нормализованное состояние устройства."""
        return self.coordinator.data.get("states", {}).get(str(self._device_id), {}) or {}

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.FAN_ONLY if bool(self._cond.get("pwr_on")) else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.api.set_power(self._device_id, hvac_mode != HVACMode.OFF)
        await self._refresh()

    async def _refresh(self) -> None:
        cb = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get("refresh_device")
        if callable(cb):
            await cb(self._device_id)

    # ---------- Температура ----------

    @property
    def current_temperature(self):
        val = self._cond.get("temp_room")
        return (val / 10) if isinstance(val, (int, float)) else None

    @property
    def target_temperature(self):
        val = self._cond.get("u_temp_room")
        return (val / 10) if isinstance(val, (int, float)) else None

    async def async_set_temperature(self, **kwargs) -> None:
        t = kwargs.get(ATTR_TEMPERATURE)
        if t is None:
            return
        if not bool(self._cond.get("pwr_on")):
            await self.api.set_power(self._device_id, True)
        await self.api.set_target_temperature(self._device_id, float(t))
        await self._refresh()

    # ---------- Влажность ----------

    @property
    def current_humidity(self) -> int | None:
        val = self._cond.get("hum_room")
        return int(val) if isinstance(val, (int, float)) else None

    @property
    def target_humidity(self) -> int | None:
        stage = self._cond.get("hum_stg")
        if stage is None:
            return 0
        return [0, 33, 66, 100][max(0, min(3, int(stage)))]

    async def async_set_humidity(self, humidity: int) -> None:
        stage = 0
        if humidity > 0 and humidity <= 33:
            stage = 1
        elif humidity <= 66:
            stage = 2
        else:
            stage = 3
        await self.api.set_humid_stage(self._device_id, stage)
        await self._refresh()

    # ---------- Вентилятор ----------

    @property
    def fan_mode(self) -> str | None:
        speed = self._cond.get("fan_speed")
        if isinstance(speed, (int, float)):
            speed = int(speed)
        return FAN_MODES[speed - 1] if speed in range(1, 8) else None

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        try:
            speed = int(fan_mode)
        except Exception:
            return
        await self.api.set_fan_speed(self._device_id, speed)
        await self._refresh()

    # ---------- Swing ----------

    @property
    def swing_mode(self) -> str | None:
        pos = self._cond.get("damp_pos")
        if isinstance(pos, int) and 0 <= pos <= 3:
            return BRIZER_SWING_MODES[pos]
        return None

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if swing_mode not in BRIZER_SWING_MODES:
            return
        await self.api.set_brizer_mode(self._device_id, BRIZER_SWING_MODES.index(swing_mode))
        await self._refresh()

    # ---------- Атрибуты для отладки ----------

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return dict(self._cond)
