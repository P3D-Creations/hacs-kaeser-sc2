"""Utility helpers for Kaeser SC2 integration."""

from __future__ import annotations

import re


def slugify_name(name: str) -> str:
    """Convert a user-provided name to a HA-friendly slug.

    Example: "Shop Air Compressor" → "shop_air_compressor"
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9_]+", "_", slug)
    slug = slug.strip("_")
    return slug
