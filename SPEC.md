# Storm Tracker — Technical Specification

**Version:** 0.1.0-draft  
**Last Updated:** April 22, 2026  
**Status:** Pre-development

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [Architecture](#3-architecture)
4. [Data Source](#4-data-source)
5. [Sector Definition](#5-sector-definition)
6. [Sensor Math](#6-sensor-math)
7. [Entity Model](#7-entity-model)
8. [Config Flow](#8-config-flow)
9. [Lovelace Card](#9-lovelace-card)
10. [Build Order](#10-build-order)
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
    ↓ reads latitude, longitude, distance from each entity
    ↓ calculates azimuth from home coords to each strike
    ↓ assigns each strike to a sector (0–360° / 8 = 45° per sector)
    ↓ computes per-sector statistics
    ↓ writes HA sensor states
8x Sector Devices + Sensors
    +
1x Summary Device + Sensors
    ↓
Custom Lovelace Card
```

### Key Design Decisions

- **No external dependencies** beyond HA core and a geo_location provider
- **Poll-based**, not event-driven — simplifies state management; 30-second interval is sufficient for storm-scale tracking
- **Home coordinates** sourced from HA's own `hass.config.latitude` / `hass.config.longitude` — no user input needed
- **Azimuth calculated internally** from home lat/lon to strike lat/lon using standard bearing formula — not read from any sensor

---

## 4. Data Source

### geo_location Entities

Storm Tracker reads all active `geo_location` entities from the HA state machine whose `domain` attribute matches the configured prefix.

**Attributes read from each entity:**
| Attribute | Source | Notes |
|-----------|--------|-------|
| `latitude` | entity attribute | Strike latitude |
| `longitude` | entity attribute | Strike longitude |
| `distance` | entity state or attribute | Distance from home in native units |

**Azimuth** is calculated by Storm Tracker from home coords + strike lat/lon:

```python
dy = (strike_lat - home_lat) * pi / 180
dx = (strike_lon - home_lon) * pi / 180 * cos(home_lat * pi / 180)
azimuth = (atan2(dx, dy) * 180 / pi) % 360
```

### Domain Prefix Filtering

The user configures a `geo_location_prefix` string (default: `blitzortung`). Storm Tracker filters to entities where the entity's platform/domain matches this prefix. This ensures only lightning strike entities are processed, not other geo_location providers (e.g. USGS earthquakes).

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

Sector assignment:
```python
sector = int((azimuth + 22.5) / 45) % 8
```

---

## 6. Sensor Math

### Per-Sector Strike Buffer

On each poll, Storm Tracker reads all active geo_location entities and builds a per-sector buffer of `(timestamp, distance)` pairs. Entities older than `time_window_minutes` are excluded (Blitzortung handles expiry of its own entities, but we filter defensively).

### Strike Count
```
count = len(strikes_in_sector)
```

### Average Distance
```
avg_distance = mean(distance for each strike in sector)
```

### Closest Distance
```
closest = min(distance for each strike in sector)
```

### Trend (Linear Regression Slope)

A linear regression is fit to the `(timestamp, distance)` pairs in the sector buffer. The slope represents the rate of change of distance over time in units/hour.

```python
# timestamps normalized to hours
x = [(t - t0) / 3600 for t in timestamps]
y = distances

slope = covariance(x, y) / variance(x)  # units per hour
```

Minimum 3 data points required to compute a meaningful slope. Fewer than 3 → trend state is `stationary` if strikes exist, `clear` if none.

### Trend State

```
if count == 0:
    state = "clear"
elif count < 3:
    state = "stationary"   # insufficient data for trend
elif slope < -threshold:
    state = "approaching"
elif slope > +threshold:
    state = "receding"
else:
    state = "stationary"
```

Where `threshold` is the user-configured approach/recede threshold in units/hour.

---

## 7. Entity Model

### Sector Devices (8 total)

One HA device per sector, named e.g. `Storm Tracker NE`.

**Sensors per sector device:**

| Entity ID | Name | Unit | State Class |
|-----------|------|------|-------------|
| `sensor.storm_tracker_ne_strike_count` | Strike Count | strikes | measurement |
| `sensor.storm_tracker_ne_avg_distance` | Avg Distance | mi or km | measurement |
| `sensor.storm_tracker_ne_closest_distance` | Closest Strike | mi or km | measurement |
| `sensor.storm_tracker_ne_trend` | Trend | — | enum: approaching / receding / stationary / clear |

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
| `time_window_minutes` | int | 30 | Lookback window for strike history |
| `update_interval_seconds` | int | 30 | How often to poll geo_location entities |
| `approach_threshold` | float | 10.0 | Min rate of change (units/hr) to classify as approaching or receding |

### Options Flow (reconfigurable after setup)

All Step 2 and Step 3 parameters are reconfigurable via the integration's Options flow without requiring removal and re-add.

---

## 9. Lovelace Card

### Card Registration

Registered as `custom:storm-tracker-card`. Delivered as a single self-contained JS file at `www/storm-tracker-card/storm-tracker-card.js`.

### Card Configuration

```yaml
type: custom:storm-tracker-card
title: Storm Tracker          # optional, default: "Storm Tracker"
entity_prefix: storm_tracker  # must match integration's entity prefix
rings: [50, 100, 150, 200]    # distance rings to draw (in configured units)
colors:
  approaching: "#ff0000"      # red
  receding: "#ffff00"         # yellow
  stationary: "#ff8800"       # orange
  clear: "#333333"            # dark gray
```

### Visual Design

- Circular radial display
- 8 wedge sectors, each spanning 45°, labeled with compass direction
- Concentric distance rings at configured intervals
- Each wedge filled with color corresponding to trend state
- Per-wedge labels showing:
  - Strike count
  - Closest distance
- Compass direction label at outer edge of each wedge
- North oriented to top

### Data Source

Card reads the following entities (constructed from `entity_prefix`):
- `sensor.{prefix}_{sector}_strike_count`
- `sensor.{prefix}_{sector}_closest_distance`
- `sensor.{prefix}_{sector}_trend`

for each sector in: `n, ne, e, se, s, sw, w, nw`

---

## 10. Build Order

### Phase 1 — Integration Scaffolding
- [ ] `manifest.json`
- [ ] `const.py`
- [ ] `strings.json` + `translations/en.json`
- [ ] `config_flow.py` (3-step flow + options flow)
- [ ] `__init__.py` (setup + unload)

### Phase 2 — Data & Math
- [ ] `coordinator.py`
  - [ ] Poll geo_location entities
  - [ ] Filter by domain prefix
  - [ ] Calculate azimuth per strike
  - [ ] Assign strikes to sectors
  - [ ] Compute per-sector stats
  - [ ] Compute trend via linear regression

### Phase 3 — Sensors
- [ ] `sensor.py`
  - [ ] Sector device + 4 sensors × 8 sectors
  - [ ] Summary device + 5 sensors

### Phase 4 — Lovelace Card
- [ ] `storm-tracker-card.js`
  - [ ] Radial canvas/SVG rendering
  - [ ] Sector coloring
  - [ ] Distance rings
  - [ ] Labels
  - [ ] Config schema

### Phase 5 — Polish
- [ ] `hacs.json`
- [ ] `CHANGELOG.md`
- [ ] Unit tests for coordinator math
- [ ] GitHub Actions CI

---

## 11. Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Minimum HA version to target? | Open |
| 2 | Should sector count (8) be user-configurable in a future version? | Deferred |
| 3 | How to handle geo_location entities that don't carry a `distance` attribute — calculate from lat/lon? | Open |
| 4 | Should the card support dark/light theme auto-detection? | Deferred |
| 5 | HACS default category: integration or plugin? (Need both) | Open |

---

*End of Specification*
