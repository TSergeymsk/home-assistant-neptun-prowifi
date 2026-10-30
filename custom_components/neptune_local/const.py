"""Constants for the Neptun Local integration."""

DOMAIN = "neptun_local"

CONF_HOST = "host"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DEBUG = "debug"

DEFAULT_PORT = 6350
DEFAULT_SCAN_INTERVAL = 120  # seconds
DEFAULT_DEBUG = False

# Resilience
SOCKET_TIMEOUT = 8            # seconds per socket operation
RETRY_ATTEMPTS_PER_CYCLE = 2  # attempts inside one update cycle
RETRY_DELAY = 8               # seconds between attempts inside a cycle
MAX_CONSECUTIVE_FAILURES = 3  # cycles before entities become Unavailable

# Packet types from neptun.py
PACKET_WHOIS = 0x49
PACKET_SYSTEM_STATE = 0x52
PACKET_COUNTER_NAME = 0x63
PACKET_COUNTER_STATE = 0x43
PACKET_SENSOR_NAME = 0x4E
PACKET_SENSOR_STATE = 0x53
PACKET_BACK_STATE = 0x42
PACKET_RECONNECT = 0x57
PACKET_SET_SYSTEM_STATE = 0x57

BROADCAST_PORT = 6350
BROADCAST_ADDRESS = "255.255.255.255"
SERVER_PORT = 6350
SOCKET_BUFSIZE = 1024