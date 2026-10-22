"""Global pytest configuration and Home Assistant mocks for offline testing."""

import sys
from unittest.mock import MagicMock
from enum import StrEnum


class MockEntityCategory(StrEnum):
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"


class MockBaseEntity:
    pass


class MockCoordinatorEntity(MockBaseEntity):
    def __init__(self, coordinator=None):
        self.coordinator = coordinator

    def __class_getitem__(cls, item):
        return cls


class MockButtonEntity(MockBaseEntity):
    pass


class MockSensorEntity(MockBaseEntity):
    pass


class MockHomeAssistantError(Exception):
    pass


modules_to_mock = [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.exceptions",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.components.button",
    "homeassistant.components.recorder",
    "homeassistant.components.recorder.const",
    "homeassistant.components.recorder.models",
    "homeassistant.components.recorder.statistics",
    "homeassistant.helpers",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.data_entry_flow",
]

for mod in modules_to_mock:
    sys.modules[mod] = MagicMock()

sys.modules["homeassistant"].config_entries = sys.modules["homeassistant.config_entries"]
sys.modules["homeassistant"].const = sys.modules["homeassistant.const"]
sys.modules["homeassistant"].core = sys.modules["homeassistant.core"]
sys.modules["homeassistant"].exceptions = sys.modules["homeassistant.exceptions"]
sys.modules["homeassistant"].components = sys.modules["homeassistant.components"]
sys.modules["homeassistant"].helpers = sys.modules["homeassistant.helpers"]
sys.modules["homeassistant"].data_entry_flow = sys.modules["homeassistant.data_entry_flow"]

sys.modules["homeassistant.exceptions"].HomeAssistantError = MockHomeAssistantError
sys.modules["homeassistant.const"].EntityCategory = MockEntityCategory
sys.modules["homeassistant.components.button"].ButtonEntity = MockButtonEntity
sys.modules["homeassistant.components.sensor"].SensorEntity = MockSensorEntity
sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = MockCoordinatorEntity
sys.modules["homeassistant.components.recorder.const"].DOMAIN = "recorder"


class MockOptionsFlow:
    """Mock for Home Assistant OptionsFlow base class."""

    def __init__(self, *args, **kwargs):
        pass

    def async_show_form(self, step_id=None, data_schema=None, errors=None, description_placeholders=None):
        return {"type": "form", "step_id": step_id, "data_schema": data_schema}

    def async_create_entry(self, title="", data=None):
        return {"type": "create_entry", "title": title, "data": data}


sys.modules["homeassistant.config_entries"].OptionsFlow = MockOptionsFlow
sys.modules["homeassistant"].config_entries.OptionsFlow = MockOptionsFlow
