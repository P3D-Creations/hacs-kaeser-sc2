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

# ---------------------------------------------------------------------------
# Report-manager enums (from system_data.js)
#
# GetReportObjects(ReportList, StartIndex, NrOfReports) returns, in field "3",
# a numeric-keyed dict of report objects. Each report object has fields:
#   ReportDateTime      combined "date time" string
#   ReportStateEvent    numeric event state (see REP_EVT_* below)
#   ReportStateEventTxt localized state text ("Coming"/"Going"/…)
#   Text                the message text
#   ReportTypeTxt       localized message category text
#   ReportId            display id / fault code
#   Id                  internal object id (used for acknowledge)
# ---------------------------------------------------------------------------

# Report list ids (the ReportList parameter to GetReportObjects)
REP_LIST_STATUS = 0            # current/pending messages — the "Messages" screen
REP_LIST_HISTORY_COMPRESSOR = 1
REP_LIST_HISTORY_SYSTEM = 2
REP_LIST_HISTORY_DIAGNOSE = 3
REP_LIST_MAINTENANCE = 4

# Report type ids (ReportType — categorises the message)
REP_TYPE_COMPRESSOR_OPERATION = 0
REP_TYPE_COMPRESSOR_WARNING = 1
REP_TYPE_COMPRESSOR_ERROR = 2
REP_TYPE_SYSTEM = 3
REP_TYPE_DIAGNOSE = 4

# Report state-event ids (ReportStateEvent):
#   an event has "come" (occurred/active) or "gone" (cleared), and may be
#   acknowledged ("quittiert") by an operator.
REP_EVT_GONE = 0               # gegangen — condition cleared
REP_EVT_COMING = 1             # gekommen — condition active
REP_EVT_COMING_ACK = 2         # gekommen quittiert — active + acknowledged
REP_EVT_GONE_ACK = 3           # gegangen quittiert — cleared + acknowledged

# Normalised lowercase labels for ReportStateEvent
REP_STATE_LABELS = {
    REP_EVT_GONE: "going",
    REP_EVT_COMING: "coming",
    REP_EVT_COMING_ACK: "coming_ack",
    REP_EVT_GONE_ACK: "going_ack",
}

# States that mean the condition is currently present/active.
REP_ACTIVE_STATES = {REP_EVT_COMING, REP_EVT_COMING_ACK}
