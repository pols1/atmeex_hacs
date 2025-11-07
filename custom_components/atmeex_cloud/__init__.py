from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import AtmeexApi
from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    try:
        return bool(int(v))
    except Exception:
        return bool(v)


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Склеить condition + settings → нормализованное состояние (+ online)."""
    cond = dict(item.get("condition") or {})
    st = dict(item.get("settings") or {})

    # Питание
    pwr_cond = cond.get("pwr_on")
    pwr = _to_bool(pwr_cond) if pwr_cond is not None else _to_bool(st.get("u_pwr_on"))

    # Скорость
    fan = cond.get("fan_speed")
    u_fan = st.get("u_fan_speed")
    if (fan is None or int(fan) == 0) and pwr and isinstance(u_fan, (int, float)) and int(u_fan) > 0:
        fan = int(u_fan)

    # Заслонка
    damp = cond.get("damp_pos")
    if damp is None and "u_damp_pos" in st:
        damp = st.get("u_damp_pos")

    # Цель температуры (деци-°C)
    u_temp = cond.get("u_temp_room")
    if u_temp is None and "u_temp_room" in st:
        u_temp = st.get("u_temp_room")

    # Увлажнение (ступень)
    hum_stg = cond.get("hum_stg")
    if hum_stg is None and "u_hum_stg" in st:
        hum_stg = st.get("u_hum_stg")

    out = dict(cond) if cond else {}
    if pwr is not None:
        out["pwr_on"] = bool(pwr)
    if fan is not None:
        try:
            out["fan_speed"] = int(fan)
        except Exception:
            pass
    if damp is not None:
        try:
            out["damp_pos"] = int(damp)
        except Exception:
            pass
    if hum_stg is not None:
        try:
            out["hum_stg"] = int(hum_stg)
        except Exception:
            pass
    if u_temp is not None:
        try:
            out["u_temp_room"] = int(u_temp)  # деци-°C
        except Exception:
            pass

    # meta
    out["online"] = bool(item.get("online", True))
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = AtmeexApi()
    await api.async_init()
    await api.login(entry.data["email"], entry.data["password"])

    last_ok: dict[str, Any] = {"devices": [], "states": {}}

    async def _fetch_devices_safely() -> List[dict]:
        """Пробуем основной список; если пусто/ошибка, делаем фолбэк."""
        try:
            devices = await api.get_devices()  # желательно ?with_condition=1 внутри api
            if isinstance(devices, list) and devices:
                return devices
        except Exception as e:
            _LOGGER.debug("get_devices failed: %s", e)

        # фолбэк: без condition
        try:
            devices = await api.get_devices(fallback=True)  # см. реализацию в api.py
        except Exception as e:
            _LOGGER.warning("fallback get_devices failed: %s", e)
            devices = []

        # дочитываем condition по каждому id
        result: List[dict] = []
        for d in devices:
            did = d.get("id")
            if did is None:
                result.append(d)
                continue
            try:
                full = await api.get_device(did)
                result.append(full if isinstance(full, dict) else d)
            except Exception as e:
                _LOGGER.debug("get_device(%s) failed: %s", did, e)
                result.append(d)
        return result

    async def _async_update_data() -> dict[str, Any]:
        """Плановый опрос: не теряем устройства между опросами."""
        nonlocal last_ok
        try:
            new_devices = await _fetch_devices_safely()

            # строим индекс по id
            new_by_id: Dict[str, dict] = {}
            for d in new_devices:
                did = d.get("id")
                if did is not None:
                    new_by_id[str(did)] = d

            # объединяем с прошлым снапшотом, чтобы не терять девайсы
            for d in last_ok.get("devices", []):
                did = d.get("id")
                if did is not None and str(did) not in new_by_id:
                    new_by_id[str(did)] = d

            devices_merged = list(new_by_id.values())

            # нормализация состояний
            states: dict[str, Any] = {}
            for d in devices_merged:
                did = d.get("id")
                if did is None:
                    continue
                states[str(did)] = _normalize_item(d)

            last_ok = {"devices": devices_merged, "states": states}
            return last_ok

        except Exception as err:
            _LOGGER.warning("Atmeex update failed: %s, using last state", err)
            return last_ok

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Atmeex Cloud",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=30),
    )

    await coordinator.async_config_entry_first_refresh()

    async def refresh_device(device_id: int | str) -> None:
        """Дочитать одно устройство и обновить координатор."""
        try:
            full = await api.get_device(device_id)
        except Exception as e:
            _LOGGER.warning("Failed to refresh device %s: %s", device_id, e)
            return

        cond_norm = _normalize_item(full)
        cur = coordinator.data or {"devices": [], "states": {}}
        devices = list(cur.get("devices", []))
        states = dict(cur.get("states", {}))

        # заменить/добавить устройство по id
        inserted = True
        for i, d in enumerate(devices):
            if d.get("id") == full.get("id"):
                devices[i] = full
                inserted = False
                break
        if inserted:
            devices.append(full)

        states[str(full.get("id"))] = cond_norm
        coordinator.async_set_updated_data({"devices": devices, "states": states})

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "refresh_device": refresh_device,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
