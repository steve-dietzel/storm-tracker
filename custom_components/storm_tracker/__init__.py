"""Storm Tracker — sector-based lightning situational awareness."""
from __future__ import annotations

import logging
import os

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import StormTrackerCoordinator

_LOGGER = logging.getLogger(__name__)

CARD_URL  = "/storm_tracker_card/storm-tracker-card.js"
CARD_FILE = os.path.join(os.path.dirname(__file__), "storm-tracker-card.js")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Storm Tracker from a config entry."""

    # Register the Lovelace card as a static path so the browser can load it.
    # This is done here (not in async_setup) because async_setup is only called
    # when the integration is listed in configuration.yaml — which we don't require.
    # async_register_static_paths is safe to call on every HA restart.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, CARD_FILE, cache_headers=False)]
    )
    _LOGGER.info("Storm Tracker card available at %s", CARD_URL)

    update_interval = int(
        entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
    )
    coordinator = StormTrackerCoordinator(hass, entry, update_interval)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Storm Tracker config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
