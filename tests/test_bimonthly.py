"""Unit tests for semi-monthly (15-day / bimonthly) data parsing and timeline generation."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from custom_components.techem_energycoach.client import (
    TechemEnergyCoachClient,
    MeterReading,
)
from custom_components.techem_energycoach.const import (
    METER_TYPE_HOT_WATER,
    METER_TYPE_COLD_WATER,
    METER_TYPE_HEAT,
    GRANULARITY_BIMONTHLY,
)
from custom_components.techem_energycoach.historical_import import (
    build_meter_statistics_timeline,
)

BIMONTHLY_HTML_PATH = Path(__file__).parents[1] / "ha_test_config" / "bimensuel.html"


@pytest.mark.skipif(not BIMONTHLY_HTML_PATH.exists(), reason="Local HTML capture not present")
def test_parse_bimonthly_html():
    """Verify parsing of 24 semi-monthly periods from real Techem M43=3 response."""
    html_content = BIMONTHLY_HTML_PATH.read_text(encoding="utf-8")

    client = TechemEnergyCoachClient("dummy@example.com", "dummy_pass")
    result = client._parse_bimonthly_html(html_content)

    assert "eau_chaude" in result
    assert "eau_froide" in result
    assert "chauffage" in result

    hot_water = result["eau_chaude"]
    assert len(hot_water) == 24
    dates = list(hot_water.keys())
    assert dates[0] == "2025/11/15"
    assert dates[-1] == "2026/10/31"

    # Eau chaude quinzaines (in hL)
    assert hot_water["2025/11/15"] == 20.0
    assert hot_water["2025/11/30"] == 16.0
    assert hot_water["2026/10/15"] == 29.0
    assert hot_water["2026/10/31"] == 8.0

    # Chauffage quinzaines
    heat = result["chauffage"]
    assert len(heat) == 24
    assert heat["2025/11/15"] == 23.0
    assert heat["2025/11/30"] == 236.0


def test_bimonthly_timeline_timestamps_and_units():
    """Verify that 15-day quinzaines are assigned to day 1 and day 16 of the respective month."""
    meter = MeterReading(
        meter_id="60828705",
        meter_type=METER_TYPE_HOT_WATER,
        location="Indéfini",
        current_month="2026/10",
        current_value_raw=8.0,
        current_value_m3_or_units=0.8,
        exercise_total_raw=494.0,
        exercise_total_m3_or_units=49.4,
        bimonthly_consumption={
            "2025/11/15": 20.0,  # 1st quinzaine Nov 2025: 20 hL -> 2.0 m3
            "2025/11/30": 16.0,  # 2nd quinzaine Nov 2025: 16 hL -> 1.6 m3
            "2025/12/15": 27.0,  # 1st quinzaine Dec 2025: 27 hL -> 2.7 m3
            "2025/12/31": 16.0,  # 2nd quinzaine Dec 2025: 16 hL -> 1.6 m3
        },
    )

    timeline = build_meter_statistics_timeline(
        m_type=METER_TYPE_HOT_WATER,
        meter=meter,
        include_annual_history=False,
        granularity=GRANULARITY_BIMONTHLY,
    )

    assert len(timeline) == 4

    # Nov 1-15 -> 2025-11-01 00:00:00 UTC, delta = 2.0, cum_sum = 2.0
    assert timeline[0] == (
        datetime(2025, 11, 1, 0, 0, tzinfo=timezone.utc),
        2.0,
        2.0,
    )
    # Nov 16-30 -> 2025-11-16 00:00:00 UTC, delta = 1.6, cum_sum = 3.6
    assert timeline[1] == (
        datetime(2025, 11, 16, 0, 0, tzinfo=timezone.utc),
        1.6,
        3.6,
    )
    # Dec 1-15 -> 2025-12-01 00:00:00 UTC, delta = 2.7, cum_sum = 6.3
    assert timeline[2] == (
        datetime(2025, 12, 1, 0, 0, tzinfo=timezone.utc),
        2.7,
        6.3,
    )
    # Dec 16-31 -> 2025-12-16 00:00:00 UTC, delta = 1.6, cum_sum = 7.9
    assert timeline[3] == (
        datetime(2025, 12, 16, 0, 0, tzinfo=timezone.utc),
        1.6,
        7.9,
    )
