"""Config flow for Hanna Cloud integration."""
import logging
from typing import Any

import aiohttp
import async_timeout
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    import base64
    import random
    import string

    # The AES key found in Hanna Cloud JavaScript
    key_base64 = "MzJmODBmMDU0ZTAyNDFjYWM0YTVhOGQxY2ZlZTkwMDM="

    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
    except ImportError:
        raise CannotConnect

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

    session = async_get_clientsession(hass)

    # Encrypt credentials
    encoded_email = hanna_encrypt(data[CONF_EMAIL])
    encoded_password = hanna_encrypt(data[CONF_PASSWORD])

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
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    }

    try:
        async with async_timeout.timeout(10):
            async with session.post(
                "https://hannacloud.com/api/auth",
                json=login_query,
                headers=headers
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    _LOGGER.debug("Validation response: %s", response_data)

                    # Check for errors first
                    if "errors" in response_data and response_data["errors"]:
                        error_msg = response_data["errors"][0].get("message", "Unknown error")
                        _LOGGER.error("API returned error during validation: %s", error_msg)
                        raise InvalidAuth

                    # Handle both array and object responses
                    if (response_data and "data" in response_data and response_data["data"] and
                        "login" in response_data["data"]):
                        login_data = response_data["data"]["login"]
                        token = None

                        if isinstance(login_data, list) and len(login_data) > 0:
                            # Array response (what we expect)
                            token = login_data[0].get("token")
                        elif isinstance(login_data, dict):
                            # Object response (fallback)
                            token = login_data.get("token")

                        if token:
                            return {"title": f"Hanna Cloud ({data[CONF_EMAIL]})"}
                        else:
                            _LOGGER.error("No token in validation response: %s", login_data)
                            raise InvalidAuth
                    else:
                        _LOGGER.error("No login data in validation response: %s", response_data)
                        raise InvalidAuth
                else:
                    response_text = await response.text()
                    _LOGGER.error("Validation failed: %s - %s", response.status, response_text)
                    if response.status == 401:
                        raise InvalidAuth
                    raise CannotConnect
    except Exception as err:
        _LOGGER.error("Error connecting to Hanna Cloud: %s", err)
        raise CannotConnect


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hanna Cloud."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_EMAIL])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Hanna Cloud."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60))
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""