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
    BURST_WINDOW_SECONDS,
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
    MIN_TREND_BUCKETS,
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
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    edge_lat: float | None = None
    edge_lon: float | None = None


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
    """Return OLS slope for (x, y) pairs, or None if fewer than 2 points.

    Negative slope → distance decreasing over time → storm approaching.
    Positive slope → distance increasing over time → storm receding.
    """
    n = len(points)
    if n < 2:
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


def _group_by_time_bucket(
    raw: list[tuple[float, float]],
) -> list[tuple[float, float, float]]:
    """Collapse (timestamp_sec, distance) pairs into time buckets.

    Strikes whose timestamps fall within BURST_WINDOW_SECONDS of the first
    strike in a group are merged into one sample.  Returns a list of
    (mean_timestamp_sec, centroid_distance, leading_edge_distance) — one
    entry per bucket.  Collapsing burst strikes eliminates spurious slopes
    caused by near-simultaneous bolts having slightly different distances.
    """
    if not raw:
        return []
    sorted_raw = sorted(raw, key=lambda p: p[0])
    buckets: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = [sorted_raw[0]]
    for pt in sorted_raw[1:]:
        if pt[0] - current[0][0] <= BURST_WINDOW_SECONDS:
            current.append(pt)
        else:
            buckets.append(current)
            current = [pt]
    buckets.append(current)

    result = []
    for bucket in buckets:
        times = [p[0] for p in bucket]
        dists = [p[1] for p in bucket]
        result.append((sum(times) / len(times), sum(dists) / len(dists), min(dists)))
    return result


