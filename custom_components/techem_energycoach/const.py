"""Constants for the Techem EnergyCoach integration."""

DOMAIN = "techem_energycoach"

# Configuration keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"

# Defaults
DEFAULT_SCAN_INTERVAL = 86400  # 24 hours in seconds
CONF_INCLUDE_ANNUAL_HISTORY = "include_annual_history"
DEFAULT_INCLUDE_ANNUAL_HISTORY = True
CONF_GRANULARITY = "granularity"
GRANULARITY_BIMONTHLY = "bimonthly"
GRANULARITY_MONTHLY = "monthly"

CONF_ENABLED_METERS = "enabled_meters"
CONF_AUTO_IMPORT = "auto_import"
DEFAULT_AUTO_IMPORT = True

# Meter families / types
METER_TYPE_HOT_WATER = "eau_chaude"
METER_TYPE_COLD_WATER = "eau_froide"
METER_TYPE_HEAT = "chauffage"

# Services
SERVICE_IMPORT_HISTORY = "import_historical_data"

