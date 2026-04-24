# Storm Tracker

A Home Assistant custom integration that provides sector-based lightning storm situational awareness, paired with a custom Lovelace card for dashboard visualization.

---

## Overview

Storm Tracker divides the area around your home into 8 compass sectors and analyzes lightning strike `geo_location` entities to determine whether storms in each sector are approaching, receding, stationary, or absent. It is designed to work alongside (but not depend on) the [Blitzortung](https://github.com/mrk-its/homeassistant-blitzortung) Home Assistant integration, or any other integration that produces `geo_location` entities for lightning strikes.

---

## Features

- 8 fixed compass sectors (N, NE, E, SE, S, SW, W, NW)
- Per-sector sensors: strike count, average distance, closest distance, trend state
- Summary sensors: total strike count, closest strike overall, active sector count, approaching sector count
- Configurable time window, update interval, and approach/recede threshold
- Configurable units (miles or kilometers)
- Custom Lovelace radial radar card with color-coded trend states and strike data labels
- **Map card integration** — centroid and leading-edge pins appear on the HA Map Card under "Data provided by Storm Tracker" alongside Blitzortung strike dots
- Trend algorithm uses `publication_date` timestamps and time-bucket centroid regression to eliminate spurious slopes from simultaneous burst strikes
- Integration-agnostic: works with any `geo_location` provider

---

## Requirements

- Home Assistant 2024.1.0 or later
- A `geo_location` platform providing lightning strike entities (e.g. Blitzortung)
- HACS (for installation)

---

## Repository Structure

```
storm-tracker/
├── README.md
├── SPEC.md                          # Full technical specification
├── CHANGELOG.md
├── hacs.json                        # HACS metadata
└── custom_components/
    └── storm_tracker/
        ├── __init__.py              # Integration setup, card registration
        ├── manifest.json            # Integration metadata
        ├── config_flow.py           # UI configuration flow
        ├── coordinator.py           # Data polling, sector math, trend algorithm
        ├── sensor.py                # Sensor entity definitions
        ├── geo_location.py          # Map pin entity definitions
        ├── const.py                 # Constants
        ├── storm-tracker-card.js    # Lovelace card (served via static path)
        ├── strings.json             # UI strings
        └── translations/
            └── en.json
```

---

## Installation

### Via HACS (recommended)
_Not yet available — pending initial release._

### Manual
1. Copy `custom_components/storm_tracker/` into your HA `custom_components/` directory
2. Restart Home Assistant
3. Add the integration: **Settings → Devices & Services → Add Integration → Storm Tracker**

The Lovelace card is served automatically by the integration — no separate resource registration required.

---

## Configuration

Configuration is handled entirely through the UI config flow. See [SPEC.md](SPEC.md) for full parameter documentation.

### Key parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Unit system | Imperial | Miles or kilometers |
| Geo location prefix | `blitzortung` | Domain prefix to filter strike entities |
| Time window | 30 min | Lookback window for strike history and trend regression |
| Update interval | 30 sec | How often to poll geo_location entities |
| Approach threshold | 10.0 | Min rate of change (units/hr) to classify as approaching or receding |

---

## Lovelace Card

```yaml
type: custom:storm-tracker-card
title: Storm Tracker
entity_prefix: storm_tracker
colors:
  approaching: "#cc2200"
  receding:    "#0066aa"
  stationary:  "#cc6600"
  clear:       "#1e2a1e"
```

The card displays a radial SVG radar with 8 color-coded wedge sectors. Active sectors show strike count and closest distance inside the wedge. A legend appears below the radar.

---

## Map Card

After setup, open your HA Map Card configuration and enable **"Data provided by Storm Tracker"** under Geo Location Sources. Each active sector will show two pins:

- **Centroid** (`mdi:weather-lightning`) — mean position of all strikes in the sector over the last 10 minutes
- **Edge** (`mdi:flash-alert`) — position of the closest strike in the sector

Both pins carry a `trend` attribute showing the current sector state.

---

## Credits

The `geo_location` entity lifecycle pattern used in this integration (dispatcher-based removal, manager class, `async_remove(force_remove=True)`) is adapted from the [homeassistant-blitzortung](https://github.com/mrk-its/homeassistant-blitzortung) integration by [Marcin Kowalski (mrk-its)](https://github.com/mrk-its), used under the MIT License.

---

## License

MIT
