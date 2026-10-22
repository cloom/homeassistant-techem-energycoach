"""DataUpdateCoordinator for Techem EnergyCoach."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import TechemEnergyCoachClient, TechemData, TechemError
from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class TechemCoordinator(DataUpdateCoordinator[TechemData]):
    """Class to manage fetching Techem data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        scan_interval_sec = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        
        self.client = TechemEnergyCoachClient(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval_sec),
        )

    async def _async_update_data(self) -> TechemData:
        """Fetch data from Techem portal."""
        try:
            return await self.hass.async_add_executor_job(self.client.fetch_data)
        except TechemError as err:
            raise UpdateFailed(f"Error fetching Techem data: {err}") from err
