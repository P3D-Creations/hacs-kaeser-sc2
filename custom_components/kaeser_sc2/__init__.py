"""Kaeser Sigma Control 2 — Home Assistant Integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import SigmaControl2
from .const import CONF_NAME, DEFAULT_PASSWORD, DEFAULT_POLL_INTERVAL, DEFAULT_USERNAME, DOMAIN
from .coordinator import KaeserSC2Coordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

CARD_JS_URL_BASE = "/kaeser_sc2/kaeser-sc2-card.js"
CARD_JS_PATH = Path(__file__).parent / "frontend" / "kaeser-sc2-card.js"
IMAGES_URL = "/kaeser_sc2/images"
IMAGES_PATH = Path(__file__).parent / "frontend" / "images"

type KaeserSC2ConfigEntry = ConfigEntry


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the custom card JS and static image assets."""
    # Read version from manifest for cache-busting query string.
    # manifest_path.read_text() is blocking I/O — run it in the executor so it
    # does not block the event loop (HA logs a warning otherwise).
    import json
    manifest_path = Path(__file__).parent / "manifest.json"
    try:
        manifest_text = await hass.async_add_executor_job(manifest_path.read_text)
        manifest = json.loads(manifest_text)
        version = manifest.get("version", "0")
    except Exception:
        version = "0"

    card_url_versioned = f"{CARD_JS_URL_BASE}?v={version}"

    _LOGGER.debug(
        "Registering frontend: JS=%s (exists=%s), images=%s (exists=%s), url=%s",
        CARD_JS_PATH, CARD_JS_PATH.exists(),
        IMAGES_PATH, IMAGES_PATH.exists(),
        card_url_versioned,
    )
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_JS_URL_BASE, str(CARD_JS_PATH), cache_headers=True),
        StaticPathConfig(IMAGES_URL, str(IMAGES_PATH), cache_headers=True),
    ])
    # Use versioned URL for cache-busting (HA frontend/service worker may
    # cache the JS even when cache_headers=False)
    add_extra_js_url(hass, card_url_versioned)
    # Also register a Lovelace resource on storage-mode dashboards (same URL,
    # deduped by the browser). Adds the dashboard resource-loader path, which
    # tends to load more reliably in the Companion app than the global
    # extra-module injection.
    await _async_register_lovelace_resource(hass, card_url_versioned)
    return True


async def _async_register_lovelace_resource(hass: HomeAssistant, url: str) -> None:
    """Add/refresh the card as a Lovelace resource (storage mode only).

    Best-effort: YAML-mode dashboards manage resources in configuration.yaml,
    and the resource-collection API has shifted across HA versions, so any
    failure is logged and ignored — add_extra_js_url still covers loading.
    Keeps a single resource, updating its URL when the version changes.
    """
    base = url.split("?", 1)[0]
    try:
        lovelace = hass.data.get("lovelace")
        mode = getattr(lovelace, "mode", None)
        resources = getattr(lovelace, "resources", None)
        if mode != "storage" or resources is None:
            return
        if not getattr(resources, "loaded", False):
            if hasattr(resources, "async_load"):
                await resources.async_load()
            elif hasattr(resources, "async_get_info"):
                await resources.async_get_info()

        items = list(resources.async_items())
        existing = next(
            (it for it in items if str(it.get("url", "")).split("?", 1)[0] == base),
            None,
        )
        if existing is None:
            await resources.async_create_item({"res_type": "module", "url": url})
            _LOGGER.debug("Added Lovelace resource %s", url)
        elif existing.get("url") != url:
            await resources.async_update_item(existing["id"], {"url": url})
            _LOGGER.debug("Updated Lovelace resource to %s", url)
    except Exception as err:  # noqa: BLE001 — never block setup on the resource
        _LOGGER.debug("Could not register Lovelace resource (%s): %s", base, err)


async def async_setup_entry(hass: HomeAssistant, entry: KaeserSC2ConfigEntry) -> bool:
    """Set up Kaeser SC2 from a config entry."""
    client = SigmaControl2(
        host=entry.data[CONF_HOST],
        username=entry.data.get(CONF_USERNAME, DEFAULT_USERNAME),
        password=entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
        timeout=15,
    )

    # Options override data for poll_interval
    poll_interval = entry.options.get(
        "poll_interval",
        entry.data.get("poll_interval", DEFAULT_POLL_INTERVAL),
    )

    coordinator = KaeserSC2Coordinator(
        hass,
        client=client,
        poll_interval=poll_interval,
        name=entry.data.get(CONF_NAME, entry.data[CONF_HOST]),
    )

    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates (e.g. poll interval change)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — adjust coordinator poll interval."""
    coordinator: KaeserSC2Coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator is None:
        return
    new_interval = entry.options.get(
        "poll_interval",
        entry.data.get("poll_interval", DEFAULT_POLL_INTERVAL),
    )
    _LOGGER.info("Updating poll interval for %s to %ds", entry.title, new_interval)
    coordinator.update_interval = timedelta(seconds=new_interval)


async def async_unload_entry(hass: HomeAssistant, entry: KaeserSC2ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: KaeserSC2Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.close()
    return unload_ok
