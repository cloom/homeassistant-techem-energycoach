"""Unit tests for multi-year history extraction and transition year de-duplication."""

from datetime import datetime, timezone
import pytest

from custom_components.techem_energycoach.client import MeterReading
from custom_components.techem_energycoach.const import (
    METER_TYPE_HOT_WATER,
    METER_TYPE_COLD_WATER,
    METER_TYPE_HEAT,
    GRANULARITY_BIMONTHLY,
    GRANULARITY_MONTHLY,
)
from custom_components.techem_energycoach.historical_import import (
    build_meter_statistics_timeline,
)

SAMPLE_ANNUAL_HISTORY = [
    {
        "date": "03/09/2026",
        "type": "Derniers Relevés",
        "eau_chaude": "0",
        "eau_froide": "0",
        "chauffage": "0",
        "repartiteur": "0",
    },
    {
        "date": "31/12/2025",
        "type": "Relevé rép & eau",
        "eau_chaude": "25 202",
        "eau_froide": "42 101",
        "chauffage": "345 819",
        "repartiteur": "0",
    },
    {
        "date": "31/12/2024",
        "type": "Relevé rép & eau",
        "eau_chaude": "24 932",
        "eau_froide": "39 193",
        "chauffage": "335 647",
        "repartiteur": "0",
    },
    {
        "date": "31/12/2023",
        "type": "Relevé rép & eau",
        "eau_chaude": "22 001",
        "eau_froide": "38 917",
        "chauffage": "335 540",
        "repartiteur": "0",
    },
    {
        "date": "31/12/2022",
        "type": "Relevé rép & eau",
        "eau_chaude": "22 285",
        "eau_froide": "41 744",
        "chauffage": "327 294",
        "repartiteur": "0",
    },
    {
        "date": "31/12/2021",
        "type": "Relevé rép & eau",
        "eau_chaude": "24 027",
        "eau_froide": "39 147",
        "chauffage": "428 354",
        "repartiteur": "0",
    },
    {
        "date": "31/12/2020",
        "type": "Relevé rép & eau",
        "eau_chaude": "24 597",
        "eau_froide": "40 861",
        "chauffage": "323 589",
        "repartiteur": "0",
    },
    {
        "date": "31/12/2019",
        "type": "Relevé rép & eau",
        "eau_chaude": "27 619",
        "eau_froide": "39 809",
        "chauffage": "303 797",
        "repartiteur": "0",
    },
    {
        "date": "31/12/2018",
        "type": "Relevé rép & eau",
        "eau_chaude": "0",
        "eau_froide": "0",
        "chauffage": "0",
        "repartiteur": "0",
    },
]


def test_transition_year_no_extrapolation_hot_water():
    """Verify that transition year 2025 contains only real measured entries without artificial remainder."""
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
            "2025/11/15": 20.0,  # 2.0 m3
            "2025/11/30": 16.0,  # 1.6 m3
            "2025/12/15": 27.0,  # 2.7 m3
            "2025/12/31": 16.0,  # 1.6 m3
            "2026/01/15": 20.0,  # 2.0 m3
        },
    )

    # 2025 bimonthly sum = 2.0 + 1.6 + 2.7 + 1.6 = 7.9 m3
    # ZERO extrapolation: no artificial remainder is injected into 2025!

    timeline = build_meter_statistics_timeline(
        m_type=METER_TYPE_HOT_WATER,
        meter=meter,
        annual_history=SAMPLE_ANNUAL_HISTORY,
        include_annual_history=True,
        granularity=GRANULARITY_BIMONTHLY,
    )

    # Check entries per year
    by_year: dict[int, float] = {}
    for dt, delta, cum_sum in timeline:
        by_year[dt.year] = round(by_year.get(dt.year, 0.0) + delta, 3)

    assert by_year[2019] == 27.619
    assert by_year[2020] == 24.597
    assert by_year[2021] == 24.027
    assert by_year[2022] == 22.285
    assert by_year[2023] == 22.001
    assert by_year[2024] == 24.932
    # Only real bimonthly entries in 2025 (no artificial extrapolation remainder!)
    assert by_year[2025] == 7.9
    # 2026 recent
    assert by_year[2026] == 2.0


