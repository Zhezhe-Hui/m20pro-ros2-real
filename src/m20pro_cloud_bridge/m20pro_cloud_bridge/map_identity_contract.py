"""Immutable occupancy-map identity helpers used by map transactions.

Metadata such as width and resolution is useful for a quick sanity check but
does not prove that Nav2 loaded the requested occupancy grid.  This module
provides one deterministic digest for the normalized OccupancyGrid payload so
the Web node can compare the archived map with the live ``/map`` sample.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any, Dict, Optional


def occupancy_grid_content_digest(payload: Dict[str, Any]) -> Optional[str]:
    """Return a digest of normalized map metadata and occupancy cells.

    Floating-point geometry is deliberately excluded: map metadata has its own
    tolerance-aware validation, while YAML ``0.1`` becomes the float32 value
    ``0.10000000149011612`` on the OccupancyGrid wire.  The digest therefore
    identifies the discrete grid shape and cells only.  Occupancy values are
    encoded as signed 32-bit integers to keep the result independent of Python
    list/array implementations and ROS serialization details.
    """
    if not isinstance(payload, dict) or not payload.get("available"):
        return None
    try:
        width = int(payload["width"])
        height = int(payload["height"])
        cells = payload["data"]
        if width <= 0 or height <= 0 or not isinstance(cells, (list, tuple)):
            return None
        if len(cells) != width * height:
            return None
        normalized = [int(value) for value in cells]
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if any(value < -1 or value > 100 for value in normalized):
        return None
    digest = hashlib.sha256()
    digest.update(struct.pack("<II", width, height))
    digest.update(b"".join(struct.pack("<i", value) for value in normalized))
    return digest.hexdigest()


def map_content_match(
    expected: Dict[str, Any],
    observed: Dict[str, Any],
    *,
    require_digest: bool = True,
) -> Dict[str, Any]:
    """Compare one archived map payload with a live OccupancyGrid payload."""
    expected_digest = str(
        expected.get("content_digest") or occupancy_grid_content_digest(expected) or ""
    )
    observed_digest = str(
        observed.get("content_digest") or occupancy_grid_content_digest(observed) or ""
    )
    if not expected_digest or not observed_digest:
        return {
            "ok": not require_digest,
            "code": "map_content_digest_missing",
            "message": "地图内容摘要缺失，不能确认 /map 与归档地图一致" if require_digest else "地图内容摘要未提供",
            "expected_digest": expected_digest or None,
            "observed_digest": observed_digest or None,
        }
    return {
        "ok": expected_digest == observed_digest,
        "code": "map_content_match" if expected_digest == observed_digest else "map_content_mismatch",
        "message": "地图内容摘要一致" if expected_digest == observed_digest else "Nav2 /map 内容摘要与目标地图不一致",
        "expected_digest": expected_digest,
        "observed_digest": observed_digest,
    }
