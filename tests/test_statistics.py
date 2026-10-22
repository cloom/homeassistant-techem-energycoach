"""Test historical statistics data preparation."""

from datetime import datetime, timezone
from custom_components.techem_energycoach.client import TechemData, MeterReading


def test_statistics_entries_calculation():
    """Verify that monthly historical readings compute chronological timestamps and cumulative sums correctly."""
    meter = MeterReading(
        meter_id="60828705",
        meter_type="eau_chaude",
        location="Indéfini",
        current_month="2026/09",
        current_value_raw=6.0,
        current_value_m3_or_units=0.6,
        exercise_total_raw=435.0,
        exercise_total_m3_or_units=43.5,
        monthly_consumption={
            "2025/10": 26.0,
            "2025/11": 30.0,
            "2025/12": 39.0,
            "2026/01": 42.0,
        },
    )

    data = TechemData(building_info="Test building", meters={"eau_chaude": meter})

    sorted_months = sorted(meter.monthly_consumption.keys())
    assert sorted_months == ["2025/10", "2025/11", "2025/12", "2026/01"]

    cumulative_sum = 0.0
    entries = []
    for month_str in sorted_months:
        val_raw = meter.monthly_consumption[month_str]
        val_m3 = round(val_raw * 0.1, 3)
        cumulative_sum += val_m3
        dt = datetime.strptime(month_str, "%Y/%m").replace(day=1, tzinfo=timezone.utc)
        entries.append((dt, val_m3, round(cumulative_sum, 3)))

    # Oct 2025: 26 hL -> 2.6 m3, sum = 2.6
    assert entries[0] == (datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc), 2.6, 2.6)
    # Nov 2025: 30 hL -> 3.0 m3, sum = 5.6
    assert entries[1] == (datetime(2025, 11, 1, 0, 0, tzinfo=timezone.utc), 3.0, 5.6)
    # Dec 2025: 39 hL -> 3.9 m3, sum = 9.5
    assert entries[2] == (datetime(2025, 12, 1, 0, 0, tzinfo=timezone.utc), 3.9, 9.5)
    # Jan 2026: 42 hL -> 4.2 m3, sum = 13.7
    assert entries[3] == (datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), 4.2, 13.7)


def test_monthly_reduction_continuity():
    """Verify that cumulative sums produce positive, non-negative monthly deltas in Energy Dashboard calculation."""
    monthly_sums = [
        ("2025-11", 3.0),
        ("2025-12", 6.9),
        ("2026-01", 11.1),
        ("2026-02", 14.6),
        ("2026-03", 19.1),
        ("2026-04", 22.2),
        ("2026-05", 26.6),
        ("2026-06", 31.9),
        ("2026-07", 36.7),
        ("2026-08", 40.3),
        ("2026-09", 45.9),
        ("2026-10", 49.4),
    ]

    prev_sum = 0.0
    changes = []
    for month, cum_sum in monthly_sums:
        delta = round(cum_sum - prev_sum, 3)
        assert delta > 0, f"Negative or zero delta in month {month}: {delta}"
        changes.append((month, delta))
        prev_sum = cum_sum

    # October delta should be +3.5 m3, not negative
    assert changes[-1] == ("2026-10", 3.5)
    assert len(changes) == 12

