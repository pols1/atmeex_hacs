from __future__ import annotations
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .const import DOMAIN
from .api import AtmeexApi

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

class AtmeexConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api = AtmeexApi("https://api.iot.atmeex.com")
            await api.async_init()
            try:
                await api.login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
                # sanity-check запросим список устройств
                await api.get_devices()
            except Exception as exc:
                _LOGGER.exception("Login/devices failed")
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_EMAIL),
                    data=user_input,
                )
            finally:
                await api.async_close()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)
