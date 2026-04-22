"""Config flow for Storm Tracker."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_APPROACH_THRESHOLD,
    CONF_GEO_LOCATION_PREFIX,
    CONF_TIME_WINDOW_MINUTES,
    CONF_UNIT_SYSTEM,
    CONF_UPDATE_INTERVAL,
    DEFAULT_APPROACH_THRESHOLD,
    DEFAULT_GEO_LOCATION_PREFIX,
    DEFAULT_NAME,
    DEFAULT_TIME_WINDOW_MINUTES,
    DEFAULT_UNIT_SYSTEM,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    UNIT_OPTIONS,
)


def _basic_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name", default=defaults.get("name", DEFAULT_NAME)): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_UNIT_SYSTEM, default=defaults.get(CONF_UNIT_SYSTEM, DEFAULT_UNIT_SYSTEM)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=UNIT_OPTIONS,
                    mode=SelectSelectorMode.LIST,
                    translation_key=CONF_UNIT_SYSTEM,
                )
            ),
        }
    )


def _data_source_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_GEO_LOCATION_PREFIX,
                default=defaults.get(CONF_GEO_LOCATION_PREFIX, DEFAULT_GEO_LOCATION_PREFIX),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
        }
    )


def _timing_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_TIME_WINDOW_MINUTES,
                default=defaults.get(CONF_TIME_WINDOW_MINUTES, DEFAULT_TIME_WINDOW_MINUTES),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=1440, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(min=10, max=3600, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_APPROACH_THRESHOLD,
                default=defaults.get(CONF_APPROACH_THRESHOLD, DEFAULT_APPROACH_THRESHOLD),
            ): NumberSelector(
                NumberSelectorConfig(min=0.1, max=1000.0, step=0.1, mode=NumberSelectorMode.BOX)
            ),
        }
    )


def _validate_data_source(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    prefix = data.get(CONF_GEO_LOCATION_PREFIX, "").strip()
    if not prefix:
        errors[CONF_GEO_LOCATION_PREFIX] = "invalid_prefix"
    return errors


def _validate_timing(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if int(data.get(CONF_TIME_WINDOW_MINUTES, 0)) < 1:
        errors[CONF_TIME_WINDOW_MINUTES] = "invalid_window"
    if int(data.get(CONF_UPDATE_INTERVAL, 0)) < 1:
        errors[CONF_UPDATE_INTERVAL] = "invalid_interval"
    if float(data.get(CONF_APPROACH_THRESHOLD, 0)) <= 0:
        errors[CONF_APPROACH_THRESHOLD] = "invalid_threshold"
    return errors


class StormTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Storm Tracker."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1 — Basic Settings."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_data_source()

        return self.async_show_form(
            step_id="user",
            data_schema=_basic_schema(self._data),
        )

    async def async_step_data_source(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2 — Data Source."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_data_source(user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_timing()

        return self.async_show_form(
            step_id="data_source",
            data_schema=_data_source_schema(user_input or self._data),
            errors=errors,
        )

    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3 — Timing & Thresholds."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_timing(user_input)
            if not errors:
                self._data.update(user_input)
                return self.async_create_entry(
                    title=self._data.get("name", DEFAULT_NAME),
                    data=self._data,
                )

        return self.async_show_form(
            step_id="timing",
            data_schema=_timing_schema(user_input or self._data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> StormTrackerOptionsFlow:
        return StormTrackerOptionsFlow(config_entry)


class StormTrackerOptionsFlow(OptionsFlow):
    """Handle the options flow for Storm Tracker."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Options step 1 — Data Source."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_data_source(user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_timing()

        current = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_data_source_schema(user_input or current),
            errors=errors,
        )

    async def async_step_timing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Options step 2 — Timing & Thresholds."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_timing(user_input)
            if not errors:
                self._data.update(user_input)
                return self.async_create_entry(data=self._data)

        current = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="timing",
            data_schema=_timing_schema(user_input or current),
            errors=errors,
        )
