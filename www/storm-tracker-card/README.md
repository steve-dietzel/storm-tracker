# Storm Tracker Card

Custom Lovelace card for the Storm Tracker integration.

## Installation

See the main [README](../../README.md) for installation instructions.

## Configuration

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

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `entity_prefix` | yes | — | Must match the integration's entity prefix |
| `title` | no | "Storm Tracker" | Card title |
| `rings` | no | [50, 100, 150, 200] | Distance rings in configured units |
| `colors.approaching` | no | #ff0000 | Color for approaching sectors |
| `colors.receding` | no | #ffff00 | Color for receding sectors |
| `colors.stationary` | no | #ff8800 | Color for stationary sectors |
| `colors.clear` | no | #333333 | Color for clear sectors |
