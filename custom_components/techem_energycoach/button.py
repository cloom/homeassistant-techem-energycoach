"""Button platform for Techem EnergyCoach."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_INCLUDE_ANNUAL_HISTORY,
    DEFAULT_INCLUDE_ANNUAL_HISTORY,
    CONF_GRANULARITY,
    GRANULARITY_BIMONTHLY,
    CONF_ENABLED_METERS,
)
from .coordinator import TechemCoordinator
from .historical_import import async_import_techem_history

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Techem button entities."""
    coordinator: TechemCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([TechemImportHistoryButton(coordinator, entry)])


class TechemImportHistoryButton(CoordinatorEntity[TechemCoordinator], ButtonEntity):
    """Button to trigger import of historical consumption into the Energy Dashboard."""

    _attr_has_entity_name = True
    _attr_name = "Importer les statistiques historiques"
    _attr_icon = "mdi:database-import"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TechemCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"techem_{entry.entry_id}_import_history"
        self._last_import_time: str | None = None
        self._last_import_status: str = "never_run"
        self._last_import_result: dict[str, int] | None = None
        self._is_importing: bool = False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes (audit trail and status)."""
        return {
            "last_import": self._last_import_time,
            "status": self._last_import_status,
            "imported_statistics_count": self._last_import_result,
            # Backward-compatible aliases
            "dernier_import": self._last_import_time,
            "statut": self._last_import_status,
            "nb_statistiques_importees": self._last_import_result,
        }

    async def async_press(self) -> None:
        """Handle button press with guard to prevent duplicate concurrent runs."""
        if self._is_importing:
            _LOGGER.warning("History import is already in progress. Action ignored.")
            return

        self._is_importing = True
        self._last_import_status = "in_progress"
        self.async_write_ha_state()

        try:
            if not self.coordinator.data:
                await self.coordinator.async_request_refresh()

            if self.coordinator.data:
                _LOGGER.info("Starting manual import of Techem history...")
                include_annual = self.entry.options.get(
                    CONF_INCLUDE_ANNUAL_HISTORY, DEFAULT_INCLUDE_ANNUAL_HISTORY
                )
                granularity = self.entry.options.get(
                    CONF_GRANULARITY, GRANULARITY_BIMONTHLY
                )
                enabled_meters = self.entry.options.get(
                    CONF_ENABLED_METERS,
                    self.entry.data.get(CONF_ENABLED_METERS, None),
                )
                counts = await async_import_techem_history(
                    self.hass,
                    self.coordinator.data,
                    include_annual_history=include_annual,
                    granularity=granularity,
                    enabled_meters=enabled_meters,
                )
                self._last_import_time = datetime.now(timezone.utc).isoformat()
                self._last_import_status = "success"
                self._last_import_result = counts
                _LOGGER.info("Techem history manually imported successfully: %s", counts)

                total_points = sum(counts.values()) if counts else 0
                meter_count = len(counts) if counts else 0
                persistent_notification.async_create(
                    self.hass,
                    f"Techem historical import completed successfully.\n\n"
                    f"• {total_points} data points imported across {meter_count} meter(s).\n"
                    f"• You can now configure these meters in Settings → Dashboards → Energy.",
                    title="Techem EnergyCoach",
                    notification_id=f"techem_import_{self.entry.entry_id}",
                )
        except Exception as err:
            self._last_import_status = "error"
            _LOGGER.exception("Error during manual Techem history import: %s", err)
            persistent_notification.async_create(
                self.hass,
                f"Techem historical import failed:\n\n{err}",
                title="Techem EnergyCoach - Error",
                notification_id=f"techem_import_{self.entry.entry_id}",
            )
            raise
        finally:
            self._is_importing = False
            self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=f"Techem EnergyCoach ({self.entry.data.get('username', 'Occupant')})",
            manufacturer="Techem",
            model="EnergyCoach WebDev",
            suggested_area="Appartement",
        )
