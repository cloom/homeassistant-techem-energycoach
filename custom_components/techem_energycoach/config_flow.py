"""Config flow for Techem EnergyCoach integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .client import (
    TechemEnergyCoachClient,
    TechemAuthError,
    TechemConnectionError,
    TechemData,
)
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    CONF_INCLUDE_ANNUAL_HISTORY,
    DEFAULT_INCLUDE_ANNUAL_HISTORY,
    CONF_GRANULARITY,
    GRANULARITY_BIMONTHLY,
    GRANULARITY_MONTHLY,
    CONF_ENABLED_METERS,
    CONF_AUTO_IMPORT,
    DEFAULT_AUTO_IMPORT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Techem EnergyCoach."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._username: str | None = None
        self._password: str | None = None
        self._discovered_data: TechemData | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (credentials entry and verification)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            # Prevent duplicate entries for same username
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            client = TechemEnergyCoachClient(username, password)
            try:
                data = await self.hass.async_add_executor_job(client.fetch_data)
            except TechemAuthError:
                errors["base"] = "invalid_auth"
            except TechemConnectionError:
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error during validation: %s", err)
                errors["base"] = "unknown"
            else:
                self._username = username
                self._password = password
                self._discovered_data = data
                return await self.async_step_discovery()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Show discovered meters and let user select meters and setup options."""
        assert self._discovered_data is not None
        assert self._username is not None
        assert self._password is not None

        errors: dict[str, str] = {}

        meter_labels = {
            "eau_chaude": "Hot Water",
            "eau_froide": "Cold Water",
            "chauffage": "Heating",
        }
        meters_dict: dict[str, str] = {}
        for m_type, meter in self._discovered_data.meters.items():
            label = meter_labels.get(m_type, m_type.replace("_", " ").title())
            meters_dict[m_type] = f"{label} (Meter #{meter.meter_id})"

        if not meters_dict:
            meters_dict = {
                "eau_chaude": "Hot Water",
                "eau_froide": "Cold Water",
                "chauffage": "Heating",
            }

        if user_input is not None:
            selected_meters = user_input.get(CONF_ENABLED_METERS, [])
            if not selected_meters:
                errors["base"] = "no_meters_selected"
            else:
                title = self._username
                if self._discovered_data.building_info:
                    b_part = self._discovered_data.building_info.split(" - ")[0]
                    title = f"{self._username} ({b_part})"

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_USERNAME: self._username,
                        CONF_PASSWORD: self._password,
                        CONF_ENABLED_METERS: selected_meters,
                        "initial_import_pending": user_input.get(CONF_AUTO_IMPORT, DEFAULT_AUTO_IMPORT),
                    },
                    options={
                        CONF_ENABLED_METERS: selected_meters,
                        CONF_AUTO_IMPORT: user_input.get(CONF_AUTO_IMPORT, DEFAULT_AUTO_IMPORT),
                        CONF_GRANULARITY: user_input.get(CONF_GRANULARITY, GRANULARITY_BIMONTHLY),
                        CONF_INCLUDE_ANNUAL_HISTORY: user_input.get(
                            CONF_INCLUDE_ANNUAL_HISTORY, DEFAULT_INCLUDE_ANNUAL_HISTORY
                        ),
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLED_METERS,
                    default=list(meters_dict.keys()),
                ): cv.multi_select(meters_dict),
                vol.Required(
                    CONF_AUTO_IMPORT,
                    default=DEFAULT_AUTO_IMPORT,
                ): bool,
                vol.Required(
                    CONF_GRANULARITY,
                    default=GRANULARITY_BIMONTHLY,
                ): vol.In([GRANULARITY_BIMONTHLY, GRANULARITY_MONTHLY]),
                vol.Required(
                    CONF_INCLUDE_ANNUAL_HISTORY,
                    default=DEFAULT_INCLUDE_ANNUAL_HISTORY,
                ): bool,
            }
        )

        placeholders = {
            "building_info": self._discovered_data.building_info or "Portail Techem",
        }

        return self.async_show_form(
            step_id="discovery",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Techem EnergyCoach."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize options flow."""
        if config_entry is not None:
            self._custom_config_entry = config_entry

    @property
    def _entry(self) -> config_entries.ConfigEntry:
        """Return config entry safely across HA versions."""
        if hasattr(self, "_custom_config_entry"):
            return self._custom_config_entry
        return self.config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self._entry
        coordinator = self.hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
        meter_labels = {
            "eau_chaude": "Hot Water",
            "eau_froide": "Cold Water",
            "chauffage": "Heating",
        }
        meters_dict: dict[str, str] = {}
        if coordinator and coordinator.data and coordinator.data.meters:
            for m_type, meter in coordinator.data.meters.items():
                label = meter_labels.get(m_type, m_type.replace("_", " ").title())
                meters_dict[m_type] = f"{label} (Meter #{meter.meter_id})"
        if not meters_dict:
            meters_dict = {
                "eau_chaude": "Hot Water",
                "eau_froide": "Cold Water",
                "chauffage": "Heating",
            }

        current_enabled = entry.options.get(
            CONF_ENABLED_METERS,
            entry.data.get(CONF_ENABLED_METERS, list(meters_dict.keys())),
        )

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLED_METERS,
                    default=current_enabled,
                ): cv.multi_select(meters_dict),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=3600, max=86400)),
                vol.Optional(
                    CONF_INCLUDE_ANNUAL_HISTORY,
                    default=entry.options.get(
                        CONF_INCLUDE_ANNUAL_HISTORY, DEFAULT_INCLUDE_ANNUAL_HISTORY
                    ),
                ): bool,
                vol.Optional(
                    CONF_GRANULARITY,
                    default=entry.options.get(
                        CONF_GRANULARITY, GRANULARITY_BIMONTHLY
                    ),
                ): vol.In([GRANULARITY_BIMONTHLY, GRANULARITY_MONTHLY]),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)

