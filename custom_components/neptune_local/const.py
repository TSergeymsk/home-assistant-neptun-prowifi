"""Constants for the Neptun Local integration."""

DOMAIN = "neptun_local"

# Configuration keys
CONF_HOST = "host"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DEBUG = "debug"
CONF_RETRY_ATTEMPTS = "retry_attempts"
CONF_RETRY_DELAY = "retry_delay"
CONF_MAX_CONSECUTIVE_FAILURES = "max_consecutive_failures"

# Defaults
DEFAULT_PORT = 6350
DEFAULT_SCAN_INTERVAL = 120
DEFAULT_DEBUG = False
DEFAULT_RETRY_ATTEMPTS = 2
DEFAULT_RETRY_DELAY = 8
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3

# Protocol constants
PACKET_SYSTEM_STATE = 0x52
SOCKET_BUFSIZE = 1024
SOCKET_TIMEOUT = 8

# Retry logic (values are overridden by config)
RETRY_ATTEMPTS_PER_CYCLE = DEFAULT_RETRY_ATTEMPTS
RETRY_DELAY = DEFAULT_RETRY_DELAY
MAX_CONSECUTIVE_FAILURES = DEFAULT_MAX_CONSECUTIVE_FAILURES