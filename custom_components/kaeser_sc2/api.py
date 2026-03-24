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
    TYPE_PRESSURE,
    TYPE_START_PAGE,
    TYPE_TEMPERATURE,
    TYPE_TEXT_DISPLAY,
    TYPE_TEXT_FRAME,
    TYPE_TIME,
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

        resp_code = resp.get("2")
        if resp_code != RESP_SUCCESS:
            if resp_code == RESP_APP_LOGOUT:
                _LOGGER.info("Session expired on %s, re-authenticating", self.host)
                if await self.authenticate():
                    resp = await self._post_json(payload)
                    if resp and resp.get("2") == RESP_SUCCESS:
                        return resp.get("3")
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
    def _find_start_page(self, obj: Any) -> dict | None:
        if isinstance(obj, dict):
            if obj.get("Type") == TYPE_START_PAGE:
                return obj
            for v in obj.values():
                result = self._find_start_page(v)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_start_page(item)
                if result:
                    return result
        return None

    def _extract_object_ids(self, menu_obj: dict) -> list[int]:
        ids: list[int] = []
        status_line = menu_obj.get("StatusLine")
        if status_line:
            ids.extend(self._ids_from_line(status_line))
        objects = menu_obj.get("Object", {})
        counter = 0
        while True:
            line = (
                objects.get(str(counter))
                if isinstance(objects, dict)
                else None
            )
            if line is None:
                line = (
                    objects.get(counter)
                    if isinstance(objects, dict)
                    else None
                )
            if line is None:
                break
            ids.extend(self._ids_from_line(line))
            counter += 1
        return ids

    def _ids_from_line(self, line: dict) -> list[int]:
        ids: list[int] = []
        if not isinstance(line, dict):
            return ids
        obj_id = line.get("Id")
        if obj_id is not None:
            ids.append(obj_id)
        counter = 0
        while True:
            sub = line.get(str(counter)) or line.get(counter)
            if sub is None:
                break
            if isinstance(sub, dict) and sub.get("Id"):
                ids.append(sub["Id"])
            counter += 1
        return ids

    # ------------------------------------------------------------------
    # Value parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _value_text(obj: dict) -> str:
        for key in ("ValueText", "Value", "Text"):
            v = obj.get(key)
            if v is not None:
                return str(v).strip()
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
    def _led_str(state: int) -> str:
        return {
            LED_STATE_OFF: "off",
            LED_STATE_ON: "on",
            LED_STATE_FLASH: "flash",
        }.get(state, "off")

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
            await self.get_menu_structure()

        # Object IDs
        if not self._object_ids and self._menu_tree:
            sp = self._find_start_page(self._menu_tree)
            if sp:
                self._object_ids = self._extract_object_ids(sp)
                _LOGGER.debug(
                    "Discovered %d HMI object IDs from %s",
                    len(self._object_ids),
                    self.host,
                )

        # HMI objects
        if self._object_ids:
            hmi = await self.get_hmi_objects(self._object_ids)
            if hmi:
                self._parse_hmi(data, hmi)

        # LEDs
        led = await self.get_led_status()
        if led:
            self._parse_leds(data, led)

        # Compressor name/info
        info = await self.get_compressor_info()
        if info:
            name = info.get("Name") or info.get("0")
            if name:
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
        return data

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------
    def _parse_hmi(self, data: CompressorData, objects: Any) -> None:
        obj_list: list[dict] = []
        if isinstance(objects, list):
            obj_list = objects
        elif isinstance(objects, dict):
            c = 0
            while True:
                o = objects.get(str(c)) or objects.get(c)
                if o is None:
                    break
                obj_list.append(o)
                c += 1

        for obj in obj_list:
            if not isinstance(obj, dict):
                continue
            ot = obj.get("Type")
            vt = self._value_text(obj)

            if ot == TYPE_PRESSURE:
                v = self._parse_numeric(vt)
                if v is not None:
                    data.pressure = v
                    um = re.search(r"\d\s*(psi|bar|kPa|MPa)", vt, re.I)
                    if um:
                        data.pressure_unit = um.group(1)

            elif ot == TYPE_TEMPERATURE:
                v = self._parse_numeric(vt)
                if v is not None:
                    data.temperature = v
                    data.temperature_unit = "°C" if "C" in vt.upper() and "°" in vt else "°F"

            elif ot == TYPE_TIME:
                data.controller_time = vt

            elif ot == TYPE_COUNTER:
                v = self._parse_numeric(vt)
                if v is not None:
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
        msgs: list[dict] = []
        if isinstance(reports, dict):
            rd = reports.get("3") or reports.get(3)
            if isinstance(rd, list):
                for entry in rd:
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
