from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE, PRECISION_WHOLE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FAN_MODES = ["1", "2", "3", "4", "5", "6", "7"]

# Под swing используем режим бризера (по damp_pos 0..3)
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
    """Климат-сущность Airnanny/Atmeex."""

    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.FAN_ONLY, HVACMode.OFF]
    _attr_min_temp = 10
    _attr_max_temp = 30
    _attr_fan_modes = FAN_MODES
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 0.5
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )
    _attr_icon = "mdi:air-purifier"
    _attr_has_entity_name = True

    _attr_fan_mode: str | None = None
    _attr_swing_modes = BRIZER_SWING_MODES
    _attr_swing_mode: str | None = None

    def __init__(self, coordinator, api, device_id: int | str, name: str) -> None:
        super().__init__(coordinator)
        self.api = api
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{device_id}"

    # ---------- helpers ----------

    @property
    def _cond(self) -> dict[str, Any]:
        return self.coordinator.data.get("states", {}).get(str(self._device_id), {}) or {}

    def _speed_to_fan_mode(self, speed: int | None) -> str | None:
        if speed is None:
            return None
        s = max(1, min(7, int(speed)))
        return FAN_MODES[s - 1]

    # ---------- HVAC ----------

    @property
    def hvac_mode(self) -> HVACMode:
        pwr = bool(self._cond.get("pwr_on"))
        if not pwr:
            return HVACMode.OFF
        # если есть целевая — трактуем как HEAT, иначе — вентиляция
        if self._cond.get("u_temp_room") is not None:
            return HVACMode.HEAT
        return HVACMode.FAN_ONLY

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.api.set_power(self._device_id, hvac_mode != HVACMode.OFF)
        await self.coordinator.async_request_refresh()

    # ---------- temperature ----------

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
        await self.api.set_target_temperature(self._device_id, float(t))
        await self.coordinator.async_request_refresh()

    # ---------- fan ----------

    @property
    def fan_mode(self) -> str | None:
        current_speed = self._cond.get("fan_speed")
        mode = self._speed_to_fan_mode(current_speed)
        if mode is not None:
            self._attr_fan_mode = mode
        return self._attr_fan_mode

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        try:
            speed = int(fan_mode)
        except (TypeError, ValueError):
            speed = None
        if speed is None or speed < 1 or speed > 7:
            _LOGGER.warning("Unsupported fan_mode %s", fan_mode)
            return
        await self.api.set_fan_speed(self._device_id, speed)
        self._attr_fan_mode = fan_mode
        await self.coordinator.async_request_refresh()

    # ---------- swing = brizer mode ----------

    @property
    def swing_mode(self) -> str | None:
        """
        Подхватываем текущий режим бризера при старте:
        condition.damp_pos: 0..3 -> BRIZER_SWING_MODES
        """
        pos = self._cond.get("damp_pos")
        if isinstance(pos, int) and 0 <= pos <= 3:
            self._attr_swing_mode = BRIZER_SWING_MODES[pos]
        return self._attr_swing_mode

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if swing_mode not in BRIZER_SWING_MODES:
            _LOGGER.warning("Unsupported swing_mode %s", swing_mode)
            return
        pos = BRIZER_SWING_MODES.index(swing_mode)  # 0..3
        await self.api.set_brizer_mode(self._device_id, pos)
        self._attr_swing_mode = swing_mode
        await self.coordinator.async_request_refresh()

    # ---------- power convenience ----------

    @property
    def is_on(self) -> bool:
        return bool(self._cond.get("pwr_on"))
