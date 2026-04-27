# Storm Tracker — Claude Code Context

## Project Overview

Home Assistant custom integration providing sector-based lightning storm situational awareness. Analyzes Blitzortung `geo_location` strike entities to classify storm movement (approaching/receding/stationary/clear) per compass sector. Includes custom Lovelace cards and a geo_location map pin platform.

## Repository & Deployment

- **Repo**: `https://github.com/steve-dietzel/storm-tracker`
- **Working directory**: `/opt/storm-tracker` — this IS the live HA device; files here are what HA runs
- **Deploy**: edit files locally → commit → `git push origin main` → create GitHub release → load via HACS in HA
- **HA restart required** for: changes to `__init__.py` (especially `async_setup`), new platforms, new JS files
- **Integration reload sufficient** for: coordinator logic, sensor changes, coordinator-only Python changes

## File Structure

```
custom_components/storm_tracker/
├── __init__.py              # async_setup (card JS registration) + async_setup_entry
├── manifest.json            # version bump needed with each release
├── config_flow.py           # 3-step UI config + options flow
├── coordinator.py           # All trend math, geocoding, snapshot/compute
├── sensor.py                # Sensor entities (sector + summary devices)
├── geo_location.py          # Map pin entities (centroid + edge per sector)
├── const.py                 # All constants — tune here first
├── storm-tracker-card.js    # ALL three Lovelace cards bundled in one file
├── strings.json
└── translations/en.json
```

## Architecture — Key Points

### Two-phase coordinator
- `_build_snapshot()` runs on the HA event loop — reads state machine
- `_compute()` runs in executor thread — pure math, no HA access
- `_async_geocode_centroids()` runs async after compute — HTTP calls via aiohttp

### Trend algorithm
1. Use `publication_date` attribute (actual strike time) not `last_changed` (HA receive time — Blitzortung batches, so last_changed is identical for many strikes)
2. Group per-sector strikes into 60-second time buckets (`BURST_WINDOW_SECONDS`)
3. Dual OLS regression: centroid distance + leading-edge (min) distance per bucket
4. Combined classification: APPROACHING if either signal; RECEDING requires both signals; otherwise STATIONARY
5. If < `MIN_TREND_BUCKETS` distinct buckets, carry previous trend forward (don't reset to stationary)

### Geo location platform
- Centroid pin (`mdi:weather-lightning`) + edge pin (`mdi:flash-alert`) per active sector
- Lifecycle: created on sector activate, updated in-place each refresh, removed via dispatcher signal on clear
- Attribution: "Data provided by Storm Tracker" — appears as separate source in HA Map Card
- Pattern adapted from homeassistant-blitzortung by mrk-its (MIT) — credited in geo_location.py header

### Lovelace cards (all in storm-tracker-card.js)
- `storm-tracker-card` — full radial SVG radar with wedges, labels, legend
- `storm-tracker-mini-card` — compact color-only radar, N/S/E/W labels via HTML overlay
- `storm-tracker-info-card` — sector activity list sorted closest to farthest with nearest city
- All three registered via `window.customCards` at bottom of file
- Card JS served from `custom_components/storm_tracker/storm-tracker-card.js` via static path in `async_setup` — no manual resource registration needed

## Key Constants (const.py)

| Constant | Value | Purpose |
|----------|-------|---------|
| `BURST_WINDOW_SECONDS` | 60 | Collapses burst strikes into one time bucket |
| `MIN_TREND_BUCKETS` | 2 | Minimum distinct buckets for regression |
| `DEFAULT_APPROACH_THRESHOLD` | 10.0 | Min slope (units/hr) to classify as approaching/receding |
| `CENTROID_WINDOW_MINUTES` | 10 | Window for centroid/edge map position (not trend regression) |
| `GEOCODE_CACHE_RADIUS_KM` | 30 | Re-geocode only if centroid moves further than this |
| `DEFAULT_TIME_WINDOW_MINUTES` | 30 | Lookback window for trend regression |

## Known Issues & Design Decisions

### Trend classification
- APPROACHING fires if EITHER centroid or edge slope exceeds threshold (safety-first)
- RECEDING requires BOTH signals to agree — prevents centroid (pulled by distant old strikes) from false-triggering when edge is stationary
- Large centroid-to-edge spread (e.g. 220 mi centroid vs 147 mi edge) is expected for active sectors with old distant strikes in the window

### Nominatim geocoding
- Rate limit: 1 req/sec enforced via `asyncio.sleep(1.1)` between requests
- Cache invalidated when centroid moves > `GEOCODE_CACHE_RADIUS_KM`
- Returns city/town/village/hamlet/county in that priority order
- "Unknown location" on failure (not cached, retried next refresh)

### Card JS bundling
- All cards must be in one file — separate JS files registered via `add_extra_js_url` in `async_setup` do not reliably appear in the HA card picker even after full restart
- `setConfig` guards against `null`/`undefined` config (HA can pass these during initialization sequences)
- Rendering wrapped in `_safeRender()` — exceptions degrade to inline error message, not HA "Configuration Error" overlay

### Prefix filtering
- Checks entity registry platform, entity_id slug, AND `source` attribute — needed because Blitzortung geo_location entities typically have no entity registry entry

## Workflow

```bash
# Make changes
git add <files>
git commit -m "Description"
git push origin main
# Then: create GitHub release, update via HACS in HA
```

## User Preferences
- Commit and push after every logical change — user expects GitHub to stay current
- Always push after committing — don't leave commits local
- User loads updates via HACS releases, not direct file copy
