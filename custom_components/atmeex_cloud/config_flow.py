from __future__ import annotations

from typing import Any

import voluptuous as vol
from aiohttp import ClientSession
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN
from .api import AtmeexApi, ApiError

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("email"): str,
        vol.Required("password"): str,
    }
)


class AtmeexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Atmeex Cloud."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input["email"]
            password = user_input["password"]

            # чтобы не создавать дублирующиеся записи
            await self.async_set_unique_id(email)
            self._abort_if_unique_id_configured()

            session: ClientSession = aiohttp_client.async_get_clientsession(self.hass)
            api = AtmeexApi(session=session, email=email, password=password)

            try:
                # просто пробуем залогиниться и получить устройства
                await api.sign_in()
                await api.get_devices()
            except ApiError:
                errors["base"] = "auth_failed"
            else:
                return self.async_create_entry(
                    title=f"Atmeex ({email})",
                    data={
                        "email": email,
                        "password": password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
