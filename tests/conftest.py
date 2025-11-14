import pytest
from types import SimpleNamespace


class DummyCoordinator:
    """Минимальный координатор, совместимый с CoordinatorEntity."""

    def __init__(self, data: dict | None = None):
        self.data = data or {}
        self.last_update_success = True
        self._listeners = []
        self.refresh_called = False

    def async_add_listener(self, listener):
        self._listeners.append(listener)
        # возвращаем функцию отписки
        def _remove():
            if listener in self._listeners:
                self._listeners.remove(listener)
        return _remove

    def async_remove_listener(self, listener):
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def async_request_refresh(self):
        self.refresh_called = True

    def async_set_updated_data(self, data: dict):
        self.data = data


@pytest.fixture
def dummy_coordinator():
    return DummyCoordinator()


@pytest.fixture
def hass_stub():
    """Простейший hass для тестов без настоящего Home Assistant."""
    return SimpleNamespace(
        data={},
        config_entries=SimpleNamespace(
            async_forward_entry_setups=None,
            async_unload_platforms=None,
        ),
    )
