from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .api import AtmeexApi, ApiError

_LOGGER = logging.getLogger(__name__)

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

        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input["email"]
            password = user_input["password"]

            # создаём HTTP-сессию Home Assistant
            session = self.hass.helpers.aiohttp_client.async_get_clientsession()

            # НОВЫЙ конструктор: передаём session + email + password
            api = AtmeexApi(session, email, password)

            try:
                # проверяем, что логин / токен рабочие
                await api.authenticate()
                # Можно дополнительно дернуть устройства, если нужно:
                # await api.get_devices()

            except ApiError as err:
                _LOGGER.warning("Atmeex auth failed: %s", err)
                errors["base"] = "auth"

            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error during Atmeex auth: %s", err)
                errors["base"] = "unknown"

            else:
                # успех — сохраняем конфиг
                await api.close()

                # уникальный ID — по e-mail
                await self.async_set_unique_id(email)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=email,
                    data={
                        "email": email,
                        "password": password,
                    },
                )

        # первый заход или есть ошибки — показываем форму
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
