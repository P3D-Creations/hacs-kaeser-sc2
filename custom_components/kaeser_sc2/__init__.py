"""Kaeser Sigma Control 2 — Home Assistant Integration."""

from __future__ import annotations

import logging
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

CARD_URL = "/kaeser_sc2/kaeser-sc2-card.js"
CARD_JS_PATH = Path(__file__).parent / "frontend" / "kaeser-sc2-card.js"
IMAGES_URL = "/kaeser_sc2/images"
IMAGES_PATH = Path(__file__).parent / "frontend" / "images"

type KaeserSC2ConfigEntry = ConfigEntry


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the custom card JS and static image assets."""
    _LOGGER.debug(
        "Registering frontend: JS=%s (exists=%s), images=%s (exists=%s)",
        CARD_JS_PATH, CARD_JS_PATH.exists(),
        IMAGES_PATH, IMAGES_PATH.exists(),
    )
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(CARD_JS_PATH), cache_headers=False),
        StaticPathConfig(IMAGES_URL, str(IMAGES_PATH), cache_headers=True),
    ])
    add_extra_js_url(hass, CARD_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KaeserSC2ConfigEntry) -> bool:
    """Set up Kaeser SC2 from a config entry."""
    client = SigmaControl2(
        host=entry.data[CONF_HOST],
        username=entry.data.get(CONF_USERNAME, DEFAULT_USERNAME),
        password=entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
        timeout=15,
    )

    poll_interval = entry.data.get("poll_interval", DEFAULT_POLL_INTERVAL)

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

    return True


async def async_unload_entry(hass: HomeAssistant, entry: KaeserSC2ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: KaeserSC2Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.close()
    return unload_ok
