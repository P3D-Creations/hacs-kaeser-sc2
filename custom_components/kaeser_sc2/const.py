"""Kaeser Sigma Control 2 — Constants."""

DOMAIN = "kaeser_sc2"
MANUFACTURER = "Kaeser Kompressoren"
MODEL = "Sigma Control 2"

# Config keys
CONF_HOST = "host"
CONF_NAME = "name"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_POLL_INTERVAL = 30  # seconds
DEFAULT_USERNAME = ""
DEFAULT_PASSWORD = ""
DEFAULT_PORT = 80

# ---------------------------------------------------------------------------
# SC2 JSON-RPC API constants (from json_requests.js)
# ---------------------------------------------------------------------------
APP_ID_HMI = 1
APP_ID_USERMANAGER = 2
APP_ID_REPORTMANAGER = 3
APP_ID_SESSION_MANAGEMENT = 8
APP_ID_DATARECORDER = "datarecorder"

SER_ID_HMI_GET_HMI_MENU = 1
SER_ID_HMI_GET_HMI_OBJECTS = 2
SER_ID_HMI_GET_LED_STATUS = 4
SER_ID_HMI_GET_COMP_INFO = 7

SER_ID_GET_REPORT_OBJECTS = 1
SER_ID_GET_EVENTS = 4
SER_ID_GET_IO_DATA = 10

RESP_SUCCESS = 0
RESP_APP_LOGOUT = 5

# ---------------------------------------------------------------------------
# HMI object type enums (from system_status.js)
# ---------------------------------------------------------------------------
TYPE_START_PAGE = 0
TYPE_START_MENU = 1
TYPE_MENU = 2
TYPE_LINE = 3
TYPE_INFO_TEXT = 4
TYPE_BINARY = 5
TYPE_FIXED_COMMA = 6
TYPE_COUNTER = 7
TYPE_PRESSURE = 8
TYPE_TEMPERATURE = 9
TYPE_TIMER = 10
TYPE_DATE = 11
TYPE_TIME = 12
TYPE_TEXT_FRAME = 13
TYPE_ENUM = 14
TYPE_TEXT_DISPLAY = 15
TYPE_IMAGE = 16
TYPE_DELQUANTITY = 17
TYPE_VOLDELQUANTITY = 18
TYPE_VOLBUFVOL = 19

# LED state enums
LED_STATE_OFF = 0
LED_STATE_ON = 1
LED_STATE_FLASH = 2

# LED colour enums
LED_COLOUR_OFF = 0
LED_COLOUR_RED = 1
LED_COLOUR_ORANGE = 2
LED_COLOUR_GREEN = 3