def test_certified_apartment_annual_history():
    """Verify that apartment_annual_history uses certified annual figures directly without scaling."""
    meter = MeterReading(
        meter_id="60828705",
        meter_type=METER_TYPE_HOT_WATER,
        location="Indéfini",
        current_month="2026/09",
        current_value_raw=6.0,
        current_value_m3_or_units=0.6,
        exercise_total_raw=435.0,
        exercise_total_m3_or_units=43.5,
        monthly_consumption={"2026/01": 42.0},  # 4.2 m3 in 2026
    )

    apt_history = {
        "eau_chaude": {
            2021: 17.3,
            2022: 13.1,
            2023: 12.9,
            2024: 21.2,
            2025: 29.7,
        }
    }

    timeline = build_meter_statistics_timeline(
        m_type=METER_TYPE_HOT_WATER,
        meter=meter,
        apartment_annual_history=apt_history,
        include_annual_history=True,
        granularity=GRANULARITY_MONTHLY,
    )

    by_year: dict[int, float] = {}
    for dt, delta, cum_sum in timeline:
        by_year[dt.year] = round(by_year.get(dt.year, 0.0) + delta, 3)

    assert by_year[2021] == 17.3
    assert by_year[2022] == 13.1
    assert by_year[2023] == 12.9
    assert by_year[2024] == 21.2
    assert by_year[2025] == 29.7
    assert by_year[2026] == 4.2


def test_monotonic_cumulative_sums():
    """Verify that all deltas in the timeline are positive and cumulative sums strictly increase."""
    meter = MeterReading(
        meter_id="82817599",
        meter_type=METER_TYPE_COLD_WATER,
        location="Indéfini",
        current_month="2026/10",
        current_value_raw=8.0,
        current_value_m3_or_units=0.8,
        exercise_total_raw=580.0,
        exercise_total_m3_or_units=58.0,
        bimonthly_consumption={
            "2025/11/15": 20.0,
            "2025/11/30": 16.0,
            "2025/12/15": 27.0,
            "2025/12/31": 16.0,
        },
    )

    timeline = build_meter_statistics_timeline(
        m_type=METER_TYPE_COLD_WATER,
        meter=meter,
        annual_history=SAMPLE_ANNUAL_HISTORY,
        include_annual_history=True,
    )

    prev_sum = 0.0
    for dt, delta, cum_sum in timeline:
        assert delta > 0, f"Delta must be positive at {dt}: {delta}"
        assert cum_sum > prev_sum, f"Cumulative sum must strictly increase at {dt}: {cum_sum} <= {prev_sum}"
        assert round(prev_sum + delta, 3) == cum_sum
        prev_sum = cum_sum


def test_disable_annual_history():
    """Verify that when include_annual_history is False, no past years or transition remainder are added."""
    meter = MeterReading(
        meter_id="60828705",
        meter_type=METER_TYPE_HOT_WATER,
        location="Indéfini",
        current_month="2026/10",
        current_value_raw=8.0,
        current_value_m3_or_units=0.8,
        exercise_total_raw=494.0,
        exercise_total_m3_or_units=49.4,
        monthly_consumption={"2026/08": 36.0, "2026/09": 6.0},
    )

    timeline = build_meter_statistics_timeline(
        m_type=METER_TYPE_HOT_WATER,
        meter=meter,
        annual_history=SAMPLE_ANNUAL_HISTORY,
        include_annual_history=False,
        granularity=GRANULARITY_MONTHLY,
    )

    years = {dt.year for dt, _, _ in timeline}
    assert years == {2026}
    assert len(timeline) == 2
