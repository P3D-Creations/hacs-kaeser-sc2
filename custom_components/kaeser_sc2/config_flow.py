"""Config flow for Kaeser Sigma Control 2."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback

from .api import SigmaControl2
from .const import DEFAULT_PASSWORD, DEFAULT_POLL_INTERVAL, DEFAULT_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _validate_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, str]:
    """Validate the user input and return info dict or raise."""
    client = SigmaControl2(
        host=data[CONF_HOST],
        username=data.get(CONF_USERNAME, DEFAULT_USERNAME),
        password=data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
        timeout=15,
    )
    try:
        ok = await client.test_connection()
    except Exception as exc:
        _LOGGER.error("Connection test failed for %s: %s", data[CONF_HOST], exc)
        raise CannotConnect from exc
    finally:
        await client.close()

    if not ok:
        raise CannotConnect

    return {"title": data.get("name", data[CONF_HOST])}


class KaeserSC2ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kaeser SC2."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KaeserSC2OptionsFlow:
        """Return the options flow handler."""
        return KaeserSC2OptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — user enters host + credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Ensure we don't add the same host twice
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            try:
                info = await _validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=info["title"], data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
                vol.Optional(
                    "poll_interval", default=DEFAULT_POLL_INTERVAL
                ): vol.All(int, vol.Range(min=10, max=300)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate invalid auth."""


class KaeserSC2OptionsFlow(OptionsFlow):
    """Handle options for Kaeser SC2 (poll interval, etc.)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.options.get(
            "poll_interval",
            self._config_entry.data.get("poll_interval", DEFAULT_POLL_INTERVAL),
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    "poll_interval",
                    default=current_interval,
                ): vol.All(int, vol.Range(min=5, max=300)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
