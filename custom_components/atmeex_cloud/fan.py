from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN

async def async_setup_entry(hass, config_entry: ConfigEntry, async_add_entities):
    # Пока без fan-сущностей; добавим после уточнения API.
    return
