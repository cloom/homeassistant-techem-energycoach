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
    apartment_annual_history: dict[str, dict[int, float]] | None = None,
    annual_history: list[dict[str, Any]] | None = None,
    include_annual_history: bool = True,
    granularity: str = GRANULARITY_BIMONTHLY,
) -> list[tuple[datetime, float, float]]:
    """Build chronological statistics entries (start_dt, delta, cumulative_sum).

    Handles bimonthly/monthly granularity and multi-year certified annual statements.
    Ensures zero extrapolation: no artificial transition year remainders are generated.
    """
    is_water = m_type in (METER_TYPE_HOT_WATER, METER_TYPE_COLD_WATER)
    factor = 0.1 if is_water else 1.0

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

    # 2. Multi-year certified annual statements from occupant apartment décomptes
    annual_by_year: dict[int, float] = {}
    if include_annual_history:
        if apartment_annual_history and m_type in apartment_annual_history:
            annual_by_year = {
                y: round(v, 3) if is_water else round(v, 1)
                for y, v in apartment_annual_history[m_type].items()
                if v > 0
            }
        elif annual_history:
            # Fallback for mock data / test suites
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
                    val_f = float(clean_v)
                    # If legacy litrage format (> 500 for water), convert to m3
                    if is_water and val_f > 500:
                        val_f *= 0.001
                    if val_f > 0 and y not in annual_by_year:
                        annual_by_year[y] = round(val_f, 3) if is_water else round(val_f, 1)
                except ValueError:
                    continue

    full_entries: list[tuple[datetime, float]] = []
    if transition_year:
        # Closed past years strictly before transition year (at Dec 31st 23:00 UTC)
        for y, val in sorted(annual_by_year.items()):
            if y < transition_year:
                dt = datetime(y, 12, 31, 23, 0, tzinfo=timezone.utc)
                full_entries.append((dt, val))

        # ZERO EXTRAPOLATION:
        # We do NOT compute any estimated remainder for the transition year.
        # The transition year and ongoing periods are strictly covered by their
        # authentic, measured meter readings (recent_entries).
    elif annual_by_year:
        for y, val in sorted(annual_by_year.items()):
            dt = datetime(y, 12, 31, 23, 0, tzinfo=timezone.utc)
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
            apartment_annual_history=getattr(data, "apartment_annual_history", None),
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

        # Ensure short-term statistics and live sensor continuity:
        # 1. Seed StatisticsShortTerm with the final historical record so that
        # when Home Assistant's core sensor recorder starts compiling this sensor,
        # it starts its cumulative sum from timeline[-1].sum instead of 0.0.
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.db_schema import StatisticsShortTerm

            recorder_instance = get_instance(hass)
            recorder_instance.async_import_statistics(
                metadata,
                [stat_entries[-1]],
                StatisticsShortTerm,
            )
        except Exception as err:
            _LOGGER.debug("Could not seed short-term statistics for %s: %s", statistic_id, err)

        # 2. Check if the live sensor already compiled any records with sum == 0.0
        # (e.g. if the integration was already running before historical import was invoked).
        # If so, automatically adjust those records to eliminate the drop/negative consumption.
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period

            recorder_instance = get_instance(hass)
            final_cum_sum = (
                stat_entries[-1]["sum"]
                if isinstance(stat_entries[-1], dict)
                else stat_entries[-1].sum
            )
            last_dt = (
                stat_entries[-1]["start"]
                if isinstance(stat_entries[-1], dict)
                else stat_entries[-1].start
            )

            future_stats = await hass.async_add_executor_job(
                statistics_during_period,
                hass,
                last_dt,
                None,
                {statistic_id},
                "hour",
                None,
                {"sum"},
            )
            rows = future_stats.get(statistic_id, [])
            drop_start = None
            drop_sum = 0.0
            for r in rows:
                r_sum = r.get("sum")
                if r_sum is not None and r_sum < final_cum_sum - 1e-4:
                    drop_start = r.get("start")
                    drop_sum = r_sum
                    break

            if drop_start is not None:
                if isinstance(drop_start, (int, float)):
                    dt_drop = datetime.fromtimestamp(drop_start, tz=timezone.utc)
                else:
                    dt_drop = drop_start
                adj = round(final_cum_sum - drop_sum, 3) if is_water else round(final_cum_sum - drop_sum, 1)
                _LOGGER.info(
                    "Fixing statistical drop for %s at %s (sum=%s < %s): applying adjustment +%s %s",
                    statistic_id,
                    dt_drop,
                    drop_sum,
                    final_cum_sum,
                    adj,
                    unit,
                )
                recorder_instance.async_adjust_statistics(
                    statistic_id,
                    dt_drop,
                    adj,
                    unit,
                )
        except Exception as err:
            _LOGGER.debug("Could not check/adjust statistical continuity for %s: %s", statistic_id, err)

    return imported_counts

