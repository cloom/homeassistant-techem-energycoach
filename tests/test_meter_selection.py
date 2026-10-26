"""Test meter selection filtering and button guard attributes."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.const import EntityCategory

from custom_components.techem_energycoach.client import TechemData, MeterReading
from custom_components.techem_energycoach.historical_import import async_import_techem_history
from custom_components.techem_energycoach.button import TechemImportHistoryButton


@pytest.mark.asyncio
async def test_historical_import_skips_disabled_meters():
    """Verify that async_import_techem_history respects enabled_meters."""
    meter_hot = MeterReading(
        meter_id="1111",
        meter_type="eau_chaude",
        location="Cuisine",
        current_month="2026/09",
        current_value_raw=10.0,
        current_value_m3_or_units=1.0,
        exercise_total_raw=100.0,
        exercise_total_m3_or_units=10.0,
        monthly_consumption={"2026/08": 10.0},
    )
    meter_cold = MeterReading(
        meter_id="2222",
        meter_type="eau_froide",
        location="Cuisine",
        current_month="2026/09",
        current_value_raw=20.0,
        current_value_m3_or_units=2.0,
        exercise_total_raw=200.0,
        exercise_total_m3_or_units=20.0,
        monthly_consumption={"2026/08": 20.0},
    )
    data = TechemData(
        building_info="Test",
        meters={"eau_chaude": meter_hot, "eau_froide": meter_cold},
    )

    hass = MagicMock()
    hass.config.components = ["recorder"]

    # Only enable hot water
    counts = await async_import_techem_history(
        hass=hass,
        data=data,
        include_annual_history=False,
        enabled_meters=["eau_chaude"],
    )

    # Cold water should be skipped completely
    assert "sensor.techem_1111_eau_chaude" in counts
    assert "sensor.techem_2222_eau_froide" not in counts


def test_button_attributes_and_defaults():
    """Verify TechemImportHistoryButton configuration and guard attributes."""
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {"username": "test_user"}
    entry.options = {}

    button = TechemImportHistoryButton(coordinator, entry)

    # Check that button is enabled by default and categorized as CONFIG
    assert button._attr_entity_registry_enabled_default is True
    assert button._attr_entity_category == EntityCategory.CONFIG

    # Check initial extra_state_attributes (bilingual)
    attrs = button.extra_state_attributes
    assert attrs["status"] == "never_run"
    assert attrs["statut"] == "never_run"
    assert attrs["last_import"] is None
    assert attrs["dernier_import"] is None
    assert attrs["imported_statistics_count"] is None
    assert attrs["nb_statistiques_importees"] is None
