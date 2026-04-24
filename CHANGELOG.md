# Changelog

All notable changes to Storm Tracker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Geo location platform** — each active sector now places two pins on the HA Map Card under the source "Data provided by Storm Tracker": a centroid (mean position of all strikes in the sector) and a leading edge (position of the closest strike). Pins are created, updated, and removed dynamically as sectors activate and clear.
- **Centroid/edge positions** use a 10-minute window so map pins reflect where the storm is now rather than a smeared average over the full 30-minute history.

### Changed
- **Trend algorithm rewritten** — replaced single-pass regression on raw strike timestamps with a two-phase approach:
  1. Use `publication_date` attribute (actual strike time from Blitzortung) instead of `last_changed` (HA receive time). Blitzortung batches delivery, so `last_changed` is identical for many strikes and collapsed the regression time axis.
  2. Group per-sector strikes into 60-second time buckets before regression. Burst strikes (multiple bolts within seconds) become a single centroid sample, eliminating spurious slopes caused by near-simultaneous distance variance.
  3. Run independent OLS regression on both centroid distance and leading-edge (min distance) per bucket.
  4. Combined classification: conservative toward APPROACHING (either signal suffices to warn); either signal RECEDING now returns RECEDING (previously required both to agree).
- **Trend carry-forward** — when a sector has only one time bucket (insufficient temporal spread for regression), the previous trend is now held rather than resetting to stationary. A briefly-quiet approaching storm keeps its last known state until new regression data changes it.
- Distance rings removed from the full radar card (purely decorative with no functional value).
- Card registered with the Lovelace card picker via `window.customCards`.
- Card served directly from `custom_components/storm_tracker/` via static path registration; the `www/storm-tracker-card/` directory has been removed.

### Fixed
- Mixed centroid/edge signals (one RECEDING, one STATIONARY) were collapsing to STATIONARY instead of RECEDING.
- Prefix filtering now checks entity registry platform, entity_id slug, and `source` attribute — fixes default Blitzortung setup where no entity registry entry exists.
- Threading safety in coordinator (HA state machine reads isolated to event loop thread).
- Haversine domain error for near-antipodal points.
- XSS: entity state values HTML-escaped before insertion into SVG.

---

## [0.1.4] — 2026-04-23

### Added
- `source` attribute check added to geo_location prefix filter so the default `blitzortung` prefix works without manual configuration.
- Diagnostic debug logging throughout coordinator snapshot and compute phases.

---

## [0.1.3] — 2026-04-22

### Fixed
- Prefix filtering was not matching Blitzortung entities correctly — now checks platform, slug, and source attribute.

---

## [0.1.2] — 2026-04-22

### Fixed
- Threading safety: HA state machine reads now isolated to the event loop thread via two-phase snapshot/compute pattern.
- Haversine: clamp input to `[0, 1]` to prevent `ValueError` for near-antipodal points.
- XSS: escape all entity state values before SVG insertion.

---

## [0.1.1] — 2026-04-21

### Changed
- Bumped version. Static path registration updated for HA 2024.x using `async_register_static_paths`.

---

## [0.1.0] — 2026-04-20

### Added
- Initial release.
- 8-sector compass-based lightning situational awareness.
- Per-sector sensors: strike count, average distance, closest distance, trend state.
- Summary sensors: total strikes, closest strike, closest sector, active sectors, approaching sectors.
- Linear regression trend classification: approaching / receding / stationary / clear.
- Custom Lovelace radial radar card with SVG wedges, compass labels, and legend.
- UI config flow: unit system, geo_location prefix, time window, update interval, approach threshold.
- Options flow for reconfiguration without re-adding the integration.
- HACS metadata.
