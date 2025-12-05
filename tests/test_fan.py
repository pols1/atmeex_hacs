import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.atmeex_cloud.fan import AtmeexFan


def _make_fan_entity():
    cond = {
        "pwr_on": True,
        "fan_speed": 50,
    }
    coordinator = SimpleNamespace(
        data={"states": {"1": cond}},
        async_request_refresh=AsyncMock(),
    )
    api = MagicMock()
    api.set_fan_speed = AsyncMock()

    device = {"id": 1, "name": "Fan Device"}
    fan = AtmeexFan(coordinator, api, device)
    return fan, cond, api, coordinator


def test_fan_basic_properties():
    fan, cond, api, coord = _make_fan_entity()
    assert fan.condition == cond
    assert fan.is_on is True
    assert fan.percentage == 50


@pytest.mark.asyncio
async def test_fan_async_set_percentage():
    fan, cond, api, coord = _make_fan_entity()
    await fan.async_set_percentage(75)

    api.set_fan_speed.assert_awaited_once_with(1, 75)
    coord.async_request_refresh.assert_awaited_once()
