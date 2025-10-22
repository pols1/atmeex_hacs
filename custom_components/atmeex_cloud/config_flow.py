from homeassistant import config_entries
import voluptuous as vol
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from .api import AtmeexApi, ApiError
from .const import DOMAIN

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_EMAIL): str,
    vol.Required(CONF_PASSWORD): str,
})

class AtmeexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            api = AtmeexApi()
            await api.async_init()
            try:
                await api.login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
                await api.get_devices()
            except ApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=user_input[CONF_EMAIL], data=user_input)
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)
