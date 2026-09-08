"""Contracts for the M20Pro-specific DDDMR edge-cloud adapter.

The production sensor path is owned by 106. 104 accepts only the processed
PointCloud2 stream and never treats a LaserScan as a substitute for 3D data.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple


EDGE_CLOUD_SOURCE_TOPIC = "/m20pro/edge_cloud"
DDDMR_EDGE_CLOUD_TOPIC = "/dddmr/edge_cloud"
EDGE_CLOUD_STATUS_TOPIC = "/m20pro/dddmr/edge_cloud/status"
EXPECTED_EDGE_CLOUD_FRAME = "m20pro_base_link"


def _finite(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("point coordinates must be finite")
    return result


def validate_edge_cloud(
    points: Iterable[Sequence[Any]],
    *,
    frame_id: str,
    expected_frame: str = EXPECTED_EDGE_CLOUD_FRAME,
    min_points: int = 20,
    max_range_m: float = 30.0,
) -> Tuple[list[Tuple[float, float, float]], Dict[str, Any]]:
    """Filter and validate one processed edge-cloud frame.

    The frame must already be expressed in the robot base frame.  Transforming
    arbitrary source frames here would hide a bad 106 calibration and make a
    real DDDMR run unsafe, so the adapter fails closed instead.
    """

    actual_frame = str(frame_id or "").strip().lstrip("/")
    wanted_frame = str(expected_frame or EXPECTED_EDGE_CLOUD_FRAME).strip().lstrip("/")
    if not actual_frame:
        return [], {"ready": False, "code": "edge_cloud_frame_missing"}
    if actual_frame != wanted_frame:
        return [], {
            "ready": False,
            "code": "edge_cloud_frame_mismatch",
            "frame_id": actual_frame,
            "expected_frame": wanted_frame,
        }

    limit = _finite(max_range_m)
    if limit <= 0.0:
        raise ValueError("max_range_m must be positive")
    accepted: list[Tuple[float, float, float]] = []
    rejected = 0
    for point in points:
        try:
            x, y, z = (_finite(point[0]), _finite(point[1]), _finite(point[2]))
        except (IndexError, TypeError, ValueError):
            rejected += 1
            continue
        if x * x + y * y > limit * limit:
            rejected += 1
            continue
        accepted.append((x, y, z))

    minimum = max(1, int(min_points))
    ready = len(accepted) >= minimum
    return accepted, {
        "ready": ready,
        "code": "edge_cloud_ready" if ready else "edge_cloud_too_few_points",
        "frame_id": actual_frame,
        "expected_frame": wanted_frame,
        "finite_points": len(accepted),
        "rejected_points": rejected,
    }


def edge_cloud_status(
    *,
    ready: bool,
    code: str,
    frame_id: str = "",
    finite_points: int = 0,
    age_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the stable JSON status consumed by the DDDMR bridge and Web."""

    payload: Dict[str, Any] = {
        "component": "m20pro_dddmr_edge_cloud",
        "ready": bool(ready),
        "code": str(code),
        "source_topic": EDGE_CLOUD_SOURCE_TOPIC,
        "output_topic": DDDMR_EDGE_CLOUD_TOPIC,
        "frame_id": str(frame_id or ""),
        "finite_points": int(max(0, finite_points)),
    }
    if age_s is not None:
        try:
            payload["age_s"] = max(0.0, float(age_s))
        except (TypeError, ValueError):
            payload["age_s"] = None
    return payload


__all__ = [
    "DDDMR_EDGE_CLOUD_TOPIC",
    "EDGE_CLOUD_SOURCE_TOPIC",
    "EDGE_CLOUD_STATUS_TOPIC",
    "EXPECTED_EDGE_CLOUD_FRAME",
    "edge_cloud_status",
    "validate_edge_cloud",
]