def _combined_trend(
    centroid_slope: float | None,
    edge_slope: float | None,
    threshold: float,
) -> str:
    """Classify trend from centroid and leading-edge regression slopes.

    Conservative toward APPROACHING: a single approaching signal is enough to
    warn.  Conservative toward RECEDING: both signals must agree before the
    storm is dismissed as moving away.
    """
    def _classify(slope: float | None) -> str | None:
        if slope is None:
            return None
        if slope < -threshold:
            return TREND_APPROACHING
        if slope > threshold:
            return TREND_RECEDING
        return TREND_STATIONARY

    c = _classify(centroid_slope)
    e = _classify(edge_slope)

    if c is None and e is None:
        return TREND_STATIONARY
    if c is None:
        return e
    if e is None:
        return c
    if TREND_APPROACHING in (c, e):
        return TREND_APPROACHING
    if c == TREND_RECEDING and e == TREND_RECEDING:
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

        all_geo = self.hass.states.async_all("geo_location")
        _LOGGER.debug(
            "Poll: found %d total geo_location entities, prefix filter=%r, cutoff=%s",
            len(all_geo), prefix, cutoff.isoformat(),
        )

        strikes: list[_Strike] = []
        skipped_prefix = 0
        skipped_window = 0

        for state in all_geo:
            # Platform filter — geo_location events are transient and typically
            # have no entity registry entry.  We check three things in order:
            #   1. entity registry platform (e.g. "blitzortung")
            #   2. entity_id slug        (e.g. "lightning_strike_*")
            #   3. source attribute      (e.g. source: "blitzortung")
            # Any one match is sufficient.
            reg_entry = ent_reg.async_get(state.entity_id)
            platform    = (reg_entry.platform if reg_entry else "").lower()
            slug        = state.entity_id.split(".", 1)[1] if "." in state.entity_id else ""
            source_attr = state.attributes.get("source", "").lower()

            if not (
                platform.startswith(prefix)
                or slug.startswith(prefix)
                or source_attr.startswith(prefix)
            ):
                _LOGGER.debug(
                    "Skipping %s — platform=%r slug=%r source=%r does not match prefix %r",
                    state.entity_id, platform, slug, source_attr, prefix,
                )
                skipped_prefix += 1
                continue

            # Time window filter
            last_changed = state.last_changed
            if last_changed is None or last_changed < cutoff:
                _LOGGER.debug(
                    "Skipping %s — last_changed %s is outside window",
                    state.entity_id,
                    last_changed.isoformat() if last_changed else "None",
                )
                skipped_window += 1
                continue

            # Use publication_date (actual strike time) as the timestamp so
            # the time axis reflects when the bolt occurred, not when HA received
            # the entity.  Blitzortung batches delivery, so last_changed is often
            # identical for many strikes and collapses the regression time axis.
            pub_time = last_changed
            pub_str = state.attributes.get("publication_date")
            if pub_str:
                try:
                    pub_time = datetime.fromisoformat(pub_str)
                except (ValueError, TypeError):
                    pass

            strikes.append((state.entity_id, dict(state.attributes), pub_time))

        _LOGGER.info(
            "Snapshot: %d strikes accepted, %d skipped (prefix), %d skipped (time window)",
            len(strikes), skipped_prefix, skipped_window,
        )
        return strikes

    def _compute(self, snapshot: list[_Strike]) -> StormTrackerData:
        """Compute sector statistics from pre-snapshotted strike data.

        Runs in an executor thread — must not access the HA state machine.

        Trend algorithm:
          1. Use publication_date (actual strike time) as the time axis so that
             Blitzortung batch-delivery doesn't collapse all points to t=0.
          2. Group strikes per sector into BURST_WINDOW_SECONDS time buckets.
             Each bucket produces one centroid sample (mean distance) and one
             leading-edge sample (min distance).
          3. Run OLS regression independently on each series.
          4. Classify via _combined_trend — conservative toward APPROACHING.
        """
        home_lat: float = self.hass.config.latitude
        home_lon: float = self.hass.config.longitude
        imperial: bool = self.unit_system == UNIT_IMPERIAL
        threshold = self.approach_threshold

        # Anchor t0 to the oldest publication time so hours_offset is always >= 0.
        if snapshot:
            t0 = min(ts.timestamp() for _, _, ts in snapshot)
        else:
            t0 = 0.0

        # Collect raw (timestamp_sec, distance) per sector before bucketing.
        # Also collect (distance, lat, lon) per sector for centroid/edge map positions.
        sector_raw: dict[int, list[tuple[float, float]]] = {i: [] for i in range(8)}
        sector_coords: dict[int, list[tuple[float, float, float]]] = {i: [] for i in range(8)}

        for entity_id, attrs, pub_time in snapshot:
            try:
                strike_lat = float(attrs["latitude"])
                strike_lon = float(attrs["longitude"])
            except (KeyError, TypeError, ValueError):
                _LOGGER.debug("Skipping %s — missing lat/lon", entity_id)
                continue

            # Distance — Blitzortung provides distance in km via the attribute.
            # Convert to miles here if imperial; do NOT apply a second conversion
            # later.  Fall back to Haversine (already unit-aware) if missing.
            raw_dist = attrs.get("distance")
            distance: float | None = None
            if raw_dist is not None:
                try:
                    km_dist = float(raw_dist)
                    distance = km_dist * 0.621371 if imperial else km_dist
                except (TypeError, ValueError):
                    distance = None

            if distance is None:
                distance = _haversine(home_lat, home_lon, strike_lat, strike_lon, imperial)

            az = _azimuth(home_lat, home_lon, strike_lat, strike_lon)
            sector = _sector_index(az)
            sector_raw[sector].append((pub_time.timestamp(), distance))
            sector_coords[sector].append((distance, strike_lat, strike_lon))

        # Build SectorData per sector
        data = StormTrackerData()
        global_distances: list[float] = []

        for idx, raw_points in sector_raw.items():
            if not raw_points:
                data.sectors[idx] = SectorData()
                continue

            distances = [p[1] for p in raw_points]
            count = len(distances)
            avg_dist = sum(distances) / count
            closest = min(distances)

            buckets = _group_by_time_bucket(raw_points)

            if len(buckets) >= MIN_TREND_BUCKETS:
                centroid_pts = [((b[0] - t0) / 3600.0, b[1]) for b in buckets]
                edge_pts     = [((b[0] - t0) / 3600.0, b[2]) for b in buckets]
                trend = _combined_trend(
                    _linear_slope(centroid_pts),
                    _linear_slope(edge_pts),
                    threshold,
                )
            else:
                trend = TREND_STATIONARY

            # Map positions: centroid = mean lat/lon; edge = lat/lon of closest strike.
            coords = sector_coords[idx]
            centroid_lat = sum(c[1] for c in coords) / len(coords)
            centroid_lon = sum(c[2] for c in coords) / len(coords)
            edge_coord   = min(coords, key=lambda c: c[0])

            data.sectors[idx] = SectorData(
                strike_count=count,
                avg_distance=round(avg_dist, 1),
                closest_distance=round(closest, 1),
                trend=trend,
                centroid_lat=centroid_lat,
                centroid_lon=centroid_lon,
                edge_lat=edge_coord[1],
                edge_lon=edge_coord[2],
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

        _LOGGER.info(
            "Compute: %d total strikes, %d active sectors, closest=%.1f (%s)",
            data.total_strike_count,
            data.active_sector_count,
            data.closest_distance or 0,
            data.closest_sector or "none",
        )
        return data
