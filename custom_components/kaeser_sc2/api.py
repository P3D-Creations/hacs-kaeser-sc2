"""
Kaeser Sigma Control 2 — Async API Client for Home Assistant.

Communicates with the SC2 controller's built-in web server via its
undocumented JSON-RPC endpoint at /json.json.

Protocol reverse-engineered from the controller's JavaScript frontend.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlparse

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
    TYPE_FIXED_COMMA,
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
            _LOGGER.debug("Auth step 1: GET %s/login.html", self.host)
            async with session.get(
                f"{self.host}/login.html",
                headers={"Content-Type": "text/html"},
            ) as resp:
                status1 = resp.status
                _LOGGER.debug(
                    "Auth step 1 response: status=%s headers=%s",
                    status1,
                    {k: v for k, v in resp.headers.items()
                     if k.lower() in ("content-type", "server", "set-cookie")},
                )
                resp.raise_for_status()

            self._session_key = self._get_cookie("Session-Key")
            if not self._session_key:
                _LOGGER.warning(
                    "No Session-Key cookie from %s. Cookies: %s",
                    self.host,
                    [c.key for c in session.cookie_jar],
                )
                return False
            _LOGGER.debug("Auth step 1 OK: Session-Key=%s", self._session_key[:8] + "...")

            # Step 2-3: compute auth
            self._ha1 = _sha256(f"{self.username}:user@sc2:{self.password}")
            auth_hash = _sha256(f"{self._ha1}:{self._session_key}")

            # Step 4: login
            _LOGGER.debug("Auth step 4: GET %s/login.html with auth headers", self.host)
            async with session.get(
                f"{self.host}/login.html",
                headers={
                    "Content-Type": "text/html",
                    "Username": self.username,
                    "Session-Auth": auth_hash,
                },
            ) as resp:
                _LOGGER.debug(
                    "Auth step 4 response: status=%s",
                    resp.status,
                )
                resp.raise_for_status()

            session_id = self._get_cookie("Session-Id")
            if session_id and session_id not in ("0", "-1"):
                self._authenticated = True
                _LOGGER.info(
                    "Logged in to %s (Session-Id=%s)", self.host, session_id
                )
                return True

            _LOGGER.warning(
                "Login failed for %s (Session-Id=%s). Cookies: %s",
                self.host, session_id,
                [c.key for c in session.cookie_jar],
            )
            return False

        except Exception as exc:
            _LOGGER.error(
                "Login error for %s: [%s] %s (repr=%r)",
                self.host, type(exc).__name__, exc, exc,
            )
            return False

    async def test_connection(self) -> bool:
        """Quick connectivity + auth test (used by config flow)."""
        parsed = urlparse(self.host)
        host = parsed.hostname or self.host.replace("http://", "").replace("https://", "").split(":")[0]
        port = parsed.port or 80

        # Raw TCP check with retry — SC2 controllers only support one
        # concurrent connection, so the first attempt may fail if a
        # browser tab is still open.
        tcp_ok = False
        for attempt in range(1, 4):
            try:
                _LOGGER.debug(
                    "TCP reachability check for %s:%s (attempt %d/3)",
                    host, port, attempt,
                )
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=10
                )
                writer.close()
                await writer.wait_closed()
                _LOGGER.debug("TCP reachability OK for %s:%s", host, port)
                tcp_ok = True
                break
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "TCP connection to %s:%s timed out (attempt %d/3). "
                    "The SC2 controller may only accept one connection — "
                    "close any browser tabs to this controller.",
                    host, port, attempt,
                )
            except OSError as exc:
                _LOGGER.warning(
                    "TCP connection to %s:%s failed (attempt %d/3): [%s] %s",
                    host, port, attempt, type(exc).__name__, exc,
                )
            # Wait before retrying to give the controller time to free up
            if attempt < 3:
                await asyncio.sleep(3)

        if not tcp_ok:
            _LOGGER.error(
                "All 3 TCP connection attempts to %s:%s failed. "
                "Possible causes: (1) another device/browser has an active "
                "session — close ALL browser tabs to http://%s then retry, "
                "(2) the controller is powered off, or "
                "(3) a firewall/VLAN is blocking the connection from Home Assistant.",
                host, port, host,
            )
            return False

        # HTTP probe: simple GET / to verify the web server responds
        try:
            session = await self._ensure_session()
            _LOGGER.debug("HTTP probe: GET %s/", self.host)
            async with session.get(f"{self.host}/") as resp:
                _LOGGER.debug(
                    "HTTP probe response: status=%s server=%s content-type=%s",
                    resp.status,
                    resp.headers.get("Server", "?"),
                    resp.headers.get("Content-Type", "?"),
                )
        except Exception as exc:
            _LOGGER.warning(
                "HTTP probe failed for %s: [%s] %s — "
                "the controller may only accept one connection at a time. "
                "Close any open browser tabs to this controller and retry.",
                self.host, type(exc).__name__, exc,
            )
            # Close the failed session so authenticate() starts fresh
            await self.close()

        try:
            ok = await self.authenticate()
            if not ok:
                _LOGGER.warning("test_connection: authenticate returned False for %s", self.host)
            return ok
        except Exception as exc:
            _LOGGER.error(
                "test_connection failed for %s: [%s] %s",
                self.host, type(exc).__name__, exc,
            )
            return False
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
            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "If-Modified-Since": "Thu, 03 Apr 2009 00:00:00 GMT",
            }
            auth = self._compute_session_auth()
            if auth:
                headers["Session-Auth"] = auth

            async with session.post(
                f"{self.host}/json.json", json=payload, headers=headers
            ) as resp:
                ct = resp.headers.get("Content-Type", "")
                if resp.status == 200 and ("json" in ct or "javascript" in ct or "text" in ct):
                    return await resp.json(content_type=None)
                # Fallback: try to parse any 200 response as JSON
                if resp.status == 200:
                    try:
                        return await resp.json(content_type=None)
                    except Exception:  # noqa: BLE001
                        pass
                _LOGGER.warning(
                    "Unexpected response from %s: status=%s content-type=%s",
                    self.host, resp.status, ct,
                )
                return None
        except Exception as exc:
            _LOGGER.error(
                "Request error for %s: [%s] %s",
                self.host, type(exc).__name__, exc,
            )
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

        data_field = resp.get("3")
        _LOGGER.debug(
            "API response app=%s svc=%s code=%s (raw=%r) data_type=%s resp_keys=%s",
            app_id, service_id, resp_code, raw_code,
            type(data_field).__name__ if data_field is not None else "None",
            list(resp.keys()) if isinstance(resp, dict) else "N/A",
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

        if data_field is None:
            _LOGGER.debug(
                "API call app=%s svc=%s succeeded but no data field ('3') in response",
                app_id, service_id,
            )
        return data_field

    # ------------------------------------------------------------------
    # High-level data retrieval
    # ------------------------------------------------------------------
    async def get_menu_structure(self) -> Any | None:
        data = await self._api_call(APP_ID_HMI, SER_ID_HMI_GET_HMI_MENU)
        _LOGGER.debug(
            "get_menu_structure: data_type=%s truthy=%s keys=%s",
            type(data).__name__ if data is not None else "None",
            bool(data) if data is not None else False,
            list(data.keys())[:20] if isinstance(data, dict) else "N/A",
        )
        if data is not None:
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
    # Helpers
    # ------------------------------------------------------------------
    def _iter_numeric_dict(self, obj: Any) -> list:
        """Iterate an array-like dict with numeric keys {"0": ..., "1": ...}."""
        if isinstance(obj, list):
            return list(obj)
        items: list = []
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

    @staticmethod
    def _safe_int(val: Any) -> int | None:
        """Convert a value to int, or None."""
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Menu / object-ID discovery
    # ------------------------------------------------------------------
    def _find_start_page(self, menu: Any) -> dict | None:
        """Find the TYPE_START_PAGE (Type=0) object in the menu tree."""
        if isinstance(menu, dict):
            t = self._safe_int(menu.get("Type"))
            if t == TYPE_START_PAGE:
                return menu
            # Iterate over all values (numeric or named)
            for v in menu.values():
                if isinstance(v, (dict, list)):
                    result = self._find_start_page(v)
                    if result:
                        return result
        elif isinstance(menu, list):
            for item in menu:
                result = self._find_start_page(item)
                if result:
                    return result
        return None

    def _extract_all_ids(self, data: Any) -> list[int]:
        """
        Brute-force: walk the entire menu data and collect every 'Id' value
        and every integer referenced in 'Object' or 'StatusLine' fields.
        """
        ids: set[int] = set()

        def _walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for key, val in obj.items():
                    if key == "Id":
                        i = self._safe_int(val)
                        if i is not None and i > 0:
                            ids.add(i)
                    elif key in ("StatusLine",):
                        i = self._safe_int(val)
                        if i is not None and i > 0:
                            ids.add(i)
                    elif key == "Object" and isinstance(val, dict):
                        for sv in val.values():
                            i = self._safe_int(sv)
                            if i is not None and i > 0:
                                ids.add(i)
                            elif isinstance(sv, dict):
                                _walk(sv)
                    if isinstance(val, (dict, list)):
                        _walk(val)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(data)
        return sorted(ids)

    def _build_id_index(self, menu: Any) -> dict[int, dict]:
        """Build a lookup of Id -> menu dict for the flat menu array."""
        index: dict[int, dict] = {}

        def _walk(obj: Any) -> None:
            if isinstance(obj, dict):
                oid = self._safe_int(obj.get("Id"))
                if oid is not None:
                    index[oid] = obj
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        _walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(menu)
        return index

    def _extract_object_ids_from_page(
        self, page: dict, id_index: dict[int, dict]
    ) -> list[int]:
        """Extract leaf HMI object IDs from a start page via its children."""
        ids: list[int] = []
        collected: set[int] = set()

        def _collect(ref: Any) -> None:
            if ref is None:
                return
            i = self._safe_int(ref)
            if i is not None:
                if i in id_index:
                    _collect_obj(id_index[i])
                elif i not in collected:
                    collected.add(i)
                    ids.append(i)
            elif isinstance(ref, dict):
                _collect_obj(ref)

        def _collect_obj(obj: dict) -> None:
            t = self._safe_int(obj.get("Type"))
            oid = self._safe_int(obj.get("Id"))
            container_types = (
                TYPE_START_PAGE, TYPE_LINE, TYPE_START_MENU, TYPE_MENU,
            )
            if t in container_types:
                sl = obj.get("StatusLine")
                if sl is not None:
                    _collect(sl)
                sub = obj.get("Object")
                if isinstance(sub, dict):
                    for v in sub.values():
                        _collect(v)
                elif isinstance(sub, list):
                    for v in sub:
                        _collect(v)
            else:
                if oid is not None and oid not in collected:
                    collected.add(oid)
                    ids.append(oid)

        _collect_obj(page)
        return ids

    async def _discover_object_ids(self) -> list[int]:
        """Discover HMI object IDs from the menu structure."""
        menu = await self.get_menu_structure()
        if menu is None:
            _LOGGER.warning("Menu response is None from %s", self.host)
            return []
        if not menu:
            _LOGGER.warning("Menu response is empty (%s) from %s", type(menu).__name__, self.host)
            return []

        # Dump raw menu structure for debugging (truncated)
        try:
            menu_repr = repr(menu)
            if len(menu_repr) > 3000:
                menu_repr = menu_repr[:3000] + "...(truncated)"
            _LOGGER.debug("Raw menu data from %s: %s", self.host, menu_repr)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Could not repr menu data from %s", self.host)

        _LOGGER.debug(
            "Menu data type=%s keys=%s",
            type(menu).__name__,
            list(menu.keys())[:20] if isinstance(menu, dict) else "N/A",
        )

        # Strategy 1: find the start page and resolve its children
        sp = self._find_start_page(menu)
        if sp:
            _LOGGER.debug("Found start page: Type=%s Id=%s", sp.get("Type"), sp.get("Id"))
            id_index = self._build_id_index(menu)
            _LOGGER.debug("ID index has %d entries", len(id_index))
            ids = self._extract_object_ids_from_page(sp, id_index)
            if ids:
                _LOGGER.debug("Strategy 1 (start page): found %d IDs: %s", len(ids), ids)
                return ids
            _LOGGER.debug("Strategy 1: start page found but no IDs extracted")
        else:
            _LOGGER.debug("Strategy 1: no TYPE_START_PAGE (Type=0) found in menu")
            # Log all Type values found for debugging
            types_found: set[int] = set()
            def _find_types(obj: Any) -> None:
                if isinstance(obj, dict):
                    t = self._safe_int(obj.get("Type"))
                    if t is not None:
                        types_found.add(t)
                    for v in obj.values():
                        if isinstance(v, (dict, list)):
                            _find_types(v)
                elif isinstance(obj, list):
                    for item in obj:
                        _find_types(item)
            _find_types(menu)
            _LOGGER.debug("Types found in menu: %s", sorted(types_found))

        # Strategy 2: brute-force collect all IDs from the menu
        _LOGGER.debug("Trying brute-force ID extraction")
        all_ids = self._extract_all_ids(menu)
        if all_ids:
            _LOGGER.debug("Strategy 2 (brute-force): found %d candidate IDs: %s", len(all_ids), all_ids)
            return all_ids

        _LOGGER.warning(
            "Could not discover any HMI object IDs from %s. "
            "Menu type=%s, menu keys=%s. Please enable debug logging "
            "and share the output.",
            self.host,
            type(menu).__name__,
            list(menu.keys())[:20] if isinstance(menu, dict) else "N/A",
        )
        return []

    # ------------------------------------------------------------------
    # Value parsing
    # ------------------------------------------------------------------
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

        # Discover object IDs (once)
        if not self._object_ids:
            self._object_ids = await self._discover_object_ids()

        # HMI objects
        if self._object_ids:
            hmi = await self.get_hmi_objects(self._object_ids)
            if hmi:
                self._parse_hmi(data, hmi)
            else:
                _LOGGER.warning("HMI objects request returned empty from %s", self.host)
        else:
            _LOGGER.warning("No HMI object IDs to fetch from %s", self.host)

        # LEDs
        led = await self.get_led_status()
        if led:
            self._parse_leds(data, led)

        # Compressor name/info
        info = await self.get_compressor_info()
        if info:
            comp_type = info.get("CompType") or ""
            comp_seq = info.get("CompSeqNum") or ""
            pn = info.get("PN") or ""
            if comp_type:
                data.name = f"SC2 {comp_seq}-{comp_type}" if comp_seq else comp_type
            elif pn:
                data.name = pn

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
            "run_hours=%s, load_hours=%s, maint_in=%s, key=%s, pa=%s, time=%s",
            self.host,
            data.pressure, data.pressure_unit,
            data.temperature, data.temperature_unit,
            data.state,
            data.run_hours, data.load_hours, data.maintenance_in,
            data.key_switch, data.pa_status,
            data.controller_time,
        )
        return data

    # ------------------------------------------------------------------
    # HMI object parser  (based on captured controller JSON responses)
    #
    # Objects come back as a numeric-keyed dict {"0": {...}, "1": {...}, ...}
    # in DISPLAY ORDER.  The start page layout is:
    #
    #   [pressure Type=8] [time Type=12] [temperature Type=9]
    #   -----  (Type=15 separator)
    #   [state Type=14  e.g. "On load"]
    #   -----  (separator)
    #   [key_src Type=14] - [key_val Type=14] ¦ [pA Type=14] - [pa_val Type=14]
    #   -----  (separator)
    #   Run    [hours Type=6]
    #   Load   [hours Type=6]
    #   Maintenance in   [hours Type=6]
    # ------------------------------------------------------------------
    def _parse_hmi(self, data: CompressorData, objects: Any) -> None:
        """Parse HMI objects into CompressorData fields."""
        obj_list = self._iter_numeric_dict(objects)
        if not obj_list and isinstance(objects, dict):
            obj_list = [v for v in objects.values() if isinstance(v, dict)]

        _LOGGER.debug("Parsing %d HMI objects", len(obj_list))

        # Collect objects by type for structured parsing
        enums: list[str] = []       # TYPE_ENUM values in display order
        labels: list[str] = []      # TYPE_TEXT_DISPLAY values in order
        counters: list[tuple[str, str]] = []  # (preceding_label, value) for hour counters
        last_label = ""

        for obj in obj_list:
            if not isinstance(obj, dict):
                continue
            ot = self._safe_int(obj.get("Type"))
            vt = (obj.get("Value") or obj.get("ValueText") or obj.get("Text") or "")
            if isinstance(vt, str):
                vt = vt.strip()
            else:
                vt = str(vt).strip()
            unit = (obj.get("Unit") or "").strip() if isinstance(obj.get("Unit"), str) else ""

            _LOGGER.debug(
                "HMI Id=%s Type=%s Value=%r Unit=%r",
                obj.get("Id"), ot, vt, unit,
            )

            # --- Status bar items (one of each) ---
            if ot == TYPE_PRESSURE:
                v = self._parse_numeric(vt)
                if v is not None:
                    data.pressure = v
                    data.pressure_unit = unit or "psi"

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

            elif ot in (TYPE_TIME, TYPE_TIMER):
                if vt:
                    data.controller_time = vt

            # --- Hour counters (TYPE_FIXED_COMMA = 6 or TYPE_COUNTER = 7) ---
            elif ot in (TYPE_FIXED_COMMA, TYPE_COUNTER):
                counters.append((last_label, vt))
                last_label = ""

            # --- Enum values (state, key switch, PA status) ---
            elif ot == TYPE_ENUM:
                enums.append(vt)

            # --- Text labels and separators ---
            elif ot in (TYPE_TEXT_DISPLAY, TYPE_TEXT_FRAME):
                cleaned = vt.strip().strip("-").strip("¦").strip()
                if cleaned:
                    last_label = cleaned
                    labels.append(cleaned)

        # ----- Interpret collected enums -----
        # Known compressor state values
        state_values = {
            "on load", "off", "load", "idle", "ready", "standby",
            "error", "motor start", "motor stop", "star", "delta",
            "star-delta", "unload", "start up", "emergency stop",
            "pressure holding",
        }
        state_idx = -1
        for i, ev in enumerate(enums):
            if ev.lower() in state_values:
                data.state = ev.lower()
                state_idx = i
                break

        # After state: remaining enums follow pattern [key_src, key_val, "pA", pa_val]
        remaining = enums[state_idx + 1:] if state_idx >= 0 else enums[1:]

        # Find "pA" marker to split key switch from PA status
        pa_marker_idx = None
        for i, ev in enumerate(remaining):
            if ev.lower() == "pa":
                pa_marker_idx = i
                break

        if pa_marker_idx is not None:
            key_enums = remaining[:pa_marker_idx]
            pa_enums = remaining[pa_marker_idx + 1:]
            if key_enums:
                # Last value before pA is the key switch value (e.g., "on" / "off")
                data.key_switch = key_enums[-1]
            if pa_enums:
                data.pa_status = pa_enums[0]
        elif len(remaining) >= 4:
            # Fallback: assume [key_src, key_val, pa_label, pa_val]
            data.key_switch = remaining[1]
            data.pa_status = remaining[3]
        elif len(remaining) >= 2:
            data.key_switch = remaining[1] if len(remaining) > 1 else remaining[0]

        # ----- Interpret hour counters -----
        # Try label-based matching first
        used = [False] * len(counters)
        for i, (label, val) in enumerate(counters):
            v = self._parse_numeric(val)
            if v is None:
                continue
            ll = label.lower()
            if "maintenance" in ll:
                data.maintenance_in = int(v)
                used[i] = True
            elif "load" in ll:
                data.load_hours = int(v)
                used[i] = True
            elif "run" in ll:
                data.run_hours = int(v)
                used[i] = True

        # For any unmatched counters, assign by position: run, load, maintenance
        unmatched = [
            self._parse_numeric(val)
            for i, (_, val) in enumerate(counters)
            if not used[i] and self._parse_numeric(val) is not None
        ]
        for v in unmatched:
            if v is None:
                continue
            if data.run_hours is None:
                data.run_hours = int(v)
            elif data.load_hours is None:
                data.load_hours = int(v)
            elif data.maintenance_in is None:
                data.maintenance_in = int(v)

    # ------------------------------------------------------------------
    # LED parser
    # ------------------------------------------------------------------
    def _parse_leds(self, data: CompressorData, led_data: dict) -> None:
        if not isinstance(led_data, dict):
            return
        _LOGGER.debug("LED keys: %s", list(led_data.keys()))
        led_names = [
            "led_error", "led_com_error", "led_maintenance", "led_voltage",
            "led_load", "led_idle", "led_remote", "led_clock", "led_power_on",
        ]
        for name in led_names:
            info = led_data.get(name)
            if isinstance(info, dict):
                setattr(data, name, self._led_str(info.get("State", LED_STATE_OFF)))
        # led_voltage is special: if present at all, it means voltage is OK
        if led_data.get("led_voltage") is not None:
            data.led_voltage = "on"

    # ------------------------------------------------------------------
    # Report parser
    # ------------------------------------------------------------------
    def _parse_reports(self, data: CompressorData, reports: Any) -> None:
        msgs: list[dict] = []
        report_list = self._iter_numeric_dict(reports) if isinstance(reports, (dict, list)) else []
        if not report_list and isinstance(reports, dict):
            rd = reports.get("3") or reports.get(3)
            if isinstance(rd, (list, dict)):
                report_list = self._iter_numeric_dict(rd) if isinstance(rd, dict) else rd

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
