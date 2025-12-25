"""Constants for the HA KakaoMap Bus integration."""

DOMAIN = "kakaomap_bus"
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_BUSES = "buses"
CONF_QUIET_START = "quiet_start"
CONF_QUIET_END = "quiet_end"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_QUIET_START = "00:00:00"
DEFAULT_QUIET_END = "05:00:00"
DEFAULT_SCAN_INTERVAL = 90
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 600
