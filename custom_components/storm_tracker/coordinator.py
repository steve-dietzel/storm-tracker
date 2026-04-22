"""Data coordinator for Storm Tracker."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import atan2, cos, pi, radians, sin, sqrt
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_APPROACH_THRESHOLD,
    CONF_GEO_LOCATION_PREFIX,
    CONF_TIME_WINDOW_MINUTES,
    CONF_UNIT_SYSTEM,
    DEFAULT_APPROACH_THRESHOLD,
    DEFAULT_GEO_LOCATION_PREFIX,
    DEFAULT_TIME_WINDOW_MINUTES,
    DEFAULT_UNIT_SYSTEM,
    DOMAIN,
    EARTH_RADIUS_KM,
    EARTH_RADIUS_MI,
    MIN_TREND_POINTS,
    SECTOR_LABELS,
    TREND_APPROACHING,
    TREND_CLEAR,
    TREND_RECEDING,
    TREND_STATIONARY,
    UNIT_IMPERIAL,
)

_LOGGER = logging.getLogger(__name__)

# Type alias for a pre-snapshotted strike record
_Strike = tuple[str, dict[str, Any], datetime]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SectorData:
    """Computed statistics for one compass sector."""

    strike_count: int = 0
    avg_distance: float | None = None
    closest_distance: float | None = None
    trend: str = TREND_CLEAR


@dataclass
class StormTrackerData:
    """Full dataset produced by one coordinator refresh."""

    sectors: dict[int, SectorData] = field(
        default_factory=lambda: {i: SectorData() for i in range(8)}
    )
    total_strike_count: int = 0
    closest_distance: float | None = None
    closest_sector: str | None = None
    active_sector_count: int = 0
    approaching_sector_count: int = 0


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _azimuth(home_lat: float, home_lon: float, strike_lat: float, strike_lon: float) -> float:
    """Return bearing in degrees (0–360) from home to strike."""
    dy = (strike_lat - home_lat) * pi / 180
    dx = (strike_lon - home_lon) * pi / 180 * cos(home_lat * pi / 180)
    return (atan2(dx, dy) * 180 / pi) % 360


def _sector_index(azimuth: float) -> int:
    """Map an azimuth (0–360) to a sector index (0–7)."""
    return int((azimuth + 22.5) / 45) % 8


def _haversine(
    lat1: float, lon1: float, lat2: float, lon2: float, imperial: bool
) -> float:
    """Return great-circle distance between two points."""
    r = EARTH_RADIUS_MI if imperial else EARTH_RADIUS_KM
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    # Clamp to [0, 1] to guard against floating-point values slightly outside
    # the domain of sqrt, which would raise ValueError for near-antipodal points.
    a = max(0.0, min(1.0, a))
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def _linear_slope(points: list[tuple[float, float]]) -> float | None:
    """Return slope of linear regression on (x, y) pairs, or None if degenerate."""
    n = len(points)
    if n < MIN_TREND_POINTS:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    numer = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    return numer / denom


def _trend_state(
    points: list[tuple[float, float]], threshold: float
) -> str:
    """Compute trend state from (timestamp_hours, distance) pairs."""
    count = len(points)
    if count == 0:
        return TREND_CLEAR
    slope = _linear_slope(points)
    if slope is None:
        return TREND_STATIONARY
    if slope < -threshold:
        return TREND_APPROACHING
    if slope > threshold:
        return TREND_RECEDING
    return TREND_STATIONARY


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class StormTrackerCoordinator(DataUpdateCoordinator[StormTrackerData]):
    """Polls geo_location entities and computes per-sector storm statistics."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, update_interval_seconds: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self._entry = entry

    # ------------------------------------------------------------------
    # Properties resolved from entry data + options (options take priority)
    # ------------------------------------------------------------------

    def _opt(self, key: str, default: Any) -> Any:
        return self._entry.options.get(key, self._entry.data.get(key, default))

    @property
    def unit_system(self) -> str:
        return self._opt(CONF_UNIT_SYSTEM, DEFAULT_UNIT_SYSTEM)

    @property
    def geo_location_prefix(self) -> str:
        return self._opt(CONF_GEO_LOCATION_PREFIX, DEFAULT_GEO_LOCATION_PREFIX)

    @property
    def time_window_minutes(self) -> int:
        return int(self._opt(CONF_TIME_WINDOW_MINUTES, DEFAULT_TIME_WINDOW_MINUTES))

    @property
    def approach_threshold(self) -> float:
        return float(self._opt(CONF_APPROACH_THRESHOLD, DEFAULT_APPROACH_THRESHOLD))

    # ------------------------------------------------------------------
    # Core update — two-phase: snapshot on event loop, compute in executor
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> StormTrackerData:
        """Snapshot HA state on the event loop, then compute in an executor."""
        try:
            # Phase 1: read HA state machine on the event loop (thread-unsafe to do elsewhere)
            snapshot = self._build_snapshot()
            # Phase 2: pure math — safe to run off the event loop
            return await self.hass.async_add_executor_job(self._compute, snapshot)
        except Exception as exc:
            raise UpdateFailed(f"Storm Tracker update failed: {exc}") from exc

    def _build_snapshot(self) -> list[_Strike]:
        """Collect matching geo_location states on the event loop thread.

        Returns a list of (entity_id, attributes_copy, last_changed) tuples
        containing only the data needed for sector math.  Copying attributes
        avoids holding live State references outside the event loop.
        """
        ent_reg = er.async_get(self.hass)
        prefix = self.geo_location_prefix.lower()
        cutoff = dt_util.utcnow() - timedelta(minutes=self.time_window_minutes)

        strikes: list[_Strike] = []
        for state in self.hass.states.async_all("geo_location"):
            # Platform filter
            reg_entry = ent_reg.async_get(state.entity_id)
            platform = (reg_entry.platform if reg_entry else "").lower()
            entity_id_prefix = (
                state.entity_id.split(".")[1].split("_")[0]
                if "." in state.entity_id
                else ""
            )
            if not (platform.startswith(prefix) or entity_id_prefix.startswith(prefix)):
                continue

            # Time window filter
            last_changed = state.last_changed
            if last_changed is None or last_changed < cutoff:
                continue

            strikes.append((state.entity_id, dict(state.attributes), last_changed))

        return strikes

    def _compute(self, snapshot: list[_Strike]) -> StormTrackerData:
        """Compute sector statistics from pre-snapshotted strike data.

        Runs in an executor thread — must not access the HA state machine.
        """
        home_lat: float = self.hass.config.latitude
        home_lon: float = self.hass.config.longitude
        imperial: bool = self.unit_system == UNIT_IMPERIAL
        threshold = self.approach_threshold

        t0: float | None = None
        sector_points: dict[int, list[tuple[float, float]]] = {i: [] for i in range(8)}

        for entity_id, attrs, last_changed in snapshot:
            # Coordinates
            try:
                strike_lat = float(attrs["latitude"])
                strike_lon = float(attrs["longitude"])
            except (KeyError, TypeError, ValueError):
                _LOGGER.debug("Skipping %s — missing lat/lon", entity_id)
                continue

            # Distance (with Haversine fallback)
            raw_dist = attrs.get("distance")
            distance: float | None = None
            if raw_dist is not None:
                try:
                    distance = float(raw_dist)
                    if imperial:
                        distance = distance * 0.621371
                except (TypeError, ValueError):
                    distance = None

            if distance is None:
                distance = _haversine(home_lat, home_lon, strike_lat, strike_lon, imperial)

            # Azimuth + sector assignment
            az = _azimuth(home_lat, home_lon, strike_lat, strike_lon)
            sector = _sector_index(az)

            # Timestamp offset in hours (relative to first strike seen this cycle)
            ts = last_changed.timestamp()
            if t0 is None:
                t0 = ts
            hours_offset = (ts - t0) / 3600.0

            sector_points[sector].append((hours_offset, distance))

        # Build SectorData per sector
        data = StormTrackerData()
        global_distances: list[float] = []

        for idx, points in sector_points.items():
            if not points:
                data.sectors[idx] = SectorData()
                continue

            distances = [p[1] for p in points]
            count = len(distances)
            avg_dist = sum(distances) / count
            closest = min(distances)
            trend = _trend_state(points, threshold)

            data.sectors[idx] = SectorData(
                strike_count=count,
                avg_distance=round(avg_dist, 1),
                closest_distance=round(closest, 1),
                trend=trend,
            )
            global_distances.extend(distances)

        # Summary
        data.total_strike_count = sum(s.strike_count for s in data.sectors.values())
        data.active_sector_count = sum(
            1 for s in data.sectors.values() if s.strike_count > 0
        )
        data.approaching_sector_count = sum(
            1 for s in data.sectors.values() if s.trend == TREND_APPROACHING
        )

        if global_distances:
            data.closest_distance = round(min(global_distances), 1)
            min_dist = data.closest_distance
            for idx, s in data.sectors.items():
                if s.closest_distance is not None and round(s.closest_distance, 1) == min_dist:
                    data.closest_sector = SECTOR_LABELS[idx]
                    break

        return data
