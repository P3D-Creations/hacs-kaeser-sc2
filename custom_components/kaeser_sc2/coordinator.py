"""DataUpdateCoordinator for Kaeser Sigma Control 2."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CompressorData, SigmaControl2
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class KaeserSC2Coordinator(DataUpdateCoordinator[CompressorData]):
    """Coordinator that polls one SC2 controller."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SigmaControl2,
        poll_interval: int,
        name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{name}",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client

    async def _async_update_data(self) -> CompressorData:
        """Fetch data from the SC2 controller."""
        try:
            data = await self.client.poll()
        except Exception as exc:
            raise UpdateFailed(f"Error polling {self.client.host}: {exc}") from exc

        if not data.online:
            raise UpdateFailed(f"Controller {self.client.host} is offline")

        return data
