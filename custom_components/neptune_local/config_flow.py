"""Config flow for Neptun Local integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_SCAN_INTERVAL,
    CONF_DEBUG,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_DEBUG,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
        vol.Optional(CONF_DEBUG, default=DEFAULT_DEBUG): bool,
    }
)


class NeptunConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Neptun Local."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Neptun ProW+",
                data={CONF_HOST: user_input[CONF_HOST]},
                options={
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    CONF_DEBUG: user_input.get(CONF_DEBUG, DEFAULT_DEBUG),
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return NeptunOptionsFlow()


class NeptunOptionsFlow(OptionsFlow):
    """Handle options flow for Neptun Local."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            host = user_input[CONF_HOST]

            # Host lives in entry.data (coordinator reads it from there).
            if host != self.config_entry.data.get(CONF_HOST):
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_HOST: host},
                )

            # scan_interval and debug live in entry.options.
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    CONF_DEBUG: user_input[CONF_DEBUG],
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=self.config_entry.data.get(CONF_HOST),
                    ): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): int,
                    vol.Optional(
                        CONF_DEBUG,
                        default=self.config_entry.options.get(
                            CONF_DEBUG, DEFAULT_DEBUG
                        ),
                    ): bool,
                }
            ),
        )