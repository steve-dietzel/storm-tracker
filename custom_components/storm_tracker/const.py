"""Constants for Storm Tracker."""

DOMAIN = "storm_tracker"

PLATFORMS = ["sensor", "geo_location"]

GEO_ATTRIBUTION = "Data provided by Storm Tracker"

# ---------------------------------------------------------------------------
# Sector definitions
# ---------------------------------------------------------------------------

SECTORS = [
    {"index": 0, "label": "N",  "center": 0.0,   "range": (337.5, 22.5)},
    {"index": 1, "label": "NE", "center": 45.0,  "range": (22.5,  67.5)},
    {"index": 2, "label": "E",  "center": 90.0,  "range": (67.5,  112.5)},
    {"index": 3, "label": "SE", "center": 135.0, "range": (112.5, 157.5)},
    {"index": 4, "label": "S",  "center": 180.0, "range": (157.5, 202.5)},
    {"index": 5, "label": "SW", "center": 225.0, "range": (202.5, 247.5)},
    {"index": 6, "label": "W",  "center": 270.0, "range": (247.5, 292.5)},
    {"index": 7, "label": "NW", "center": 315.0, "range": (292.5, 337.5)},
]

SECTOR_LABELS = [s["label"] for s in SECTORS]  # ["N", "NE", ..., "NW"]

# ---------------------------------------------------------------------------
# Trend states
# ---------------------------------------------------------------------------

TREND_APPROACHING = "approaching"
TREND_RECEDING    = "receding"
TREND_STATIONARY  = "stationary"
TREND_CLEAR       = "clear"

TREND_STATES = [TREND_APPROACHING, TREND_RECEDING, TREND_STATIONARY, TREND_CLEAR]

# ---------------------------------------------------------------------------
# Config / options keys
# ---------------------------------------------------------------------------

CONF_UNIT_SYSTEM           = "unit_system"
CONF_GEO_LOCATION_PREFIX   = "geo_location_prefix"
CONF_TIME_WINDOW_MINUTES   = "time_window_minutes"
CONF_UPDATE_INTERVAL       = "update_interval_seconds"
CONF_APPROACH_THRESHOLD    = "approach_threshold"

# ---------------------------------------------------------------------------
# Unit system values
# ---------------------------------------------------------------------------

UNIT_IMPERIAL = "imperial"
UNIT_METRIC   = "metric"
UNIT_OPTIONS  = [UNIT_IMPERIAL, UNIT_METRIC]

UNIT_MILES      = "mi"
UNIT_KILOMETERS = "km"

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

DEFAULT_NAME               = "Storm Tracker"
DEFAULT_UNIT_SYSTEM        = UNIT_IMPERIAL
DEFAULT_GEO_LOCATION_PREFIX = "blitzortung"
DEFAULT_TIME_WINDOW_MINUTES = 30
DEFAULT_UPDATE_INTERVAL    = 30
DEFAULT_APPROACH_THRESHOLD = 10.0

# ---------------------------------------------------------------------------
# Trend calculation parameters
# ---------------------------------------------------------------------------

# Strikes whose publication_dates fall within this window are collapsed into
# a single centroid/leading-edge sample before regression.  This prevents a
# burst of simultaneous bolts from producing a meaningless slope.
BURST_WINDOW_SECONDS = 60

# Minimum number of distinct time buckets required to compute a trend slope.
# Fewer than two buckets means we cannot measure change over time.
MIN_TREND_BUCKETS = 2

# Time window used to compute centroid and leading-edge map positions.
# Shorter than the trend window so pins reflect where the storm is now,
# not a smeared average over the full history.
CENTROID_WINDOW_MINUTES = 10

# Reverse geocoding — only re-query Nominatim when the centroid moves further
# than this distance from the last geocoded position.
GEOCODE_CACHE_RADIUS_KM = 30

# ---------------------------------------------------------------------------
# Earth radius constants (for Haversine fallback)
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0
EARTH_RADIUS_MI = 3958.8
