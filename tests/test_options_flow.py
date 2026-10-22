"""Test Techem EnergyCoach Options Flow."""

import pytest
from unittest.mock import MagicMock

from custom_components.techem_energycoach.config_flow import OptionsFlowHandler
from custom_components.techem_energycoach.const import (
    DOMAIN,
    CONF_ENABLED_METERS,
    CONF_SCAN_INTERVAL,
    CONF_INCLUDE_ANNUAL_HISTORY,
    CONF_GRANULARITY,
    GRANULARITY_BIMONTHLY,
)


@pytest.mark.asyncio
async def test_options_flow_init():
    """Test options flow handler initialization and form rendering without AttributeError."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry_id"
    config_entry.options = {
        CONF_ENABLED_METERS: ["eau_chaude", "eau_froide"],
        CONF_SCAN_INTERVAL: 43200,
        CONF_INCLUDE_ANNUAL_HISTORY: True,
        CONF_GRANULARITY: GRANULARITY_BIMONTHLY,
    }
    config_entry.data = {}

    handler = OptionsFlowHandler(config_entry)

    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.data.meters = {}
    hass.data = {DOMAIN: {"test_entry_id": {"coordinator": coordinator}}}
    handler.hass = hass

    result = await handler.async_step_init()

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert "data_schema" in result


@pytest.mark.asyncio
async def test_options_flow_save():
    """Test saving options flow user input."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry_id"
    config_entry.options = {}
    config_entry.data = {}

    handler = OptionsFlowHandler(config_entry)
    hass = MagicMock()
    handler.hass = hass

    user_input = {
        CONF_ENABLED_METERS: ["eau_chaude"],
        CONF_SCAN_INTERVAL: 86400,
        CONF_INCLUDE_ANNUAL_HISTORY: True,
        CONF_GRANULARITY: GRANULARITY_BIMONTHLY,
    }

    result = await handler.async_step_init(user_input=user_input)
    assert result["type"] == "create_entry"
    assert result["data"] == user_input
