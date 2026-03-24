"""Diagnostics support for Kaeser Sigma Control 2.

Accessible via Settings > Devices > [compressor] > Download diagnostics.
Includes network connectivity tests to help debug connection issues.
"""

from __future__ import annotations

import asyncio
import platform
import socket
import time
from typing import Any
from urllib.parse import urlparse

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import KaeserSC2Coordinator

REDACTED = "**REDACTED**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: KaeserSC2Coordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )

    diag: dict[str, Any] = {}

    # ── 1. Configuration (redacted) ──────────────────────────────
    diag["config"] = {
        "host": entry.data.get(CONF_HOST),
        "username": entry.data.get(CONF_USERNAME, "(default)"),
        "password": REDACTED,
        "poll_interval": entry.options.get(
            "poll_interval", entry.data.get("poll_interval", "default")
        ),
    }

    # ── 2. Home Assistant host network info ──────────────────────
    diag["ha_host"] = await _get_ha_network_info(hass, entry.data.get(CONF_HOST, ""))

    # ── 3. Network connectivity tests to the controller ──────────
    diag["network_tests"] = await _run_network_tests(
        hass, entry.data.get(CONF_HOST, "")
    )

    # ── 4. Current coordinator data ──────────────────────────────
    if coordinator and coordinator.data:
        data = coordinator.data
        diag["coordinator"] = {
            "online": data.online,
            "status_text": data.status_text,
            "state": data.state,
            "pressure": data.pressure,
            "temperature": data.temperature,
            "model": data.model,
            "serial": data.serial,
            "last_update": coordinator.last_update_success_time.isoformat()
            if coordinator.last_update_success_time
            else None,
            "update_interval_s": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
            "sensor_count": len(data.sensors) if data.sensors else 0,
        }

        # Include sensor names (but not values — they're in entities)
        if data.sensors:
            diag["sensor_names"] = sorted(data.sensors.keys())
    else:
        diag["coordinator"] = {
            "online": False,
            "note": "No data available — coordinator may not have completed first poll",
        }

    return diag


async def _get_ha_network_info(hass: HomeAssistant, target_host: str) -> dict[str, Any]:
    """Gather HA host network details relevant to connectivity."""
    info: dict[str, Any] = {
        "platform": platform.system(),
        "python": platform.python_version(),
    }

    parsed = urlparse(target_host)
    hostname = (
        parsed.hostname
        or target_host.replace("http://", "").replace("https://", "").split(":")[0]
    )

    # DNS resolution of the target
    try:
        loop = asyncio.get_running_loop()
        addrs = await loop.getaddrinfo(hostname, 80, proto=socket.IPPROTO_TCP)
        info["dns_resolution"] = [
            {"family": _af_name(a[0]), "address": a[4][0]} for a in addrs
        ]
    except Exception as exc:
        info["dns_resolution"] = f"FAILED: {exc}"

    # HA's own IP when routing to the target
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0)
        try:
            sock.connect((hostname, 80))
            info["ha_source_ip"] = sock.getsockname()[0]
        finally:
            sock.close()
    except Exception:
        info["ha_source_ip"] = "unknown"

    return info


async def _run_network_tests(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Run a series of network tests against the controller."""
    parsed = urlparse(host)
    hostname = (
        parsed.hostname
        or host.replace("http://", "").replace("https://", "").split(":")[0]
    )
    port = parsed.port or 80
    base_url = host if host.startswith("http") else f"http://{host}"

    results: dict[str, Any] = {}

    # ── Test 1: ICMP-like check via raw socket (TCP SYN) ─────────
    # We can't do real ICMP from Python without root, but we can
    # test ARP/reachability by trying TCP to a likely-unused port
    # as a baseline, then the actual port.

    # ── Test 2: TCP connect to port 80 ───────────────────────────
    results["tcp_connect"] = await _tcp_test(hostname, port, timeout=10)

    # ── Test 3: TCP connect to port 443 (check if HTTPS available) ─
    results["tcp_connect_443"] = await _tcp_test(hostname, 443, timeout=5)

    # ── Test 4: HTTP GET / ───────────────────────────────────────
    results["http_get_root"] = await _http_test(base_url, "/", timeout=10)

    # ── Test 5: HTTP GET /login.html ─────────────────────────────
    results["http_get_login"] = await _http_test(base_url, "/login.html", timeout=10)

    # ── Test 6: HTTP POST /json.json (unauthenticated) ───────────
    results["json_rpc_unauth"] = await _json_rpc_test(base_url, timeout=10)

    return results


async def _tcp_test(host: str, port: int, timeout: float) -> dict[str, Any]:
    """Test raw TCP connectivity."""
    result: dict[str, Any] = {"host": host, "port": port}
    start = time.monotonic()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        elapsed = time.monotonic() - start
        writer.close()
        await writer.wait_closed()
        result["status"] = "OK"
        result["elapsed_ms"] = round(elapsed * 1000, 1)
    except asyncio.TimeoutError:
        result["status"] = f"TIMEOUT after {timeout}s"
        result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 1)
    except OSError as exc:
        result["status"] = f"FAILED: [{type(exc).__name__}] {exc}"
        result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 1)
    return result


async def _http_test(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    """Test HTTP GET request."""
    url = f"{base_url}{path}"
    result: dict[str, Any] = {"url": url}
    start = time.monotonic()
    try:
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar) as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                elapsed = time.monotonic() - start
                result["status"] = "OK"
                result["http_status"] = resp.status
                result["server"] = resp.headers.get("Server", "?")
                result["content_type"] = resp.headers.get("Content-Type", "?")
                result["content_length"] = resp.headers.get("Content-Length", "?")
                # Read first 200 chars of body for debugging
                body = await resp.text()
                result["body_preview"] = body[:200] if body else "(empty)"
                result["elapsed_ms"] = round(elapsed * 1000, 1)
                # Capture any cookies set
                cookies = {c.key: c.value for c in session.cookie_jar}
                if cookies:
                    result["cookies_set"] = list(cookies.keys())
    except asyncio.TimeoutError:
        result["status"] = f"TIMEOUT after {timeout}s"
        result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 1)
    except Exception as exc:
        result["status"] = f"FAILED: [{type(exc).__name__}] {exc}"
        result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 1)
    return result


async def _json_rpc_test(base_url: str, timeout: float) -> dict[str, Any]:
    """Test JSON-RPC POST /json.json without authentication."""
    url = f"{base_url}/json.json"
    result: dict[str, Any] = {"url": url}
    payload = '{"0":1,"1":1}'
    start = time.monotonic()
    try:
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar) as session:
            async with session.post(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                elapsed = time.monotonic() - start
                result["status"] = "OK"
                result["http_status"] = resp.status
                body = await resp.text()
                # Parse to check the SC2 error message
                result["body_preview"] = body[:300] if body else "(empty)"
                result["elapsed_ms"] = round(elapsed * 1000, 1)
    except asyncio.TimeoutError:
        result["status"] = f"TIMEOUT after {timeout}s"
        result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 1)
    except Exception as exc:
        result["status"] = f"FAILED: [{type(exc).__name__}] {exc}"
        result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 1)
    return result


def _af_name(af: int) -> str:
    """Friendly name for address family."""
    return {
        socket.AF_INET: "IPv4",
        socket.AF_INET6: "IPv6",
    }.get(af, f"AF_{af}")
