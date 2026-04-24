# Storm Tracker — Technical Specification

**Version:** 0.2.0-dev
**Last Updated:** April 24, 2026
**Status:** Active development

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [Architecture](#3-architecture)
4. [Data Source](#4-data-source)
5. [Sector Definition](#5-sector-definition)
6. [Trend Algorithm](#6-trend-algorithm)
7. [Entity Model](#7-entity-model)
8. [Config Flow](#8-config-flow)
9. [Lovelace Card](#9-lovelace-card)
10. [Map Integration](#10-map-integration)
11. [Open Questions](#11-open-questions)

---

## 1. Problem Statement

The Blitzortung Home Assistant integration provides a single "Lightning Trend" sensor derived from a derivative of the distance sensor. This approach has two fundamental problems:

1. **It tracks only the most recent strike**, not a history of strikes — making the derivative extremely noisy when strikes are sparse or scattered across multiple cells.
2. **It cannot distinguish multiple storm cells** — a squall line 100 miles long and a discrete cell 100 miles away produce indistinguishable output.

With strike-only data (no radar reflectivity), reliably identifying discrete storm cells is mathematically intractable. However, **sector-based situational awareness** is tractable and practically useful: dividing the area around the home into 8 compass sectors and tracking strike density, distance, and trend per sector gives actionable information about what is approaching, what is receding, and where activity is concentrated.

---

## 2. Goals & Non-Goals

### Goals
- Provide per-sector lightning situational awareness
- Expose clean sensor entities suitable for HA automations
- Provide a custom Lovelace card for radial dashboard visualization
- Place sector centroid and leading-edge map pins on the HA Map Card
- Be integration-agnostic (work with any `geo_location` lightning provider)
- All parameters configurable via UI (no YAML required)

### Non-Goals
- Discrete storm cell identification or tracking
- Direct MQTT connection to Blitzortung or any external service
- Radar data integration
- Storm path prediction
- Mobile notifications (handled by user automations against exposed sensors)

---

## 3. Architecture

```
geo_location entities (any provider)
    ↓ filtered by domain prefix (e.g. "blitzortung")
    ↓ polled every N seconds by coordinator
Storm Tracker Coordinator
    ↓ reads latitude, longitude, distance, publication_date from each entity
    ↓ calculates azimuth from home coords to each strike
    ↓ assigns each strike to a sector (0–360° / 8 = 45° per sector)
    ↓ groups strikes into 60-second time buckets per sector
    ↓ runs dual OLS regression (centroid + leading edge) per sector
    ↓ classifies trend per sector
    ↓ writes HA sensor states + geo_location map pins
8x Sector Devices + Sensors
    +
1x Summary Device + Sensors
    +
Up to 16x Geo Location Entities (2 per active sector)
    ↓
Custom Lovelace Card + HA Map Card
```

### Key Design Decisions

- **No external dependencies** beyond HA core and a geo_location provider
- **Poll-based**, not event-driven — simplifies state management; 30-second interval is sufficient for storm-scale tracking
- **Home coordinates** sourced from HA's own `hass.config.latitude` / `hass.config.longitude` — no user input needed
- **Azimuth calculated internally** from home lat/lon to strike lat/lon using standard bearing formula
- **Two-phase coordinator** — snapshot reads HA state on the event loop; compute runs in an executor thread (pure math, no HA state access)
- **publication_date used for timestamps** — Blitzortung batches delivery so `last_changed` is identical for many strikes; `publication_date` is the actual bolt time

---

## 4. Data Source

### geo_location Entities

Storm Tracker reads all active `geo_location` entities from the HA state machine whose platform, entity_id slug, or `source` attribute matches the configured prefix.

**Attributes read from each entity:**

| Attribute | Source | Notes |
|-----------|--------|-------|
| `latitude` | entity attribute | Strike latitude |
| `longitude` | entity attribute | Strike longitude |
| `distance` | entity state | Distance from home in km (converted to miles if imperial) |
| `publication_date` | entity attribute | ISO 8601 timestamp of actual strike; falls back to `last_changed` if absent |

**Azimuth** is calculated by Storm Tracker from home coords + strike lat/lon:

```python
dy = (strike_lat - home_lat) * pi / 180
dx = (strike_lon - home_lon) * pi / 180 * cos(home_lat * pi / 180)
azimuth = (atan2(dx, dy) * 180 / pi) % 360
```

### Domain Prefix Filtering

The user configures a `geo_location_prefix` string (default: `blitzortung`). Storm Tracker accepts an entity if any of the following matches the prefix:
1. Entity registry platform (e.g. `blitzortung`)
2. Entity ID slug (e.g. `lightning_strike_*`)
3. `source` state attribute (e.g. `source: blitzortung`)

---

## 5. Sector Definition

8 fixed compass sectors, each spanning 45°, centered on cardinal and intercardinal directions:

| Sector | Label | Center | Range |
|--------|-------|--------|-------|
| 0 | N  | 0°   | 337.5° – 22.5°  |
| 1 | NE | 45°  | 22.5°  – 67.5°  |
| 2 | E  | 90°  | 67.5°  – 112.5° |
| 3 | SE | 135° | 112.5° – 157.5° |
| 4 | S  | 180° | 157.5° – 202.5° |
| 5 | SW | 225° | 202.5° – 247.5° |
| 6 | W  | 270° | 247.5° – 292.5° |
| 7 | NW | 315° | 292.5° – 337.5° |

```python
sector = int((azimuth + 22.5) / 45) % 8
```

---

## 6. Trend Algorithm

### Overview

Trend classification uses a two-phase approach designed to handle the specific characteristics of Blitzortung data: batched delivery (many strikes arrive simultaneously with the same `last_changed`), and burst lightning (multiple bolts in seconds that don't represent storm movement).

### Phase 1 — Time Bucketing

Strikes within each sector are sorted by `publication_date` and grouped into 60-second buckets (`BURST_WINDOW_SECONDS`). Each bucket produces:
- **Centroid distance** — mean distance of all strikes in the bucket
- **Leading edge distance** — minimum distance of all strikes in the bucket

This collapses burst strikes into single samples, preventing near-simultaneous bolts with slightly different distances from producing spurious regression slopes.

### Phase 2 — Dual OLS Regression

If a sector has at least `MIN_TREND_BUCKETS = 2` distinct time buckets, two independent linear regressions are run:

```
centroid_slope  = OLS slope of (hours_offset, centroid_distance) pairs
edge_slope      = OLS slope of (hours_offset, leading_edge_distance) pairs
```

Where `hours_offset` is seconds since the oldest strike in the snapshot, converted to hours. Anchoring to the oldest strike ensures offsets are always ≥ 0, preserving slope sign.

**Slope sign convention:**
- Negative slope → distance decreasing → storm approaching
- Positive slope → distance increasing → storm receding

### Phase 3 — Combined Classification

```
_classify(slope):
    if slope < -threshold:  → APPROACHING
    if slope > +threshold:  → RECEDING
    else:                   → STATIONARY

combined:
    if either signal = APPROACHING  → APPROACHING
    if either signal = RECEDING     → RECEDING
    else                            → STATIONARY
```

Conservative toward APPROACHING: one signal is enough to warn. APPROACHING takes priority over RECEDING if signals conflict.

### Insufficient Data Fallback

If a sector has fewer than `MIN_TREND_BUCKETS` distinct time buckets (e.g. all strikes arrived in a single burst), regression is not attempted. Instead:
- If the sector had a non-CLEAR trend in the previous refresh, that trend is carried forward.
- If no previous trend exists (new activity), defaults to STATIONARY.

This prevents a briefly-quiet approaching storm from flipping to stationary just because it hasn't struck again yet.

### Parameters

| Constant | Value | Description |
|----------|-------|-------------|
| `BURST_WINDOW_SECONDS` | 60 | Max time spread within a single bucket |
| `MIN_TREND_BUCKETS` | 2 | Minimum buckets required for regression |
| `DEFAULT_APPROACH_THRESHOLD` | 10.0 | Min slope magnitude (units/hr) for approaching/receding |
| `CENTROID_WINDOW_MINUTES` | 10 | Time window for centroid/edge map position calculation |

---

## 7. Entity Model

### Sector Devices (8 total)

One HA device per sector, named e.g. `Storm Tracker NE`.

**Sensors per sector device:**

| Entity ID | Name | Unit | Notes |
|-----------|------|------|-------|
| `sensor.storm_tracker_ne_strike_count` | Strike Count | strikes | All strikes in time window |
| `sensor.storm_tracker_ne_avg_distance` | Avg Distance | mi or km | Mean distance |
| `sensor.storm_tracker_ne_closest_distance` | Closest Strike | mi or km | Minimum distance |
| `sensor.storm_tracker_ne_trend` | Trend | — | approaching / receding / stationary / clear |

### Summary Device (1 total)

One HA device named `Storm Tracker`.

**Sensors:**

| Entity ID | Name | Unit | Notes |
|-----------|------|------|-------|
| `sensor.storm_tracker_total_strike_count` | Total Strike Count | strikes | Sum across all sectors |
| `sensor.storm_tracker_closest_distance` | Closest Strike | mi or km | Global minimum |
| `sensor.storm_tracker_closest_sector` | Closest Sector | — | e.g. "SW" |
| `sensor.storm_tracker_active_sector_count` | Active Sectors | sectors | Sectors with count > 0 |
| `sensor.storm_tracker_approaching_sector_count` | Approaching Sectors | sectors | Sectors with trend = approaching |

---

## 8. Config Flow

### Step 1 — Basic Settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string | "Storm Tracker" | Integration instance name |
| `unit_system` | select | "imperial" | imperial (miles) or metric (km) |

### Step 2 — Data Source

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `geo_location_prefix` | string | "blitzortung" | Domain prefix to filter geo_location entities |

### Step 3 — Timing & Thresholds

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `time_window_minutes` | int | 30 | Lookback window for strike history and trend regression |
| `update_interval_seconds` | int | 30 | How often to poll geo_location entities |
| `approach_threshold` | float | 10.0 | Min rate of change (units/hr) to classify as approaching or receding |

### Options Flow

All Step 2 and Step 3 parameters are reconfigurable via the integration's Options flow without requiring removal and re-add.

---

## 9. Lovelace Card

### Card Registration

Registered as `custom:storm-tracker-card`. Delivered as a single JS file at `custom_components/storm_tracker/storm-tracker-card.js`, served via HA's static path registration in `async_setup`. No manual resource registration required.

### Card Configuration

```yaml
type: custom:storm-tracker-card
title: Storm Tracker          # optional, default: "Storm Tracker"
entity_prefix: storm_tracker  # must match integration's entity prefix
colors:
  approaching: "#cc2200"
  receding:    "#0066aa"
  stationary:  "#cc6600"
  clear:       "#1e2a1e"
```

### Visual Design

- Circular radial SVG display
- 8 wedge sectors, each spanning 45°, labeled with compass direction
- Each wedge filled with color corresponding to trend state; text color auto-computed for legibility
- Per-wedge labels showing strike count and closest distance (only when strikes > 0)
- North oriented to top
- Legend below radar showing trend state colors

### Data Source

Card reads the following entities (constructed from `entity_prefix`):
- `sensor.{prefix}_{sector}_strike_count`
- `sensor.{prefix}_{sector}_closest_strike`
- `sensor.{prefix}_{sector}_trend`

for each sector in: `n, ne, e, se, s, sw, w, nw`

---

## 10. Map Integration

### geo_location Platform

Storm Tracker implements a `geo_location` platform that places map pins on the HA Map Card. Pins appear under the source **"Data provided by Storm Tracker"** and can be toggled in the Map Card's Geo Location Sources configuration.

### Pin Types

For each active sector (strike_count > 0), two pins are placed:

| Type | Icon | Position | Distance attribute |
|------|------|----------|--------------------|
| Centroid | `mdi:weather-lightning` | Mean lat/lon of strikes in last 10 min | Sector avg distance |
| Edge | `mdi:flash-alert` | Lat/lon of closest strike in last 10 min | Sector closest distance |

Both pins carry a `trend` extra state attribute with the current sector trend state.

### Lifecycle

- Pins are created via `async_add_entities` when a sector becomes active.
- Pins are updated in-place (position, distance, trend) on each coordinator refresh.
- Pins are removed via HA dispatcher signal when a sector goes clear.
- At most 16 pins total (2 × 8 sectors).

---

## 11. Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Minimum HA version to target? | Resolved — 2024.1.0 |
| 2 | Should sector count (8) be user-configurable in a future version? | Deferred |
| 3 | How to handle geo_location entities that don't carry a `distance` attribute? | Resolved — Haversine fallback from lat/lon |
| 4 | Should the card support dark/light theme auto-detection? | Resolved — text color computed from background luminance |
| 5 | HACS default category: integration or plugin? | Deferred — integration only for now; card bundled inside |

---

*End of Specification*
