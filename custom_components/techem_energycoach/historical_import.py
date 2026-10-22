"""Utility to import Techem historical consumption into Home Assistant recorder statistics."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .client import MeterReading, TechemData
from .const import (
    METER_TYPE_HOT_WATER,
    METER_TYPE_COLD_WATER,
    METER_TYPE_HEAT,
    GRANULARITY_BIMONTHLY,
    GRANULARITY_MONTHLY,
)

_LOGGER = logging.getLogger(__name__)


def build_meter_statistics_timeline(
    m_type: str,
    meter: MeterReading,
    annual_history: list[dict[str, Any]] | None = None,
    include_annual_history: bool = True,
    granularity: str = GRANULARITY_BIMONTHLY,
) -> list[tuple[datetime, float, float]]:
    """Build chronological statistics entries (start_dt, delta, cumulative_sum).

    Handles bimonthly/monthly granularity and multi-year annual statement de-duplication.
    """
    is_water = m_type in (METER_TYPE_HOT_WATER, METER_TYPE_COLD_WATER)
    factor = 0.1 if is_water else 1.0
    annual_factor = 0.001 if is_water else 1.0

    recent_entries: list[tuple[datetime, float]] = []
    covered_months: set[tuple[int, int]] = set()

    # 1. Semi-monthly (15-day) quinzaines if requested and available
    if granularity == GRANULARITY_BIMONTHLY and meter.bimonthly_consumption:
        for dt_str, val in meter.bimonthly_consumption.items():
            try:
                dt = datetime.strptime(dt_str, "%Y/%m/%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            start_day = 1 if dt.day <= 15 else 16
            start_dt = dt.replace(day=start_day, hour=0, minute=0, second=0, microsecond=0)
            val_converted = round(val * factor, 3) if is_water else float(val)
            recent_entries.append((start_dt, val_converted))
            covered_months.add((dt.year, dt.month))

        # Check if any month in monthly_consumption is not covered by bimonthly
        for m_str, val in meter.monthly_consumption.items():
            try:
                dt = datetime.strptime(m_str, "%Y/%m").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if (dt.year, dt.month) not in covered_months:
                start_dt = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                val_converted = round(val * factor, 3) if is_water else float(val)
                recent_entries.append((start_dt, val_converted))
    elif meter.monthly_consumption:
        for m_str, val in meter.monthly_consumption.items():
            try:
                dt = datetime.strptime(m_str, "%Y/%m").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            start_dt = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            val_converted = round(val * factor, 3) if is_water else float(val)
            recent_entries.append((start_dt, val_converted))

    recent_entries.sort(key=lambda x: x[0])
    earliest_recent_dt = recent_entries[0][0] if recent_entries else None
    transition_year = earliest_recent_dt.year if earliest_recent_dt else None

    # 2. Multi-year annual statements from HISINDEX
    annual_by_year: dict[int, float] = {}
    if include_annual_history and annual_history:
        for row in annual_history:
            d_str = row.get("date", "")
            if not re.match(r"^\d{2}/\d{2}/\d{4}$", d_str):
                continue
            try:
                y = int(d_str.split("/")[2])
            except ValueError:
                continue
            val_str = row.get(m_type, "0")
            clean_v = re.sub(r"[^\d.]", "", str(val_str).replace(",", "."))
            try:
                val_f = float(clean_v) * annual_factor
                if val_f > 0 and y not in annual_by_year:
                    annual_by_year[y] = round(val_f, 3) if is_water else round(val_f, 1)
            except ValueError:
                continue

    full_entries: list[tuple[datetime, float]] = []
    if transition_year:
        # A. Past years before transition year
        for y, val in sorted(annual_by_year.items()):
            if y < transition_year:
                dt = datetime(y, 12, 1, 0, 0, tzinfo=timezone.utc)
                full_entries.append((dt, val))

        # B. Transition year remainder (Jan-Oct before rolling window)
        if transition_year in annual_by_year:
            annual_val = annual_by_year[transition_year]
            recent_transition_sum = sum(
                v for dt, v in recent_entries if dt.year == transition_year
            )
            rem = round(annual_val - recent_transition_sum, 3) if is_water else round(annual_val - recent_transition_sum, 1)
            if rem > 0:
                if earliest_recent_dt.day == 1:
                    prev_month = earliest_recent_dt.replace(day=1) - timedelta(days=1)
                    rem_dt = prev_month.replace(day=16, hour=0, minute=0, second=0, microsecond=0)
                else:
                    rem_dt = earliest_recent_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                full_entries.append((rem_dt, rem))
    elif annual_by_year:
        for y, val in sorted(annual_by_year.items()):
            dt = datetime(y, 12, 1, 0, 0, tzinfo=timezone.utc)
            full_entries.append((dt, val))

    full_entries.extend(recent_entries)
    full_entries.sort(key=lambda x: x[0])

    # 3. Compute monotonic cumulative sum
    timeline: list[tuple[datetime, float, float]] = []
    cumulative_sum = 0.0
    for dt, delta in full_entries:
        cumulative_sum += delta
        timeline.append((
            dt,
            delta,
            round(cumulative_sum, 3) if is_water else round(cumulative_sum, 1),
        ))

    return timeline


async def async_import_techem_history(
    hass: HomeAssistant,
    data: TechemData,
    include_annual_history: bool = True,
    granularity: str = GRANULARITY_BIMONTHLY,
    enabled_meters: list[str] | None = None,
) -> dict[str, int]:
    """Import historical consumption into long-term statistics for the Energy Dashboard."""
    # Check if recorder is loaded
    if "recorder" not in hass.config.components:
        raise HomeAssistantError("The 'recorder' integration must be enabled to import statistics.")

    try:
        from homeassistant.components.recorder.const import DOMAIN as RECORDER_DOMAIN
        from homeassistant.components.recorder.models import StatisticData
        from homeassistant.components.recorder.statistics import async_import_statistics
        try:
            from homeassistant.components.recorder.models import StatisticMeanType
        except ImportError:
            StatisticMeanType = None  # type: ignore[assignment]
    except ImportError as err:
        raise HomeAssistantError(f"Recorder API unavailable: {err}") from err

    imported_counts: dict[str, int] = {}

    for m_type, meter in data.meters.items():
        if enabled_meters is not None and m_type not in enabled_meters:
            _LOGGER.info("Historical import skipped for disabled meter: %s", m_type)
            continue

        timeline = build_meter_statistics_timeline(
            m_type=m_type,
            meter=meter,
            annual_history=data.annual_history,
            include_annual_history=include_annual_history,
            granularity=granularity,
        )
        if not timeline:
            continue

        is_water = m_type in (METER_TYPE_HOT_WATER, METER_TYPE_COLD_WATER)
        unit = "m³" if is_water else "units"
        statistic_id = f"sensor.techem_{meter.meter_id}_{m_type}"
        stat_name = f"Techem {m_type.replace('_', ' ').title()}"

        metadata: dict[str, Any] = {
            "has_mean": False,
            "has_sum": True,
            "name": stat_name,
            "source": RECORDER_DOMAIN,
            "statistic_id": statistic_id,
            "unit_of_measurement": unit,
            "unit_class": "volume" if is_water else None,
        }

        if StatisticMeanType is not None:
            metadata["mean_type"] = StatisticMeanType.NONE

        stat_entries = [
            StatisticData(start=dt, state=delta, sum=cum_sum)
            for dt, delta, cum_sum in timeline
        ]

        _LOGGER.info(
            "Importing %d historical statistics for %s",
            len(stat_entries),
            statistic_id,
        )
        async_import_statistics(hass, metadata, stat_entries)  # type: ignore[arg-type]
        imported_counts[statistic_id] = len(stat_entries)

    return imported_counts

