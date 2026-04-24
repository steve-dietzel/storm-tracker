"""Sensor platform for Storm Tracker."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_UNIT_SYSTEM,
    DEFAULT_UNIT_SYSTEM,
    DOMAIN,
    SECTOR_LABELS,
    TREND_STATES,
    UNIT_IMPERIAL,
    UNIT_KILOMETERS,
    UNIT_MILES,
)
from .coordinator import StormTrackerCoordinator, StormTrackerData

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entity description helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class StormTrackerSensorDescription(SensorEntityDescription):
    """Extended description carrying a value extractor."""


def _distance_unit(entry: ConfigEntry) -> str:
    unit_sys = entry.options.get(
        CONF_UNIT_SYSTEM, entry.data.get(CONF_UNIT_SYSTEM, DEFAULT_UNIT_SYSTEM)
    )
    return UNIT_MILES if unit_sys == UNIT_IMPERIAL else UNIT_KILOMETERS


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Storm Tracker sensors from a config entry."""
    coordinator: StormTrackerCoordinator = entry.runtime_data
    dist_unit = _distance_unit(entry)

    entities: list[SensorEntity] = []

    # 8 sector devices
    for idx, label in enumerate(SECTOR_LABELS):
        device_id = f"{entry.entry_id}_sector_{label.lower()}"
        entities.extend(
            [
                SectorStrikeCountSensor(coordinator, entry, idx, label, device_id),
                SectorAvgDistanceSensor(coordinator, entry, idx, label, device_id, dist_unit),
                SectorClosestDistanceSensor(coordinator, entry, idx, label, device_id, dist_unit),
                SectorTrendSensor(coordinator, entry, idx, label, device_id),
            ]
        )

    # 1 summary device
    summary_device_id = f"{entry.entry_id}_summary"
    entities.extend(
        [
            SummaryTotalStrikeCountSensor(coordinator, entry, summary_device_id),
            SummaryClosestDistanceSensor(coordinator, entry, summary_device_id, dist_unit),
            SummaryClosestSectorSensor(coordinator, entry, summary_device_id),
            SummaryActiveSectorCountSensor(coordinator, entry, summary_device_id),
            SummaryApproachingSectorCountSensor(coordinator, entry, summary_device_id),
        ]
    )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class StormTrackerSensorBase(CoordinatorEntity[StormTrackerCoordinator], SensorEntity):
    """Base for all Storm Tracker sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        unique_id_suffix: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_id_suffix}"
        self._attr_device_info = device_info

    @property
    def data(self) -> StormTrackerData:
        return self.coordinator.data


# ---------------------------------------------------------------------------
# Sector device info factory
# ---------------------------------------------------------------------------

def _sector_device(entry: ConfigEntry, label: str, device_id: str) -> DeviceInfo:
    integration_name = entry.data.get("name", "Storm Tracker")
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=f"{integration_name} {label}",
        manufacturer="Storm Tracker",
        model="Sector Monitor",
        entry_type=None,
    )


def _summary_device(entry: ConfigEntry, device_id: str) -> DeviceInfo:
    integration_name = entry.data.get("name", "Storm Tracker")
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=integration_name,
        manufacturer="Storm Tracker",
        model="Summary Monitor",
        entry_type=None,
    )


# ---------------------------------------------------------------------------
# Sector sensors
# ---------------------------------------------------------------------------

class SectorStrikeCountSensor(StormTrackerSensorBase):
    """Strike count for one sector."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "strikes"
    _attr_icon = "mdi:lightning-bolt-circle"
    _attr_translation_key = "sector_strike_count"

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        sector_idx: int,
        label: str,
        device_id: str,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            f"sector_{label.lower()}_strike_count",
            _sector_device(entry, label, device_id),
        )
        self._sector_idx = sector_idx
        self._attr_name = "Strike Count"

    @property
    def native_value(self) -> int:
        return self.data.sectors[self._sector_idx].strike_count


class SectorAvgDistanceSensor(StormTrackerSensorBase):
    """Average strike distance for one sector."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-distance"
    _attr_translation_key = "sector_avg_distance"

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        sector_idx: int,
        label: str,
        device_id: str,
        dist_unit: str,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            f"sector_{label.lower()}_avg_distance",
            _sector_device(entry, label, device_id),
        )
        self._sector_idx = sector_idx
        self._attr_name = "Avg Distance"
        self._attr_native_unit_of_measurement = dist_unit

    @property
    def native_value(self) -> float | None:
        return self.data.sectors[self._sector_idx].avg_distance


class SectorClosestDistanceSensor(StormTrackerSensorBase):
    """Closest strike distance for one sector."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-distance"
    _attr_translation_key = "sector_closest_distance"

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        sector_idx: int,
        label: str,
        device_id: str,
        dist_unit: str,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            f"sector_{label.lower()}_closest_distance",
            _sector_device(entry, label, device_id),
        )
        self._sector_idx = sector_idx
        self._attr_name = "Closest Strike"
        self._attr_native_unit_of_measurement = dist_unit

    @property
    def native_value(self) -> float | None:
        return self.data.sectors[self._sector_idx].closest_distance


