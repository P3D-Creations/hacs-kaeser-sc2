"""Frontend registration for the Kaeser SC2 custom card."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
)
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARD_JS = "kaeser-sc2-card.js"
CARD_URL = "/kaeser_sc2/kaeser-sc2-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Register the custom card JS as a Lovelace resource."""
    # Serve the JS file from our integration directory
    hass.http.register_static_path(
        CARD_URL,
        str(Path(__file__).parent / ".." / ".." / ".." / "js" / CARD_JS),
        cache_headers=False,
    )
    _LOGGER.debug("Registered Kaeser SC2 card at %s", CARD_URL)
