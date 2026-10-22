"""Sensor platform for Techem EnergyCoach."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import MeterReading
from .const import (
    DOMAIN,
    METER_TYPE_HOT_WATER,
    METER_TYPE_COLD_WATER,
    METER_TYPE_HEAT,
    CONF_ENABLED_METERS,
)
from .coordinator import TechemCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Techem sensors based on a config entry."""
    coordinator: TechemCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    enabled_meters = entry.options.get(
        CONF_ENABLED_METERS,
        entry.data.get(CONF_ENABLED_METERS, None),
    )

    entities: list[TechemMeterSensor] = []
    if coordinator.data and coordinator.data.meters:
        for m_type, meter in coordinator.data.meters.items():
            if enabled_meters is not None and m_type not in enabled_meters:
                _LOGGER.debug("Techem meter skipped (not enabled): %s", m_type)
                continue
            entities.append(TechemMeterSensor(coordinator, entry, meter, m_type))

    async_add_entities(entities)


class TechemMeterSensor(CoordinatorEntity[TechemCoordinator], SensorEntity):
    """Sensor representing a Techem meter's consumption."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TechemCoordinator,
        entry: ConfigEntry,
        meter: MeterReading,
        meter_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self.meter_type = meter_type
        self.meter_id = meter.meter_id

        self._attr_unique_id = f"techem_{self.meter_id}_{meter_type}"
        self.entity_id = f"sensor.techem_{self.meter_id}_{meter_type}"
        self._attr_translation_key = meter_type

        # Labels & Device Classes
        if meter_type == METER_TYPE_HOT_WATER:
            self._attr_name = "Eau Chaude"
            self._attr_device_class = SensorDeviceClass.WATER
            self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
            self._attr_icon = "mdi:water-boiler"
        elif meter_type == METER_TYPE_COLD_WATER:
            self._attr_name = "Eau Froide"
            self._attr_device_class = SensorDeviceClass.WATER
            self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
            self._attr_icon = "mdi:water"
        elif meter_type == METER_TYPE_HEAT:
            self._attr_name = "Chauffage"
            self._attr_native_unit_of_measurement = "units"
            self._attr_icon = "mdi:radiator"
        else:
            self._attr_name = meter_type.replace("_", " ").title()
            self._attr_icon = "mdi:counter"

        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def meter(self) -> MeterReading | None:
        """Return the current meter reading."""
        if not self.coordinator.data or not self.coordinator.data.meters:
            return None
        return self.coordinator.data.meters.get(self.meter_type)

    @property
    def native_value(self) -> float | None:
        """Return the current month's cumulative consumption."""
        m = self.meter
        if m is None:
            return None
        return m.current_value_m3_or_units

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        m = self.meter
        if m is None:
            return {}
        return {
            "meter_id": m.meter_id,
            "meter_type": m.meter_type,
            "location": m.location,
            "current_month": m.current_month,
            "current_month_raw": m.current_value_raw,
            "exercise_total": m.exercise_total_m3_or_units,
            "exercise_total_raw": m.exercise_total_raw,
            "monthly_history": m.monthly_consumption,
            "bimonthly_history": m.bimonthly_consumption,
            # Backward-compatible French aliases
            "compteur_id": m.meter_id,
            "type_compteur": m.meter_type,
            "localisation": m.location,
            "mois_en_cours": m.current_month,
            "consommation_mois_brute": m.current_value_raw,
            "total_exercice": m.exercise_total_m3_or_units,
            "total_exercice_brut": m.exercise_total_raw,
            "historique_mensuel": m.monthly_consumption,
            "historique_bimensuel": m.bimonthly_consumption,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the meter."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=f"Techem EnergyCoach ({self.entry.data.get('username', 'Occupant')})",
            manufacturer="Techem",
            model="EnergyCoach WebDev",
            suggested_area="Apartment",
        )
