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
        self._consecutive_failures = 0

    async def _async_update_data(self) -> CompressorData:
        """Fetch data from the SC2 controller."""
        try:
            data = await self.client.poll()
        except Exception as exc:
            self._consecutive_failures += 1
            if self._consecutive_failures <= 3:
                _LOGGER.warning(
                    "Error polling %s (attempt %d): %s",
                    self.client.host, self._consecutive_failures, exc,
                )
            raise UpdateFailed(
                f"Error polling {self.client.host}: {exc}"
            ) from exc

        if not data.online:
            self._consecutive_failures += 1
            if self._consecutive_failures <= 3 or self._consecutive_failures % 10 == 0:
                _LOGGER.warning(
                    "Controller %s offline (attempt %d) — will retry",
                    self.client.host, self._consecutive_failures,
                )
            raise UpdateFailed(
                f"Controller {self.client.host} is offline"
            )

        # Reset failure counter on success
        if self._consecutive_failures > 0:
            _LOGGER.info(
                "Controller %s back online after %d failed polls",
                self.client.host, self._consecutive_failures,
            )
        self._consecutive_failures = 0
        return data
