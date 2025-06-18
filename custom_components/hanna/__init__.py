"""Hanna Cloud Integration for Home Assistant."""
import asyncio
import logging
from datetime import timedelta

import async_timeout
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, CONF_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hanna Cloud from a config entry."""
    coordinator = HannaCloudCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await coordinator.api.close()
        raise

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api.close()
    return unload_ok


class HannaCloudAPI:
    """API client for Hanna Cloud."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str):
        """Initialize the API client."""
        self.session = session
        self.email = email
        self.password = password
        self.token = None
        self.base_url = "https://hannacloud.com/api"

    async def authenticate(self) -> bool:
        """Authenticate with the Hanna Cloud API using proper encryption."""
        import base64
        import random
        import string

        # The AES key found in Hanna Cloud JavaScript
        key_base64 = "MzJmODBmMDU0ZTAyNDFjYWM0YTVhOGQxY2ZlZTkwMDM="

        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad
        except ImportError:
            _LOGGER.error("pycryptodome is required for Hanna Cloud authentication")
            return False

        def hanna_encrypt(plaintext: str) -> str:
            """Encrypt credentials using Hanna Cloud method."""
            key = base64.b64decode(key_base64)

            # Generate 16-character random IV (letters + digits)
            chars = string.ascii_letters + string.digits
            iv = "".join(random.choice(chars) for _ in range(16))

            # AES-256-CBC encryption
            cipher = AES.new(key, AES.MODE_CBC, iv.encode())
            padded = pad(plaintext.encode(), AES.block_size)
            encrypted = cipher.encrypt(padded)

            # Return IV:encrypted_hex
            return f"{iv}:{encrypted.hex()}"

        # Encrypt credentials
        encoded_email = hanna_encrypt(self.email)
        encoded_password = hanna_encrypt(self.password)

        login_query = {
            "operationName": "Login",
            "variables": {
                "email": encoded_email,
                "password": encoded_password,
                "userLanguage": "German",
                "source": "web"
            },
            "query": """query Login($email: String!, $password: String!, $userLanguage: String!, $source: String) {
                login(
                    email: $email
                    password: $password
                    language: $userLanguage
                    source: $source
                ) {
                    token
                    tokenType
                    __typename
                }
            }"""
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
            "Origin": "https://hannacloud.com",
            "Referer": "https://hannacloud.com/login",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive"
        }

        _LOGGER.debug("Attempting authentication with encrypted credentials")
        _LOGGER.debug("Encoded email: %s", encoded_email)

        try:
            async with async_timeout.timeout(15):
                async with self.session.post(
                    f"{self.base_url}/auth",
                    json=login_query,
                    headers=headers
                ) as response:
                    response_text = await response.text()
                    _LOGGER.debug("Auth response status: %s", response.status)
                    _LOGGER.debug("Auth response text: %s", response_text[:1000])

                    if response.status == 200:
                        try:
                            data = await response.json()
                            _LOGGER.debug("Authentication response: %s", data)

                            # Check for errors first
                            if "errors" in data and data["errors"]:
                                error_msg = data["errors"][0].get("message", "Unknown error")
                                _LOGGER.error("API returned error: %s", error_msg)
                                return False

                            # Handle both array and object responses
                            if (data and "data" in data and data["data"] and "login" in data["data"]):
                                login_data = data["data"]["login"]
                                token = None

                                if isinstance(login_data, list) and len(login_data) > 0:
                                    # Array response (what we expect)
                                    token = login_data[0].get("token")
                                elif isinstance(login_data, dict):
                                    # Object response (fallback)
                                    token = login_data.get("token")

                                if token:
                                    self.token = token
                                    _LOGGER.info("Successfully authenticated with Hanna Cloud using encrypted credentials")
                                    return True
                                else:
                                    _LOGGER.error("No token found in login data: %s", login_data)
                                    return False
                            else:
                                _LOGGER.error("No login data in response: %s", data)
                                return False

                        except Exception as json_err:
                            _LOGGER.error("Failed to parse JSON response: %s", json_err)
                            _LOGGER.error("Raw response: %s", response_text)
                            return False
                    else:
                        _LOGGER.error("Authentication failed with status %s: %s", response.status, response_text)
                        return False

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout during authentication")
            return False
        except Exception as err:
            _LOGGER.error("Error during authentication: %s", err)
            return False

    async def get_devices(self) -> list:
        """Get all devices from the API."""
        if not self.token:
            if not await self.authenticate():
                raise UpdateFailed("Authentication failed")

        devices_query = {
            "operationName": "Devices",
            "variables": {
                "modelGroups": ["BL12x", "BL13x", "BL13xs"],
                "deviceLogs": True
            },
            "query": """query Devices($modelGroups: [String!], $deviceLogs: Boolean!) {
                devices(modelGroups: $modelGroups, deviceLogs: $deviceLogs) {
                    _id
                    DID
                    DM
                    modelGroup
                    DT
                    DINFO {
                        deviceName
                        deviceVersion
                        userId
                        emailId
                        assignedUsers {
                            emailId
                            __typename
                        }
                        tankId
                        tankName
                        __typename
                    }
                    parentId
                    childDevices {
                        DID
                        __typename
                    }
                    dashboardViewStatus
                    deviceOrder
                    secondaryUser
                    reportedSettings
                    status
                    lastUpdated
                    message
                    deviceName
                    batteryStatus
                    __typename
                }
            }"""
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Authorization": f"Bearer {self.token}",
            "Origin": "https://hannacloud.com",
            "Referer": "https://hannacloud.com/dashboard",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
        }

        try:
            async with async_timeout.timeout(10):
                async with self.session.post(
                        f"{self.base_url}/graphql",
                        json=devices_query,
                        headers=headers
                ) as response:
                    response_text = await response.text()
                    _LOGGER.debug("Devices response status: %s", response.status)
                    _LOGGER.debug("Devices response: %s", response_text[:1000])

                    if response.status == 200:
                        data = await response.json()
                        if "data" in data and "devices" in data["data"]:
                            return data["data"]["devices"]
                        elif "errors" in data:
                            error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
                            _LOGGER.error("GraphQL error getting devices: %s", error_msg)
                            raise UpdateFailed(f"GraphQL error: {error_msg}")
                        else:
                            _LOGGER.error("Unexpected devices response: %s", data)
                            raise UpdateFailed("Unexpected response format")

                    # Token might be expired - handle both 401 and 403
                    if response.status in [401, 403]:
                        _LOGGER.info("Token expired (HTTP %s), attempting to re-authenticate", response.status)
                        self.token = None
                        if await self.authenticate():
                            _LOGGER.info("Re-authentication successful, retrying request")
                            return await self.get_devices()
                        else:
                            _LOGGER.error("Re-authentication failed")
                            raise UpdateFailed("Re-authentication failed")

                    _LOGGER.error("Failed to get devices: HTTP %s - %s", response.status, response_text)
                    raise UpdateFailed(f"Failed to get devices: {response.status}")
        except asyncio.TimeoutError:
            raise UpdateFailed("Timeout getting devices")

    async def get_device_readings(self, device_ids: list) -> dict:
        """Get the latest readings for specified devices."""
        if not self.token:
            if not await self.authenticate():
                raise UpdateFailed("Authentication failed")

        readings_query = {
            "operationName": "GetLastDeviceReading",
            "variables": {
                "deviceIds": device_ids
            },
            "query": """query GetLastDeviceReading($deviceIds: [String!]) {
                lastDeviceReadings(deviceIds: $deviceIds) {
                    DID
                    DT
                    messages
                    __typename
                }
            }"""
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Authorization": f"Bearer {self.token}",
            "Origin": "https://hannacloud.com",
            "Referer": "https://hannacloud.com/dashboard",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
        }

        try:
            async with async_timeout.timeout(10):
                async with self.session.post(
                        f"{self.base_url}/graphql",
                        json=readings_query,
                        headers=headers
                ) as response:
                    response_text = await response.text()
                    _LOGGER.debug("Device readings response status: %s", response.status)
                    _LOGGER.debug("Device readings response: %s", response_text[:2000])

                    if response.status == 200:
                        data = await response.json()
                        if "data" in data and "lastDeviceReadings" in data["data"]:
                            readings_dict = {reading["DID"]: reading for reading in data["data"]["lastDeviceReadings"]}
                            _LOGGER.debug("Processed readings dict: %s", readings_dict)
                            return readings_dict

                    # Token might be expired - handle both 401 and 403
                    if response.status in [401, 403]:
                        _LOGGER.info("Token expired (HTTP %s), attempting to re-authenticate", response.status)
                        self.token = None
                        if await self.authenticate():
                            _LOGGER.info("Re-authentication successful, retrying request")
                            return await self.get_device_readings(device_ids)
                        else:
                            _LOGGER.error("Re-authentication failed")
                            raise UpdateFailed("Re-authentication failed")

                    raise UpdateFailed(f"Failed to get device readings: {response.status}")
        except asyncio.TimeoutError:
            raise UpdateFailed("Timeout getting device readings")

    async def close(self):
        """Close the API session."""
        # Session is managed by Home Assistant, no need to close


class HannaCloudCoordinator(DataUpdateCoordinator):
    """Coordinator for Hanna Cloud data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the coordinator."""
        self.api = HannaCloudAPI(
            async_get_clientsession(hass),
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD]
        )

        update_interval = timedelta(minutes=entry.options.get(CONF_UPDATE_INTERVAL, 5))

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            devices = await self.api.get_devices()
            if not devices:
                return {"devices": [], "readings": {}}

            device_ids = [device["DID"] for device in devices]
            _LOGGER.debug(f"Fetching readings for devices: {device_ids}")

            readings = await self.api.get_device_readings(device_ids)
            _LOGGER.debug(f"Received readings: {readings}")

            return {
                "devices": devices,
                "readings": readings
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")