# Storm Tracker

A Home Assistant custom integration that provides sector-based lightning storm situational awareness, paired with a custom Lovelace card for dashboard visualization.

---

## Overview

Storm Tracker divides the area around your home into 8 compass sectors and analyzes lightning strike geo_location entities to determine whether storms in each sector are approaching, receding, stationary, or absent. It is designed to work alongside (but not depend on) the [Blitzortung](https://github.com/mrk-its/homeassistant-blitzortung) Home Assistant integration, or any other integration that produces `geo_location` entities for lightning strikes.

---

## Features

- 8 fixed compass sectors (N, NE, E, SE, S, SW, W, NW)
- Per-sector sensors: strike count, average distance, closest distance, trend state
- Summary sensors: total strike count, closest strike overall, active sector count
- Configurable time window, update interval, and approach/recede threshold
- Configurable units (miles or kilometers)
- Custom Lovelace card with radial sector display, distance rings, and color-coded trend states
- Integration-agnostic: works with any `geo_location` provider

---

## Requirements

- Home Assistant (version TBD — target current stable at time of release)
- A `geo_location` platform providing lightning strike entities (e.g. Blitzortung)
- HACS (for installation of both the integration and the Lovelace card)

---

## Repository Structure

```
storm-tracker/
├── README.md
├── SPEC.md                          # Full technical specification
├── CHANGELOG.md
├── hacs.json                        # HACS metadata
├── custom_components/
│   └── storm_tracker/
│       ├── __init__.py              # Integration setup
│       ├── manifest.json            # Integration metadata
│       ├── config_flow.py           # UI configuration flow
│       ├── coordinator.py           # Data polling + sector math
│       ├── sensor.py                # Sensor entity definitions
│       ├── const.py                 # Constants
│       ├── strings.json             # UI strings
│       └── translations/
│           └── en.json
└── www/
    └── storm-tracker-card/
        ├── storm-tracker-card.js    # Lovelace card
        └── README.md                # Card-specific docs
```

---

## Installation

### Via HACS (recommended)
_Not yet available — pending initial release._

### Manual
1. Copy `custom_components/storm_tracker/` into your HA `custom_components/` directory
2. Copy `www/storm-tracker-card/storm-tracker-card.js` into your HA `www/` directory
3. Add the card resource in HA: **Settings → Dashboards → Resources**
4. Restart Home Assistant
5. Add the integration: **Settings → Devices & Services → Add Integration → Storm Tracker**

---

## Configuration

Configuration is handled entirely through the UI config flow. See [SPEC.md](SPEC.md) for full parameter documentation.

---

## Lovelace Card

```yaml
type: custom:storm-tracker-card
title: Storm Tracker
entity_prefix: storm_tracker
rings: [50, 100, 150, 200]
colors:
  approaching: "#ff0000"
  receding: "#ffff00"
  stationary: "#ff8800"
  clear: "#333333"
```

See [www/storm-tracker-card/README.md](www/storm-tracker-card/README.md) for full card documentation.

---

## License

MIT
