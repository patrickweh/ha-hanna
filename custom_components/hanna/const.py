"""Constants for the Hanna Cloud integration."""

DOMAIN = "ha-hanna"

# Configuration keys
CONF_UPDATE_INTERVAL = "update_interval"

# Default values
DEFAULT_UPDATE_INTERVAL = 5  # minutes

# Device classes
DEVICE_CLASS_PH = "ph"
DEVICE_CLASS_TEMPERATURE = "temperature"
DEVICE_CLASS_VOLTAGE = "voltage"  # For redox/ORP measurements

# Units
UNIT_PH = "pH"
UNIT_MV = "mV"  # millivolts for redox
UNIT_CELSIUS = "°C"

# Attributes
ATTR_DEVICE_ID = "device_id"
ATTR_DEVICE_NAME = "device_name"
ATTR_TANK_NAME = "tank_name"
ATTR_LAST_UPDATED = "last_updated"
ATTR_BATTERY_STATUS = "battery_status"
ATTR_STATUS = "status"
ATTR_MODEL_GROUP = "model_group"