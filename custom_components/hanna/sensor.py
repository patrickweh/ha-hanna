"""Sensor platform for Hanna Cloud integration."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from dateutil import parser as date_parser
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    UnitOfTemperature,
    UnitOfElectricPotential,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HannaCloudCoordinator
from .const import (
    ATTR_BATTERY_STATUS,
    ATTR_DEVICE_ID,
    ATTR_DEVICE_NAME,
    ATTR_LAST_UPDATED,
    ATTR_MODEL_GROUP,
    ATTR_STATUS,
    ATTR_TANK_NAME,
    DEVICE_CLASS_PH,
    DOMAIN,
    UNIT_MV,
    UNIT_PH,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hanna Cloud sensors from a config entry."""
    coordinator: HannaCloudCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    if coordinator.data and "devices" in coordinator.data:
        for device in coordinator.data["devices"]:
            device_id = device["DID"]
            device_name = device.get("deviceName") or device.get("DINFO", {}).get("deviceName", f"Device {device_id}")

            _LOGGER.debug(f"Setting up sensors for device {device_id}: {device_name}")

            # Always create these standard sensors for BL12x devices
            if device.get("modelGroup") == "BL12x":
                # Main measurement sensors
                entities.extend([
                    HannaCloudSensor(
                        coordinator,
                        device,
                        "pH",
                        UNIT_PH,
                        DEVICE_CLASS_PH,
                        config_entry.data[CONF_EMAIL]
                    ),
                    HannaCloudSensor(
                        coordinator,
                        device,
                        "Temperature",
                        UnitOfTemperature.CELSIUS,
                        SensorDeviceClass.TEMPERATURE,
                        config_entry.data[CONF_EMAIL]
                    ),
                    HannaCloudSensor(
                        coordinator,
                        device,
                        "Redox",
                        UNIT_MV,
                        SensorDeviceClass.VOLTAGE,
                        config_entry.data[CONF_EMAIL]
                    ),
                    HannaCloudSensor(
                        coordinator,
                        device,
                        "Chlorine",
                        "ppm",
                        None,
                        config_entry.data[CONF_EMAIL]
                    ),
                    HannaCloudSensor(
                        coordinator,
                        device,
                        "AcidBase",
                        "L",
                        UnitOfVolume.LITERS,
                        config_entry.data[CONF_EMAIL]
                    )
                ])

                # Pump status sensors
                entities.extend([
                    HannaCloudPumpSensor(
                        coordinator,
                        device,
                        "pH Pump",
                        "phPumpColor",
                        config_entry.data[CONF_EMAIL]
                    ),
                    HannaCloudPumpSensor(
                        coordinator,
                        device,
                        "Chlorine Pump",
                        "clPumpColor",
                        config_entry.data[CONF_EMAIL]
                    )
                ])

                # Last dosed volume sensors
                entities.extend([
                    HannaCloudDosedVolumeSensor(
                        coordinator,
                        device,
                        "pH Last Dosed",
                        "acidBase",
                        config_entry.data[CONF_EMAIL]
                    ),
                    HannaCloudDosedVolumeSensor(
                        coordinator,
                        device,
                        "Chlorine Last Dosed",
                        "cl",
                        config_entry.data[CONF_EMAIL]
                    )
                ])

                # Calibration info sensors (GLP)
                entities.extend([
                    HannaCloudCalibrationSensor(
                        coordinator,
                        device,
                        "pH Calibration Date",
                        "pHDateTime",
                        None,
                        None,  # Don't use TIMESTAMP device class
                        config_entry.data[CONF_EMAIL]
                    ),
                    HannaCloudCalibrationSensor(
                        coordinator,
                        device,
                        "ORP Calibration Date",
                        "orpDateTime",
                        None,
                        None,  # Don't use TIMESTAMP device class
                        config_entry.data[CONF_EMAIL]
                    ),
                    HannaCloudCalibrationSensor(
                        coordinator,
                        device,
                        "pH Slope",
                        "pHSlope",
                        "%",
                        None,
                        config_entry.data[CONF_EMAIL]
                    ),
                    HannaCloudCalibrationSensor(
                        coordinator,
                        device,
                        "pH Offset",
                        "pHOffset",
                        UNIT_MV,
                        SensorDeviceClass.VOLTAGE,
                        config_entry.data[CONF_EMAIL]
                    )
                ])

            # Always add a status sensor for each device
            entities.append(
                HannaCloudStatusSensor(
                    coordinator,
                    device,
                    config_entry.data[CONF_EMAIL]
                )
            )

    _LOGGER.debug(f"Adding {len(entities)} entities: {[e.name for e in entities]}")
    async_add_entities(entities)


class HannaCloudSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Hanna Cloud sensor."""

    def __init__(
        self,
        coordinator: HannaCloudCoordinator,
        device: dict,
        sensor_type: str,
        unit: str,
        device_class: str,
        email: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._device = device
        self._sensor_type = sensor_type
        self._unit = unit
        self._device_class = device_class
        self._email = email

        device_id = device["DID"]
        device_name = device.get("deviceName") or device.get("DINFO", {}).get("deviceName", f"Device {device_id}")

        self._attr_name = f"{device_name} {sensor_type}"
        self._attr_unique_id = f"{device_id}_{sensor_type.lower().replace(' ', '_')}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        if device_class in [DEVICE_CLASS_PH, SensorDeviceClass.TEMPERATURE, SensorDeviceClass.VOLTAGE]:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        device_id = self._device["DID"]
        device_name = self._device.get("deviceName") or self._device.get("DINFO", {}).get("deviceName", f"Device {device_id}")
        model_group = self._device.get("modelGroup", "Unknown")

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Hanna Instruments",
            model=model_group,
            sw_version=self._device.get("DINFO", {}).get("deviceVersion"),
        )

    @property
    def native_value(self) -> float | None:
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None

        device_id = self._device["DID"]
        readings = self.coordinator.data.get("readings", {}).get(device_id, {})

        if not readings or "messages" not in readings:
            return None

        messages = readings["messages"]

        # Check if messages has the new "parameters" structure
        if isinstance(messages, dict) and "parameters" in messages:
            parameters = messages["parameters"]
            if isinstance(parameters, list):
                _LOGGER.debug(f"Device {device_id} parameters for {self._sensor_type}: {parameters}")

                # Map sensor types to parameter names
                parameter_map = {
                    "pH": "ph",
                    "Temperature": "temp",
                    "Redox": "orp",
                    "Chlorine": "cl",
                    "AcidBase": "acidBase"
                }

                target_param = parameter_map.get(self._sensor_type)
                if target_param:
                    for param in parameters:
                        if isinstance(param, dict) and param.get("name") == target_param:
                            try:
                                value = param.get("value")
                                if value is not None:
                                    return float(value)
                            except (ValueError, TypeError) as e:
                                _LOGGER.warning(f"Could not convert {target_param} value '{value}' to float: {e}")
                                return None

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_DEVICE_ID: self._device["DID"],
            ATTR_DEVICE_NAME: self._device.get("deviceName") or self._device.get("DINFO", {}).get("deviceName"),
            ATTR_MODEL_GROUP: self._device.get("modelGroup"),
            ATTR_STATUS: self._device.get("status"),
            ATTR_LAST_UPDATED: self._device.get("lastUpdated"),
        }

        # Add tank information if available
        if self._device.get("DINFO", {}).get("tankName"):
            attrs[ATTR_TANK_NAME] = self._device["DINFO"]["tankName"]

        # Add battery status if available
        if self._device.get("batteryStatus"):
            attrs[ATTR_BATTERY_STATUS] = self._device["batteryStatus"]

        return {k: v for k, v in attrs.items() if v is not None}


class HannaCloudPumpSensor(CoordinatorEntity, SensorEntity):
    """Representation of a pump status sensor."""

    def __init__(
        self,
        coordinator: HannaCloudCoordinator,
        device: dict,
        sensor_name: str,
        pump_key: str,
        email: str,
    ) -> None:
        """Initialize the pump sensor."""
        super().__init__(coordinator)

        self._device = device
        self._sensor_name = sensor_name
        self._pump_key = pump_key
        self._email = email

        device_id = device["DID"]
        device_name = device.get("deviceName") or device.get("DINFO", {}).get("deviceName", f"Device {device_id}")

        self._attr_name = f"{device_name} {sensor_name}"
        self._attr_unique_id = f"{device_id}_{sensor_name.lower().replace(' ', '_')}"
        self._attr_icon = "mdi:pump"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        device_id = self._device["DID"]
        device_name = self._device.get("deviceName") or self._device.get("DINFO", {}).get("deviceName", f"Device {device_id}")
        model_group = self._device.get("modelGroup", "Unknown")

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Hanna Instruments",
            model=model_group,
            sw_version=self._device.get("DINFO", {}).get("deviceVersion"),
        )

    @property
    def native_value(self) -> str | None:
        """Return the pump status."""
        if not self.coordinator.data:
            return None

        device_id = self._device["DID"]
        readings = self.coordinator.data.get("readings", {}).get(device_id, {})

        if readings and "messages" in readings:
            messages = readings["messages"]
            if isinstance(messages, dict) and "status" in messages:
                status_obj = messages["status"]
                if isinstance(status_obj, dict):
                    return status_obj.get(self._pump_key, "Unknown")

        return "Unknown"


class HannaCloudDosedVolumeSensor(CoordinatorEntity, SensorEntity):
    """Representation of a last dosed volume sensor."""

    def __init__(
        self,
        coordinator: HannaCloudCoordinator,
        device: dict,
        sensor_name: str,
        dose_key: str,
        email: str,
    ) -> None:
        """Initialize the dosed volume sensor."""
        super().__init__(coordinator)

        self._device = device
        self._sensor_name = sensor_name
        self._dose_key = dose_key
        self._email = email

        device_id = device["DID"]
        device_name = device.get("deviceName") or device.get("DINFO", {}).get("deviceName", f"Device {device_id}")

        self._attr_name = f"{device_name} {sensor_name}"
        self._attr_unique_id = f"{device_id}_{sensor_name.lower().replace(' ', '_')}"
        self._attr_native_unit_of_measurement = "L"
        self._attr_device_class = SensorDeviceClass.VOLUME
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:beaker"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        device_id = self._device["DID"]
        device_name = self._device.get("deviceName") or self._device.get("DINFO", {}).get("deviceName", f"Device {device_id}")
        model_group = self._device.get("modelGroup", "Unknown")

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Hanna Instruments",
            model=model_group,
            sw_version=self._device.get("DINFO", {}).get("deviceVersion"),
        )

    @property
    def native_value(self) -> float | None:
        """Return the last dosed volume."""
        if not self.coordinator.data:
            return None

        device_id = self._device["DID"]
        readings = self.coordinator.data.get("readings", {}).get(device_id, {})

        if readings and "messages" in readings:
            messages = readings["messages"]
            if isinstance(messages, dict) and "lastDosedVolumes" in messages:
                volumes = messages["lastDosedVolumes"]
                if isinstance(volumes, dict):
                    try:
                        value = volumes.get(self._dose_key)
                        if value is not None:
                            return float(value)
                    except (ValueError, TypeError):
                        return None

        return None


class HannaCloudCalibrationSensor(CoordinatorEntity, SensorEntity):
    """Representation of a calibration info sensor (GLP data)."""

    def __init__(
        self,
        coordinator: HannaCloudCoordinator,
        device: dict,
        sensor_name: str,
        glp_key: str,
        unit: str,
        device_class: str,
        email: str,
    ) -> None:
        """Initialize the calibration sensor."""
        super().__init__(coordinator)

        self._device = device
        self._sensor_name = sensor_name
        self._glp_key = glp_key
        self._email = email

        device_id = device["DID"]
        device_name = device.get("deviceName") or device.get("DINFO", {}).get("deviceName", f"Device {device_id}")

        self._attr_name = f"{device_name} {sensor_name}"
        self._attr_unique_id = f"{device_id}_{sensor_name.lower().replace(' ', '_')}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_icon = "mdi:calendar-clock"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        device_id = self._device["DID"]
        device_name = self._device.get("deviceName") or self._device.get("DINFO", {}).get("deviceName", f"Device {device_id}")
        model_group = self._device.get("modelGroup", "Unknown")

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Hanna Instruments",
            model=model_group,
            sw_version=self._device.get("DINFO", {}).get("deviceVersion"),
        )

    @property
    def native_value(self) -> str | float | None:
        """Return the calibration value."""
        if not self.coordinator.data:
            return None

        device_id = self._device["DID"]
        readings = self.coordinator.data.get("readings", {}).get(device_id, {})

        if readings and "messages" in readings:
            messages = readings["messages"]
            if isinstance(messages, dict) and "glp" in messages:
                glp = messages["glp"]
                if isinstance(glp, dict):
                    value = glp.get(self._glp_key)
                    if value is not None:
                        # Handle datetime fields - keep as string for display
                        if "DateTime" in self._glp_key:
                            return str(value)
                        else:
                            try:
                                return float(value)
                            except (ValueError, TypeError):
                                return value

        return None


class HannaCloudStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Hanna Cloud device status sensor."""

    def __init__(
        self,
        coordinator: HannaCloudCoordinator,
        device: dict,
        email: str,
    ) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator)

        self._device = device
        self._email = email

        device_id = device["DID"]
        device_name = device.get("deviceName") or device.get("DINFO", {}).get("deviceName", f"Device {device_id}")

        self._attr_name = f"{device_name} Status"
        self._attr_unique_id = f"{device_id}_status"
        self._attr_icon = "mdi:water-check"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        device_id = self._device["DID"]
        device_name = self._device.get("deviceName") or self._device.get("DINFO", {}).get("deviceName", f"Device {device_id}")
        model_group = self._device.get("modelGroup", "Unknown")

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Hanna Instruments",
            model=model_group,
            sw_version=self._device.get("DINFO", {}).get("deviceVersion"),
        )

    @property
    def native_value(self) -> str | None:
        """Return the native value of the sensor."""
        # Try to get status from readings first
        if self.coordinator.data:
            device_id = self._device["DID"]
            readings = self.coordinator.data.get("readings", {}).get(device_id, {})
            if readings and "messages" in readings:
                messages = readings["messages"]
                if isinstance(messages, dict) and "status" in messages:
                    status_obj = messages["status"]
                    if isinstance(status_obj, dict):
                        # Return the overall status color or a summary
                        status_color = status_obj.get("StatusColor", "Unknown")
                        return status_color

        # Fallback to device status
        return self._device.get("status", "Unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_DEVICE_ID: self._device["DID"],
            ATTR_DEVICE_NAME: self._device.get("deviceName") or self._device.get("DINFO", {}).get("deviceName"),
            ATTR_MODEL_GROUP: self._device.get("modelGroup"),
            ATTR_LAST_UPDATED: self._device.get("lastUpdated"),
        }

        # Add tank information if available
        if self._device.get("DINFO", {}).get("tankName"):
            attrs[ATTR_TANK_NAME] = self._device["DINFO"]["tankName"]

        # Add battery status if available
        if self._device.get("batteryStatus"):
            attrs[ATTR_BATTERY_STATUS] = self._device["batteryStatus"]

        # Add latest reading data
        if self.coordinator.data:
            device_id = self._device["DID"]
            readings = self.coordinator.data.get("readings", {}).get(device_id, {})
            if readings:
                attrs["last_reading_time"] = readings.get("DT")
                if "messages" in readings:
                    messages = readings["messages"]
                    if isinstance(messages, dict):
                        # Add status details if available
                        if "status" in messages:
                            status_obj = messages["status"]
                            if isinstance(status_obj, dict):
                                for key, value in status_obj.items():
                                    attrs[f"status_{key.lower()}"] = value

                        # Add alarm information
                        if "alarms" in messages:
                            attrs["alarms"] = messages["alarms"]
                        if "warnings" in messages:
                            attrs["warnings"] = messages["warnings"]
                        if "errors" in messages:
                            attrs["errors"] = messages["errors"]

                        # Add connection state
                        if "connectionState" in messages:
                            attrs["connection_state"] = messages["connectionState"]

        return {k: v for k, v in attrs.items() if v is not None}