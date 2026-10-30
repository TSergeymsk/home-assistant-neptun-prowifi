"""Config flow for Neptun Local integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_SCAN_INTERVAL,
    CONF_DEBUG,
    CONF_RETRY_ATTEMPTS,
    CONF_RETRY_DELAY,
    CONF_MAX_CONSECUTIVE_FAILURES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_DEBUG,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_DELAY,
    DEFAULT_MAX_CONSECUTIVE_FAILURES,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
        vol.Optional(CONF_DEBUG, default=DEFAULT_DEBUG): bool,
        vol.Optional(CONF_RETRY_ATTEMPTS, default=DEFAULT_RETRY_ATTEMPTS): cv.positive_int,
        vol.Optional(CONF_RETRY_DELAY, default=DEFAULT_RETRY_DELAY): cv.positive_int,
        vol.Optional(CONF_MAX_CONSECUTIVE_FAILURES, default=DEFAULT_MAX_CONSECUTIVE_FAILURES): cv.positive_int,
    }
)


class NeptunConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Neptun Local."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(
                title=f"Neptun {user_input[CONF_HOST]}", data=user_input
            )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return NeptunOptionsFlow()


class NeptunOptionsFlow(config_entries.OptionsFlow):
    """Neptun Local options flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): cv.positive_int,
                vol.Optional(
                    CONF_DEBUG, default=options.get(CONF_DEBUG, DEFAULT_DEBUG)
                ): bool,
                vol.Optional(
                    CONF_RETRY_ATTEMPTS,
                    default=options.get(
                        CONF_RETRY_ATTEMPTS, DEFAULT_RETRY_ATTEMPTS
                    ),
                ): cv.positive_int,
                vol.Optional(
                    CONF_RETRY_DELAY,
                    default=options.get(CONF_RETRY_DELAY, DEFAULT_RETRY_DELAY),
                ): cv.positive_int,
                vol.Optional(
                    CONF_MAX_CONSECUTIVE_FAILURES,
                    default=options.get(
                        CONF_MAX_CONSECUTIVE_FAILURES,
                        DEFAULT_MAX_CONSECUTIVE_FAILURES,
                    ),
                ): cv.positive_int,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)