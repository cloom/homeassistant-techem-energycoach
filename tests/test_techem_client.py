"""Unit tests for Techem EnergyCoach client and parser."""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Mock homeassistant modules so custom_components package can be imported in any environment
mock_ha = MagicMock()
for mod in [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.exceptions",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.components.button",
    "homeassistant.components.recorder",
    "homeassistant.components.recorder.models",
    "homeassistant.components.recorder.statistics",
    "homeassistant.helpers",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.update_coordinator",
]:
    sys.modules[mod] = mock_ha

from custom_components.techem_energycoach.client import (
    TechemEnergyCoachClient,
    TechemData,
    TechemAuthError,
    TechemConnectionError,
)

SAMPLE_HTML_PATH = Path(__file__).parents[1] / "techem_data" / "r3_pure_requests.html"


@pytest.mark.skipif(not SAMPLE_HTML_PATH.exists(), reason="Local HTML capture not present")
def test_parse_sample_html():
    """Verify parsing of real Techem monthly response."""
    html_content = SAMPLE_HTML_PATH.read_text(encoding="utf-8")

    client = TechemEnergyCoachClient("dummy@example.com", "dummy_pass")
    data: TechemData = client._parse_monthly_page(html_content)

    assert data.building_info != ""
    assert "94272" in data.building_info
    assert "220" in data.building_info
    assert "Déconnexion" not in data.building_info
    assert data.building_info.startswith("Immeuble")

    # Meters verified
    assert "eau_chaude" in data.meters
    assert "eau_froide" in data.meters
    assert "chauffage" in data.meters

    # Eau chaude
    hot_water = data.meters["eau_chaude"]
    assert hot_water.meter_id == "60828705"
    assert hot_water.current_month == "2026/09"
    assert hot_water.current_value_raw == 6.0
    assert hot_water.current_value_m3_or_units == 0.6  # 6 hL = 0.6 m3
    assert hot_water.monthly_consumption["2025/10"] == 26.0
    assert hot_water.monthly_consumption["2026/08"] == 36.0

    # Eau froide
    cold_water = data.meters["eau_froide"]
    assert cold_water.meter_id == "82817599"
    assert cold_water.current_month == "2026/09"
    assert cold_water.current_value_raw == 8.0
    assert cold_water.current_value_m3_or_units == 0.8  # 8 hL = 0.8 m3
    assert cold_water.monthly_consumption["2025/10"] == 24.0
    assert cold_water.monthly_consumption["2026/07"] == 70.0

    # Chauffage
    heat = data.meters["chauffage"]
    assert heat.meter_id == "67659047"
    assert heat.current_month == "2026/09"
    assert heat.current_value_raw == 2.0
    assert heat.current_value_m3_or_units == 2.0  # units
    assert heat.monthly_consumption["2026/01"] == 552.0


def test_auth_failure():
    """Verify that bad credentials raise TechemAuthError."""
    client = TechemEnergyCoachClient("bad_user@example.com", "wrong_password")
    with pytest.raises(TechemAuthError):
        client.login()
