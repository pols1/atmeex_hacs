from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .api import AtmeexApi, ApiError

_LOGGER = logging.getLogger(__name__)

# Поля, которые показываем в мастере настройки
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("email"): str,
        vol.Required("password"): str,
    }
)


class AtmeexCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Atmeex Cloud integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Первый заход — отрисовываем форму логина
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
            )

        email: str = user_input["email"]
        password: str = user_input["password"]

        session = async_get_clientsession(self.hass)
        api = AtmeexApi(session, email, password)

        # Проверяем логин и заодно тестируем доступ к устройствам
        try:
            await api.authenticate()
            # Если хочешь — можно сразу проверить, что девайсы есть
            # devices = await api.get_devices()
            _LOGGER.debug("Atmeex auth succeeded for %s", email)
        except ApiError as err:
            _LOGGER.error("Atmeex auth failed: %s", err)
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": "auth_failed"},
            )
        except Exception as err:  # на всякий пожарный
            _LOGGER.exception("Unexpected error in Atmeex config flow: %s", err)
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": "unknown"},
            )

        # Делаем запись уникальной по email
        await self.async_set_unique_id(email)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Atmeex ({email})",
            data={
                "email": email,
                "password": password,
            },
        )
