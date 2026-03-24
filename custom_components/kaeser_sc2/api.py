"""
Kaeser Sigma Control 2 — Async API Client for Home Assistant.

Communicates with the SC2 controller's built-in web server via its
undocumented JSON-RPC endpoint at /json.json.

Protocol reverse-engineered from the controller's JavaScript frontend.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from typing import Any

import aiohttp

from .const import (
    APP_ID_DATARECORDER,
    APP_ID_HMI,
    APP_ID_REPORTMANAGER,
    APP_ID_SESSION_MANAGEMENT,
    LED_STATE_FLASH,
    LED_STATE_OFF,
    LED_STATE_ON,
    RESP_APP_LOGOUT,
    RESP_SUCCESS,
    SER_ID_GET_IO_DATA,
    SER_ID_GET_REPORT_OBJECTS,
    SER_ID_HMI_GET_COMP_INFO,
    SER_ID_HMI_GET_HMI_MENU,
    SER_ID_HMI_GET_HMI_OBJECTS,
    SER_ID_HMI_GET_LED_STATUS,
    TYPE_COUNTER,
    TYPE_ENUM,
    TYPE_LINE,
    TYPE_MENU,
    TYPE_PRESSURE,
    TYPE_START_MENU,
    TYPE_START_PAGE,
    TYPE_TEMPERATURE,
    TYPE_TEXT_DISPLAY,
    TYPE_TEXT_FRAME,
    TYPE_TIME,
    TYPE_TIMER,
)

_LOGGER = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    """Return hex SHA-256 digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CompressorData:
    """Parsed telemetry snapshot from one Sigma Control 2 unit."""

    name: str = ""

    # Status bar
    pressure: float | None = None
    pressure_unit: str = "psi"
    temperature: float | None = None
    temperature_unit: str = "°F"
    controller_time: str = ""

    # Operational state
    state: str = "unknown"
    key_switch: str = "unknown"
    pa_status: str = "unknown"

    # Counters
    run_hours: int | None = None
    load_hours: int | None = None
    maintenance_in: int | None = None

    # LED states: "off", "on", "flash"
    led_error: str = "off"
    led_com_error: str = "off"
    led_maintenance: str = "off"
    led_voltage: str = "off"
    led_load: str = "off"
    led_idle: str = "off"
    led_remote: str = "off"
    led_clock: str = "off"
    led_power_on: str = "off"

    # I/O data
    io_data: dict = field(default_factory=dict)

    # Active alarms / messages
    active_messages: list = field(default_factory=list)

    # Connectivity
    online: bool = False


