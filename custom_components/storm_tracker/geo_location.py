"""Geo location platform for Storm Tracker — centroid and leading-edge map pins."""
from __future__ import annotations

import logging

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, GEO_ATTRIBUTION, SECTOR_LABELS
from .coordinator import SectorData, StormTrackerCoordinator, StormTrackerData

_LOGGER = logging.getLogger(__name__)

# Entity types placed on the map per active sector
_TYPE_CENTROID = "centroid"
_TYPE_EDGE     = "edge"


def _delete_signal(entry_id: str, sector_idx: int, entity_type: str) -> str:
    return f"{DOMAIN}_delete_{entry_id}_{sector_idx}_{entity_type}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: StormTrackerCoordinator = entry.runtime_data
    manager = StormTrackerGeoManager(hass, entry, async_add_entities)

    if coordinator.data:
        manager.update(coordinator.data)

    entry.async_on_unload(
        coordinator.async_add_listener(
            lambda: manager.update(coordinator.data)
        )
    )


class StormTrackerGeoManager:
    """Creates, updates, and removes geo_location entities as sectors change."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._async_add_entities = async_add_entities
        self._entities: dict[tuple[int, str], StormTrackerGeoEntity] = {}

    @callback
    def update(self, data: StormTrackerData) -> None:
        for idx, sector in data.sectors.items():
            label = SECTOR_LABELS[idx]
            active = sector.strike_count > 0

            if active and sector.centroid_lat is not None:
                self._upsert(idx, _TYPE_CENTROID, sector, label)
            else:
                self._remove(idx, _TYPE_CENTROID)

            if active and sector.edge_lat is not None:
                self._upsert(idx, _TYPE_EDGE, sector, label)
            else:
                self._remove(idx, _TYPE_EDGE)

    def _upsert(
        self,
        idx: int,
        entity_type: str,
        sector: SectorData,
        label: str,
    ) -> None:
        key = (idx, entity_type)
        lat  = sector.centroid_lat if entity_type == _TYPE_CENTROID else sector.edge_lat
        lon  = sector.centroid_lon if entity_type == _TYPE_CENTROID else sector.edge_lon
        dist = sector.avg_distance if entity_type == _TYPE_CENTROID else sector.closest_distance

        if key in self._entities:
            self._entities[key].update_position(lat, lon, dist, sector.trend)
        else:
            entity = StormTrackerGeoEntity(
                self._entry.entry_id, idx, entity_type, lat, lon, dist, sector.trend, label
            )
            self._entities[key] = entity
            self._async_add_entities([entity])

    def _remove(self, idx: int, entity_type: str) -> None:
        key = (idx, entity_type)
        if key in self._entities:
            del self._entities[key]
            async_dispatcher_send(
                self._hass,
                _delete_signal(self._entry.entry_id, idx, entity_type),
            )


class StormTrackerGeoEntity(GeolocationEvent):
    """A single map pin — either the centroid or leading edge of an active sector."""

    _attr_should_poll  = False
    _attr_attribution  = GEO_ATTRIBUTION
    _attr_source       = DOMAIN

    def __init__(
        self,
        entry_id: str,
        sector_idx: int,
        entity_type: str,
        lat: float,
        lon: float,
        distance: float | None,
        trend: str,
        sector_label: str,
    ) -> None:
        self._entry_id    = entry_id
        self._sector_idx  = sector_idx
        self._entity_type = entity_type
        self._attr_latitude  = lat
        self._attr_longitude = lon
        self._attr_distance  = distance
        self._attr_unique_id = f"{entry_id}_geo_{sector_idx}_{entity_type}"
        self._attr_name      = f"Storm {sector_label} {entity_type.title()}"
        self._attr_icon      = "mdi:weather-lightning" if entity_type == _TYPE_CENTROID else "mdi:flash-alert"
        self._attr_extra_state_attributes = {"trend": trend, "sector": sector_label}
        self._remove_signal: callable | None = None

    async def async_added_to_hass(self) -> None:
        self._remove_signal = async_dispatcher_connect(
            self.hass,
            _delete_signal(self._entry_id, self._sector_idx, self._entity_type),
            self._delete_callback,
        )

    async def _delete_callback(self) -> None:
        if self._remove_signal:
            self._remove_signal()
            self._remove_signal = None
        await self.async_remove(force_remove=True)

    @callback
    def update_position(
        self,
        lat: float,
        lon: float,
        distance: float | None,
        trend: str,
    ) -> None:
        self._attr_latitude  = lat
        self._attr_longitude = lon
        self._attr_distance  = distance
        self._attr_extra_state_attributes = {
            "trend": trend,
            "sector": self._attr_extra_state_attributes["sector"],
        }
        self.async_write_ha_state()