class SectorTrendSensor(StormTrackerSensorBase):
    """Trend state for one sector."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_icon = "mdi:trending-up"
    _attr_options = TREND_STATES
    _attr_translation_key = "sector_trend"

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        sector_idx: int,
        label: str,
        device_id: str,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            f"sector_{label.lower()}_trend",
            _sector_device(entry, label, device_id),
        )
        self._sector_idx = sector_idx
        self._attr_name = "Trend"

    @property
    def native_value(self) -> str:
        return self.data.sectors[self._sector_idx].trend

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sector = self.data.sectors[self._sector_idx]
        unit = (
            UNIT_MILES
            if self._entry.options.get(CONF_UNIT_SYSTEM, self._entry.data.get(CONF_UNIT_SYSTEM, DEFAULT_UNIT_SYSTEM)) == UNIT_IMPERIAL
            else UNIT_KILOMETERS
        )
        attrs: dict[str, Any] = {
            "direction": SECTOR_LABELS[self._sector_idx],
            "closest_distance": sector.closest_distance,
            "distance_unit": unit,
            "strike_count": sector.strike_count,
        }
        if sector.nearest_city is not None:
            attrs["nearest_city"] = sector.nearest_city
        return attrs


# ---------------------------------------------------------------------------
# Summary sensors
# ---------------------------------------------------------------------------

class SummaryTotalStrikeCountSensor(StormTrackerSensorBase):
    """Total strike count across all sectors."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "strikes"
    _attr_icon = "mdi:lightning-bolt"
    _attr_translation_key = "total_strike_count"

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        device_id: str,
    ) -> None:
        super().__init__(
            coordinator, entry, "total_strike_count", _summary_device(entry, device_id)
        )
        self._attr_name = "Total Strike Count"

    @property
    def native_value(self) -> int:
        return self.data.total_strike_count


class SummaryClosestDistanceSensor(StormTrackerSensorBase):
    """Globally closest strike distance."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-distance"
    _attr_translation_key = "closest_distance"

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        device_id: str,
        dist_unit: str,
    ) -> None:
        super().__init__(
            coordinator, entry, "closest_distance", _summary_device(entry, device_id)
        )
        self._attr_name = "Closest Strike"
        self._attr_native_unit_of_measurement = dist_unit

    @property
    def native_value(self) -> float | None:
        return self.data.closest_distance


class SummaryClosestSectorSensor(StormTrackerSensorBase):
    """Compass label of the sector containing the closest strike."""

    _attr_icon = "mdi:compass"
    _attr_translation_key = "closest_sector"

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        device_id: str,
    ) -> None:
        super().__init__(
            coordinator, entry, "closest_sector", _summary_device(entry, device_id)
        )
        self._attr_name = "Closest Sector"

    @property
    def native_value(self) -> str | None:
        return self.data.closest_sector


class SummaryActiveSectorCountSensor(StormTrackerSensorBase):
    """Number of sectors with at least one strike."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "sectors"
    _attr_icon = "mdi:weather-lightning"
    _attr_translation_key = "active_sector_count"

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        device_id: str,
    ) -> None:
        super().__init__(
            coordinator, entry, "active_sector_count", _summary_device(entry, device_id)
        )
        self._attr_name = "Active Sectors"

    @property
    def native_value(self) -> int:
        return self.data.active_sector_count


class SummaryApproachingSectorCountSensor(StormTrackerSensorBase):
    """Number of sectors with trend = approaching."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "sectors"
    _attr_icon = "mdi:arrow-collapse-all"
    _attr_translation_key = "approaching_sector_count"

    def __init__(
        self,
        coordinator: StormTrackerCoordinator,
        entry: ConfigEntry,
        device_id: str,
    ) -> None:
        super().__init__(
            coordinator, entry, "approaching_sector_count", _summary_device(entry, device_id)
        )
        self._attr_name = "Approaching Sectors"

    @property
    def native_value(self) -> int:
        return self.data.approaching_sector_count
