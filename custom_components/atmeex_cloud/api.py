# ... оставь свой импорт/класс как есть выше ...
import logging
_LOGGER = logging.getLogger(__name__)

class AtmeexApi:
    # ... остальное без изменений ...

    async def set_params(self, device_id, params: dict):
        url = f"{self.base_url}/devices/{device_id}/params"
        async with async_timeout.timeout(20):
            async with self._session.put(url, json=params) as resp:
                txt = await resp.text()
                if resp.status >= 400:
                    raise ApiError(f"PUT /devices/{device_id}/params failed {resp.status}: {txt[:200]}")

    async def set_power(self, device_id, on: bool):
        await self.set_params(device_id, {"u_pwr_on": bool(on)})

    async def set_fan_speed(self, device_id, speed: int):
        await self.set_params(device_id, {"u_fan_speed": int(speed)})

    async def set_target_temperature(self, device_id, temperature_c: float):
        await self.set_params(device_id, {"u_temp_room": int(round(temperature_c * 10))})

    # ------ NEW: humidification (0..3) ------
    async def set_humid_stage(self, device_id: int | str, stage: int) -> None:
        """0 = off, 1..3 = ступени увлажнения"""
        st = max(0, min(3, int(stage)))
        await self.set_params(device_id, {"u_hum_stg": st})

    # ------ NEW: brizer mode via damper position (0..3) ------
    async def set_brizer_mode(self, device_id: int | str, damp_pos: int) -> None:
        """
        Маппинг:
          0 = приточная вентиляция
          1 = рециркуляция
          2 = смешанный режим
          3 = приточный клапан
        """
        pos = max(0, min(3, int(damp_pos)))
        await self.set_params(device_id, {"u_damp_pos": pos})
