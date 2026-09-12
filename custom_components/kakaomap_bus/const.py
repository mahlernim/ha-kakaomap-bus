"""Constants for HA KakaoMap Bus."""

DOMAIN = "kakaomap_bus"
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_STOP_DIRECTION = "stop_direction"
CONF_STOP_NICKNAME = "stop_nickname"
CONF_ROUTE_LABELS = "route_labels"
CONF_BUSES = "buses"
CONF_QUIET_ENABLED = "quiet_enabled"
CONF_QUIET_START = "quiet_start"
CONF_QUIET_END = "quiet_end"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_POLLING_MODE = "polling_mode"
POLLING_ADAPTIVE = "adaptive"
POLLING_FIXED = "fixed"
ADAPTIVE_INTERVAL = 120
NEAR_INTERVAL = 30
NEAR_SECONDS = 180

DEFAULT_QUIET_START = "00:00:00"
DEFAULT_QUIET_END = "05:00:00"
DEFAULT_SCAN_INTERVAL = 90
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 600
DEFAULT_REQUEST_RETRIES = 3

ARRIVAL_STATUSES = [
    "live",
    "no_arrival",
    "paused",
    "connection_lost",
    "expired",
    "rate_limited",
    "invalid_stop",
    "ambiguous_route",
]