class SigmaControl2:
    """Async client for a single Kaeser Sigma Control 2 controller."""

    def __init__(
        self,
        host: str,
        username: str = "",
        password: str = "",
        session: aiohttp.ClientSession | None = None,
        timeout: int = 10,
    ) -> None:
        self.host = host.rstrip("/")
        if not self.host.startswith("http"):
            self.host = f"http://{self.host}"
        self.username = username
        self.password = password
        self.timeout = aiohttp.ClientTimeout(total=timeout)

        self._external_session = session is not None
        self._session: aiohttp.ClientSession | None = session
        self._ha1: str | None = None
        self._session_key: str | None = None
        self._authenticated = False

        # Cached menu data
        self._menu_tree: dict | None = None
        self._object_ids: list[int] = []

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                cookie_jar=jar,
                headers={
                    "Content-Type": "application/json",
                    "If-Modified-Since": "Thu, 03 Apr 2009 00:00:00 GMT",
                },
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session if we own it."""
        if not self._external_session and self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    async def authenticate(self) -> bool:
        """
        Authenticate with the SC2 controller.

        1. GET /login.html → receive Session-Key cookie
        2. HA1 = sha256(username + ":user@sc2:" + password)
        3. Session-Auth = sha256(HA1 + ":" + Session-Key)
        4. GET /login.html with Username + Session-Auth headers
        5. Receive Session-Id cookie → authenticated
        """
        try:
            session = await self._ensure_session()

            # Step 1: get Session-Key
            async with session.get(f"{self.host}/login.html") as resp:
                resp.raise_for_status()

            self._session_key = self._get_cookie("Session-Key")
            if not self._session_key:
                _LOGGER.warning("No Session-Key cookie from %s", self.host)
                return False

            # Step 2-3: compute auth
            self._ha1 = _sha256(f"{self.username}:user@sc2:{self.password}")
            auth_hash = _sha256(f"{self._ha1}:{self._session_key}")

            # Step 4: login
            async with session.get(
                f"{self.host}/login.html",
                headers={"Username": self.username, "Session-Auth": auth_hash},
            ) as resp:
                resp.raise_for_status()

            session_id = self._get_cookie("Session-Id")
            if session_id and session_id not in ("0", "-1"):
                self._authenticated = True
                _LOGGER.info(
                    "Logged in to %s (Session-Id=%s)", self.host, session_id
                )
                return True

            _LOGGER.warning(
                "Login failed for %s (Session-Id=%s)", self.host, session_id
            )
            return False

        except (aiohttp.ClientError, TimeoutError) as exc:
            _LOGGER.error("Login error for %s: %s", self.host, exc)
            return False

    async def test_connection(self) -> bool:
        """Quick connectivity + auth test (used by config flow)."""
        try:
            ok = await self.authenticate()
            return ok
        finally:
            await self.close()

    def _get_cookie(self, name: str) -> str | None:
        if self._session is None:
            return None
        for cookie in self._session.cookie_jar:
            if cookie.key == name:
                return cookie.value
        return None

    def _compute_session_auth(self) -> str | None:
        if not self._ha1 or not self._session:
            return None
        key = self._get_cookie("Session-Key")
        if not key:
            return None
        return _sha256(f"{self._ha1}:{key}")

    # ------------------------------------------------------------------
    # Low-level JSON-RPC
    # ------------------------------------------------------------------
    async def _post_json(self, payload: dict) -> dict | None:
        try:
            session = await self._ensure_session()
            headers: dict[str, str] = {}
            auth = self._compute_session_auth()
            if auth:
                headers["Session-Auth"] = auth

            async with session.post(
                f"{self.host}/json.json", json=payload, headers=headers
            ) as resp:
                ct = resp.headers.get("Content-Type", "")
                if resp.status == 200 and ct.startswith("application/json"):
                    return await resp.json(content_type=None)
                _LOGGER.warning(
                    "Unexpected response from %s: %s %s",
                    self.host, resp.status, ct,
                )
                return None
        except (aiohttp.ClientError, TimeoutError) as exc:
            _LOGGER.error("Request error for %s: %s", self.host, exc)
            return None

    async def _api_call(
        self, app_id: Any, service_id: int, data: Any = None
    ) -> Any | None:
        payload: dict[str, Any] = {"0": app_id, "1": service_id}
        if data is not None:
            payload["2"] = data

        resp = await self._post_json(payload)
        if resp is None:
            return None

        # Response code may be int or str depending on controller firmware
        raw_code = resp.get("2")
        try:
            resp_code = int(raw_code) if raw_code is not None else -1
        except (ValueError, TypeError):
            resp_code = -1

        _LOGGER.debug(
            "API response app=%s svc=%s code=%s (raw=%r) data_type=%s",
            app_id, service_id, resp_code, raw_code,
            type(resp.get("3")).__name__ if resp.get("3") is not None else "None",
        )
        if resp_code != RESP_SUCCESS:
            if resp_code == RESP_APP_LOGOUT:
                _LOGGER.info("Session expired on %s, re-authenticating", self.host)
                if await self.authenticate():
                    resp = await self._post_json(payload)
                    if resp:
                        raw2 = resp.get("2")
                        try:
                            code2 = int(raw2) if raw2 is not None else -1
                        except (ValueError, TypeError):
                            code2 = -1
                        if code2 == RESP_SUCCESS:
                            return resp.get("3")
            _LOGGER.warning(
                "API call failed for %s: app=%s svc=%s code=%s",
                self.host, app_id, service_id, resp_code,
            )
            return None

        return resp.get("3")

    # ------------------------------------------------------------------
    # High-level data retrieval
    # ------------------------------------------------------------------
    async def get_menu_structure(self) -> Any | None:
        data = await self._api_call(APP_ID_HMI, SER_ID_HMI_GET_HMI_MENU)
        if data:
            self._menu_tree = data
        return data

    async def get_hmi_objects(self, object_ids: list[int]) -> Any | None:
        if not object_ids:
            return None
        return await self._api_call(
            APP_ID_HMI, SER_ID_HMI_GET_HMI_OBJECTS, {"0": object_ids}
        )

    async def get_led_status(self) -> dict | None:
        return await self._api_call(APP_ID_HMI, SER_ID_HMI_GET_LED_STATUS)

    async def get_compressor_info(self) -> dict | None:
        return await self._api_call(APP_ID_HMI, SER_ID_HMI_GET_COMP_INFO)

    async def get_io_data(self) -> dict | None:
        return await self._api_call(APP_ID_DATARECORDER, SER_ID_GET_IO_DATA, {})

    async def get_reports(
        self, report_list: int = 0, start: int = 0, count: int = 20
    ) -> Any | None:
        return await self._api_call(
            APP_ID_REPORTMANAGER,
            SER_ID_GET_REPORT_OBJECTS,
            {"0": report_list, "1": start, "2": count},
        )

    # ------------------------------------------------------------------
    # Menu parsing helpers
    # ------------------------------------------------------------------
    def _iter_numeric_dict(self, obj: Any) -> list:
        """Iterate an array-like dict with numeric keys {"0": ..., "1": ...}."""
        items: list = []
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            c = 0
            while True:
                v = obj.get(str(c))
                if v is None:
                    v = obj.get(c)
                if v is None:
                    break
                items.append(v)
                c += 1
        return items

    def _find_start_page(self, obj: Any) -> dict | None:
        """Find the TYPE_START_PAGE object in the flat menu array."""
        if isinstance(obj, dict):
            raw_type = obj.get("Type")
            try:
                obj_type = int(raw_type) if raw_type is not None else None
            except (ValueError, TypeError):
                obj_type = None
            if obj_type == TYPE_START_PAGE:
                return obj
            # Iterate numeric-keyed flat array
            for item in self._iter_numeric_dict(obj):
                result = self._find_start_page(item)
                if result:
                    return result
            # Also check named values
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    result = self._find_start_page(v)
                    if result:
                        return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_start_page(item)
                if result:
                    return result
        return None

    def _build_id_index(self, menu: Any) -> dict[int, dict]:
        """Build a lookup of Id → menu object for the flat menu array."""
        index: dict[int, dict] = {}
        items = self._iter_numeric_dict(menu) if isinstance(menu, (dict, list)) else []
        for item in items:
            if isinstance(item, dict) and item.get("Id") is not None:
                try:
                    idx = int(item["Id"])
                except (ValueError, TypeError):
                    continue
                index[idx] = item
        return index

    def _extract_object_ids(self, start_page: dict, id_index: dict[int, dict]) -> list[int]:
        """
        Extract all leaf HMI object IDs from the start page and its children.

        The start page has:
        - StatusLine: int ID or dict (references a TYPE_LINE)
        - Object: {"0": id_or_dict, "1": id_or_dict, ...} (lines on the page)

        Each TYPE_LINE has:
        - Object: {"0": id_or_dict, ...} (actual IO objects like pressure, temp)
        """
        ids: list[int] = []
        collected: set[int] = set()

        def _collect_from(ref: Any) -> None:
            """Recursively collect object IDs from a reference."""
            if ref is None:
                return
            # Convert string IDs to int
            if isinstance(ref, str):
                try:
                    ref = int(ref)
                except ValueError:
                    return
            if isinstance(ref, int):
                # This is an ID referencing another object in the menu
                if ref in id_index:
                    obj = id_index[ref]
                    _collect_from_obj(obj)
                else:
                    # It's a leaf object ID — add it
                    if ref not in collected:
                        collected.add(ref)
                        ids.append(ref)
            elif isinstance(ref, dict):
                _collect_from_obj(ref)

        def _collect_from_obj(obj: dict) -> None:
            raw_type = obj.get("Type")
            try:
                obj_type = int(raw_type) if raw_type is not None else None
            except (ValueError, TypeError):
                obj_type = None
            obj_id = obj.get("Id")
            if isinstance(obj_id, str):
                try:
                    obj_id = int(obj_id)
                except ValueError:
                    pass

            # If it's a container (start_page, line, menu), recurse into children
            if obj_type in (TYPE_START_PAGE, TYPE_LINE, TYPE_START_MENU, TYPE_MENU):
                # Collect StatusLine
                sl = obj.get("StatusLine")
                if sl is not None:
                    _collect_from(sl)
                # Collect Object children
                sub_objects = obj.get("Object")
                if sub_objects is not None:
                    for child in self._iter_numeric_dict(sub_objects):
                        _collect_from(child)
                    # Also try named keys
                    if isinstance(sub_objects, dict):
                        for v in sub_objects.values():
                            if isinstance(v, (int, dict)):
                                _collect_from(v)
            else:
                # It's a leaf object (pressure, temp, etc.) — add its ID
                if obj_id is not None and obj_id not in collected:
                    collected.add(obj_id)
                    ids.append(obj_id)

        _collect_from_obj(start_page)
        return ids

    # ------------------------------------------------------------------
    # Value parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _value_text(obj: dict) -> str:
        """Get the display value text from an HMI object."""
        for key in ("Value", "ValueText", "Text"):
            v = obj.get(key)
            if v is not None:
                return str(v).strip()
        return ""

    @staticmethod
    def _unit_text(obj: dict) -> str:
        """Get the unit string from an HMI object (separate field)."""
        u = obj.get("Unit")
        if u is not None:
            return str(u).strip()
        return ""

    @staticmethod
    def _parse_numeric(text: str) -> float | None:
        m = re.search(r"(-?\d+\.?\d*)", text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def _led_str(state: Any) -> str:
        try:
            s = int(state)
        except (ValueError, TypeError):
            return "off"
        return {
            LED_STATE_OFF: "off",
            LED_STATE_ON: "on",
            LED_STATE_FLASH: "flash",
        }.get(s, "off")

    # ------------------------------------------------------------------
    # Main poll
    # ------------------------------------------------------------------
    async def poll(self) -> CompressorData:
        """Poll all data and return a snapshot."""
        data = CompressorData()

        if not self._authenticated:
            if not await self.authenticate():
                _LOGGER.warning("Cannot auth to %s — trying unauthenticated", self.host)

        # Menu discovery (once)
        if self._menu_tree is None:
            menu = await self.get_menu_structure()
            _LOGGER.debug("Menu structure from %s: %s", self.host, menu)

        # Object IDs
        if not self._object_ids and self._menu_tree:
            sp = self._find_start_page(self._menu_tree)
            if sp:
                _LOGGER.debug("Start page from %s: %s", self.host, sp)
                id_index = self._build_id_index(self._menu_tree)
                _LOGGER.debug("Menu ID index has %d entries", len(id_index))
                self._object_ids = self._extract_object_ids(sp, id_index)
                _LOGGER.debug(
                    "Discovered %d HMI object IDs from %s: %s",
                    len(self._object_ids),
                    self.host,
                    self._object_ids,
                )
            else:
                _LOGGER.warning("No start page found in menu from %s", self.host)

        # HMI objects
        if self._object_ids:
            hmi = await self.get_hmi_objects(self._object_ids)
            _LOGGER.debug("HMI objects from %s: %s", self.host, hmi)
            if hmi:
                self._parse_hmi(data, hmi)
        else:
            _LOGGER.warning("No HMI object IDs to fetch from %s", self.host)

        # LEDs
        led = await self.get_led_status()
        _LOGGER.debug("LED status from %s: %s", self.host, led)
        if led:
            self._parse_leds(data, led)

        # Compressor name/info
        info = await self.get_compressor_info()
        _LOGGER.debug("Compressor info from %s: %s", self.host, info)
        if info:
            comp_type = info.get("CompType") or ""
            comp_seq = info.get("CompSeqNum") or ""
            pn = info.get("PN") or ""
            name = info.get("Name") or ""
            if comp_type:
                data.name = f"SC2 {comp_seq}-{comp_type}" if comp_seq else comp_type
            elif pn:
                data.name = pn
            elif name:
                data.name = str(name)

        # I/O
        io = await self.get_io_data()
        if io:
            data.io_data = io

        # Reports
        try:
            rpt = await self.get_reports(report_list=0, start=0, count=10)
            if rpt:
                self._parse_reports(data, rpt)
        except Exception:  # noqa: BLE001
            pass

        data.online = True
        _LOGGER.debug(
            "Poll result from %s: pressure=%s %s, temp=%s %s, state=%s, "
            "run_hours=%s, maintenance_in=%s, key=%s, pa=%s, time=%s",
            self.host,
            data.pressure, data.pressure_unit,
            data.temperature, data.temperature_unit,
            data.state,
            data.run_hours, data.maintenance_in,
            data.key_switch, data.pa_status,
            data.controller_time,
        )
        return data

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------
    def _parse_hmi(self, data: CompressorData, objects: Any) -> None:
        """Parse HMI object response into CompressorData fields."""
        obj_list: list[dict] = self._iter_numeric_dict(objects)
        if not obj_list and isinstance(objects, dict):
            # Maybe it's a single object or has non-numeric keys
            obj_list = [
                v for v in objects.values() if isinstance(v, dict)
            ]

        _LOGGER.debug("Parsing %d HMI objects", len(obj_list))

        for obj in obj_list:
            if not isinstance(obj, dict):
                continue
            raw_type = obj.get("Type")
            try:
                ot = int(raw_type) if raw_type is not None else None
            except (ValueError, TypeError):
                ot = None
            vt = self._value_text(obj)
            unit = self._unit_text(obj)

            _LOGGER.debug(
                "HMI obj Id=%s Type=%s Value='%s' Unit='%s'",
                obj.get("Id"), ot, vt, unit,
            )

            if ot == TYPE_PRESSURE:
                v = self._parse_numeric(vt)
                if v is not None:
                    data.pressure = v
                    if unit:
                        data.pressure_unit = unit
                    else:
                        # Fallback: try to extract unit from value text
                        um = re.search(r"(psi|bar|kPa|MPa)", vt, re.I)
                        if um:
                            data.pressure_unit = um.group(1)

            elif ot == TYPE_TEMPERATURE:
                v = self._parse_numeric(vt)
                if v is not None:
                    data.temperature = v
                    if unit:
                        data.temperature_unit = unit
                    elif "C" in vt.upper() and "°" in vt:
                        data.temperature_unit = "°C"
                    else:
                        data.temperature_unit = "°F"

            elif ot == TYPE_TIME:
                data.controller_time = vt

            elif ot == TYPE_COUNTER:
                v = self._parse_numeric(vt)
                if v is not None:
                    low_unit = unit.lower() if unit else ""
                    low_vt = vt.lower()
                    if data.run_hours is None:
                        data.run_hours = int(v)
                    elif data.maintenance_in is None:
                        data.maintenance_in = int(v)

            elif ot in (TYPE_ENUM, TYPE_TEXT_DISPLAY):
                low = vt.lower()
                if low in (
                    "off", "load", "idle", "ready", "standby",
                    "error", "motor start", "motor stop",
                    "star", "delta", "star-delta",
                ):
                    data.state = low

            elif ot == TYPE_TEXT_FRAME:
                self._parse_text_frame(data, vt)

            elif ot == TYPE_TIMER:
                # TYPE_TIMER (10) — could be controller time
                if not data.controller_time:
                    data.controller_time = vt

    def _parse_text_frame(self, data: CompressorData, text: str) -> None:
        low = text.lower().strip()
        if "key" in low:
            m = re.search(r"key\s*[-–]\s*(\w+)", low)
            if m:
                data.key_switch = m.group(1)
        if "pa " in low or "pa-" in low:
            m = re.search(r"pa\s*[-–]\s*(\w+)", low)
            if m:
                data.pa_status = m.group(1)
        if "run" in low:
            m = re.search(r"run\s+(\d+)\s*h", low)
            if m:
                data.run_hours = int(m.group(1))
        if "maintenance" in low:
            m = re.search(r"maintenance\s+in\s+(\d+)\s*h", low)
            if m:
                data.maintenance_in = int(m.group(1))
        for st in ("off", "load", "idle", "ready", "standby", "error", "motor start"):
            if low == st:
                data.state = st
                break

    def _parse_leds(self, data: CompressorData, led_data: dict) -> None:
        _LOGGER.debug("LED raw keys: %s", list(led_data.keys()) if isinstance(led_data, dict) else type(led_data))
        mapping = {
            "led_error": "led_error",
            "led_com_error": "led_com_error",
            "led_maintenance": "led_maintenance",
            "led_voltage": "led_voltage",
            "led_load": "led_load",
            "led_idle": "led_idle",
            "led_remote": "led_remote",
            "led_clock": "led_clock",
            "led_power_on": "led_power_on",
        }
        for api_key, attr in mapping.items():
            info = led_data.get(api_key)
            if info and isinstance(info, dict):
                setattr(data, attr, self._led_str(info.get("State", LED_STATE_OFF)))
        if led_data.get("led_voltage") is not None:
            data.led_voltage = "on"

    def _parse_reports(self, data: CompressorData, reports: Any) -> None:
        """Parse report objects into active_messages."""
        msgs: list[dict] = []
        # _api_call already extracted resp["3"], so reports IS the data payload
        report_list: list = []
        if isinstance(reports, list):
            report_list = reports
        elif isinstance(reports, dict):
            # Try numeric-keyed iteration
            report_list = self._iter_numeric_dict(reports)
            if not report_list:
                # Maybe the data is nested one more level
                rd = reports.get("3") or reports.get(3)
                if isinstance(rd, list):
                    report_list = rd

        for entry in report_list:
            if isinstance(entry, dict):
                msgs.append({
                    "date": entry.get("Date", ""),
                    "time": entry.get("Time", ""),
                    "state": entry.get("State", ""),
                    "message": entry.get("Message", ""),
                    "type": entry.get("Type", ""),
                    "id": entry.get("Id", ""),
                })
        data.active_messages = msgs
