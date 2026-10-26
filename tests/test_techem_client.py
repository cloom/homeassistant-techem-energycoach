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
    client.session.get = MagicMock(return_value=MagicMock(
        status_code=200,
        text='<form action="/login_step2"></form>'
    ))
    client.session.post = MagicMock(return_value=MagicMock(
        status_code=200,
        text='<html><body>Nom d\'utilisateur ou mot de passe invalide</body></html>'
    ))
    with pytest.raises(TechemAuthError):
        client.login()


def test_server_outage():
    """Verify that portal server error / END_PAGE raises TechemConnectionError."""
    client = TechemEnergyCoachClient("user@example.com", "password")
    client.session.get = MagicMock(return_value=MagicMock(
        status_code=200,
        text='<html><title>END_PAGE</title><form action="/WEBENERGY_OCCUPANTS/END_PAGE/123"></form>Impossible to Connect On Server Data!</html>'
    ))
    with pytest.raises(TechemConnectionError):
        client.login()


def test_parse_apartment_annual_history_html():
    """Verify parsing of real apartment annual tables (A8, A16, A19)."""
    sample_post_login_html = """
    <html>
      <body>
        <table id="A8">
          <tr><td> 2024</td><td>212</td></tr>
          <tr><td> 2025</td><td>297</td></tr>
        </table>
        <table id="A16">
          <tr><td> 2024</td><td>288</td></tr>
          <tr><td> 2025</td><td>341</td></tr>
        </table>
        <script>
          clWDUtil.DeclareChamp("A19", void 0, void 0, void 0, WDGraphe, [
            {"m_tabValeur": [1745, 1940, 0]},
            {"m_tabValeur": [" 2024", " 2025", " 2026"]}
          ]);
        </script>
      </body>
    </html>
    """
    client = TechemEnergyCoachClient("user", "pass")
    history = client._parse_apartment_annual_history(sample_post_login_html)

    assert history["eau_chaude"] == {2024: 21.2, 2025: 29.7}
    assert history["eau_froide"] == {2024: 28.8, 2025: 34.1}
    assert history["chauffage"] == {2024: 1745.0, 2025: 1940.0}


def test_parse_apartment_annual_history_svg():
    """Verify parsing when SVG desc elements are present."""
    sample_svg_html = """
    <html>
      <body>
        <desc id="A12-desc-0">Total 2021=173 2022=131 2023=129</desc>
        <desc id="A13-desc-0">Total 2021=218 2022=184 2023=178</desc>
        <desc id="A19-desc-0">Total 2021=3009 2022=1551 2023=841</desc>
      </body>
    </html>
    """
    client = TechemEnergyCoachClient("user", "pass")
    history = client._parse_apartment_annual_history(sample_svg_html)

    assert history["eau_chaude"] == {2021: 17.3, 2022: 13.1, 2023: 12.9}
    assert history["eau_froide"] == {2021: 21.8, 2022: 18.4, 2023: 17.8}
    assert history["chauffage"] == {2021: 3009.0, 2022: 1551.0, 2023: 841.0}

