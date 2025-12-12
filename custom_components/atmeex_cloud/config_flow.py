from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .api import AtmeexApi, ApiError

_LOGGER = logging.getLogger(__name__)


async def _test_credentials(
    hass: HomeAssistant,
    email: str,
    password: str,
) -> None:
    """Пробная авторизация и запрос устройств для проверки логина/пароля."""
    session = async_get_clientsession(hass)
    api = AtmeexApi(session, email, password)

    # Минимальная проверка: логинимся и получаем список устройств.
    # В твоём AtmeexApi login обычно вызывается внутри get_devices,
    # поэтому здесь достаточно одного вызова.
    devices = await api.get_devices()
    if devices is None:
        raise ApiError("Empty devices list")


class AtmeexCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Мастер настройки интеграции Atmeex Cloud."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Первый шаг мастера — ввод email/пароля."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]

            # делаем unique_id по email, чтобы не создать дубликат
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()

            try:
                await _test_credentials(self.hass, email, password)
            except ApiError as err:
                _LOGGER.error("Error communicating with Atmeex API: %s", err)
                # тут можно было бы различать invalid_auth / cannot_connect,
                # но сервер часто отдаёт 500, поэтому делаем один тип ошибки
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Atmeex auth")
                errors["base"] = "unknown"
            else:
                # всё ок – создаём запись конфига и сохраняем email/пароль
                return self.async_create_entry(
                    title=email,
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )