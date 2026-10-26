"""The Techem EnergyCoach integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    SERVICE_IMPORT_HISTORY,
    CONF_INCLUDE_ANNUAL_HISTORY,
    DEFAULT_INCLUDE_ANNUAL_HISTORY,
    CONF_GRANULARITY,
    GRANULARITY_BIMONTHLY,
    CONF_ENABLED_METERS,
)
from .coordinator import TechemCoordinator
from .historical_import import async_import_techem_history

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Techem component."""
    hass.data.setdefault(DOMAIN, {})

    async def handle_import_history(call: ServiceCall) -> None:
        """Handle the import historical data service call."""
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            coordinator: TechemCoordinator = entry_data.get("coordinator")
            entry = hass.config_entries.async_get_entry(entry_id)
            if coordinator and coordinator.data and entry:
                _LOGGER.info("Manual history import requested via service for %s", entry_id)
                include_annual = entry.options.get(
                    CONF_INCLUDE_ANNUAL_HISTORY, DEFAULT_INCLUDE_ANNUAL_HISTORY
                )
                granularity = entry.options.get(
                    CONF_GRANULARITY, GRANULARITY_BIMONTHLY
                )
                enabled_meters = entry.options.get(
                    CONF_ENABLED_METERS,
                    entry.data.get(CONF_ENABLED_METERS, None),
                )
                await async_import_techem_history(
                    hass,
                    coordinator.data,
                    include_annual_history=include_annual,
                    granularity=granularity,
                    enabled_meters=enabled_meters,
                )

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_HISTORY,
        handle_import_history,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Techem EnergyCoach from a config entry."""
    coordinator = TechemCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to fetch initial Techem readings: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }

    # Handle automatic initial import for new setup or one-time upgrade migration
    if entry.data.get("initial_import_pending", False) or not entry.data.get("v1_clean_import_done", False):
        new_data = dict(entry.data)
        new_data["initial_import_pending"] = False
        new_data["v1_clean_import_done"] = True
        hass.config_entries.async_update_entry(entry, data=new_data)

        async def _run_initial_auto_import() -> None:
            _LOGGER.info("Starting initial automatic import of Techem history...")
            try:
                include_annual = entry.options.get(
                    CONF_INCLUDE_ANNUAL_HISTORY, DEFAULT_INCLUDE_ANNUAL_HISTORY
                )
                granularity = entry.options.get(
                    CONF_GRANULARITY, GRANULARITY_BIMONTHLY
                )
                enabled_meters = entry.options.get(
                    CONF_ENABLED_METERS,
                    entry.data.get(CONF_ENABLED_METERS, None),
                )
                counts = await async_import_techem_history(
                    hass,
                    coordinator.data,
                    include_annual_history=include_annual,
                    granularity=granularity,
                    enabled_meters=enabled_meters,
                )
                _LOGGER.info("Initial Techem auto-import completed successfully: %s", counts)
            except Exception as err:
                _LOGGER.error("Error during initial Techem auto-import: %s", err)

        hass.async_create_background_task(_run_initial_auto_import(), "techem_initial_auto_import")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
