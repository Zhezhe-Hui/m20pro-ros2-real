"""Pure GNSS normalization helpers for the M20Pro navigation stack.

The vendor publishes GNSS as ``drdds/msg/NavSat`` on ``/GPS``.  This module
keeps the interpretation independent from ROS imports so contracts can be
tested on development machines that do not have the factory ``drdds`` package.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional


GNSS_SOURCE_TOPIC = "/GPS"
GNSS_FIX_TOPIC = "/m20pro/gnss/fix"
GNSS_STATUS_TOPIC = "/m20pro/gnss/status"
GNSS_FRAME_ID = "m20pro_gnss"
_GNSS_CONTAINER_KEYS = ("data", "GPS", "gps", "Items", "items")


def _get_field(source: Any, names: Iterable[str], default: Any = None) -> Any:
    visited = set()

    def visit(node: Any) -> tuple[bool, Any]:
        if node is None:
            return False, default
        node_id = id(node)
        if node_id in visited:
            return False, default
        visited.add(node_id)
        for name in names:
            if isinstance(node, dict) and name in node:
                return True, node.get(name)
            if hasattr(node, name):
                return True, getattr(node, name)
        children = []
        if isinstance(node, dict):
            for key in _GNSS_CONTAINER_KEYS:
                if key in node:
                    child = node.get(key)
                    if isinstance(child, list):
                        children.extend(child)
                    else:
                        children.append(child)
        else:
            for key in _GNSS_CONTAINER_KEYS:
                if hasattr(node, key):
                    child = getattr(node, key)
                    if isinstance(child, list):
                        children.extend(child)
                    else:
                        children.append(child)
        for child in children:
            found, value = visit(child)
            if found:
                return True, value
        return False, default

    found, value = visit(source)
    return value if found else default


def _finite_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _int_value(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _valid_latitude(value: Optional[float]) -> bool:
    return value is not None and -90.0 <= value <= 90.0


def _valid_longitude(value: Optional[float]) -> bool:
    return value is not None and -180.0 <= value <= 180.0


def normalize_gnss_sample(
    message_or_value: Any,
    *,
    source_topic: str = GNSS_SOURCE_TOPIC,
    received_at: Optional[float] = None,
) -> Dict[str, Any]:
    """Normalize vendor ``NavSat`` or basic_server GPS data into one schema.

    The helper accepts flat ``Latitude``/``Longitude`` style payloads, nested
    ``GPS`` groups, and message wrappers that place the GNSS payload under
    ``data`` or ``Items``.
    """

    value = _get_field(message_or_value, ("data",), message_or_value)
    latitude = _finite_float(_get_field(value, ("latitude", "Latitude", "GPS.Latitude")))
    longitude = _finite_float(_get_field(value, ("longitude", "Longitude", "GPS.Longitude")))
    speed_kmh = _finite_float(_get_field(value, ("speed", "Speed", "GPS.Speed")))
    course_deg = _finite_float(_get_field(value, ("course", "Course", "GPS.Course")))
    fix_quality = _int_value(_get_field(value, ("fixquality", "FixQuality", "GPS.FixQuality")))
    num_satellites = _int_value(
        _get_field(value, ("numsatellites", "NumSatellites", "GPS.NumSatellites"))
    )
    altitude_m = _finite_float(_get_field(value, ("altitude", "Altitude", "GPS.Altitude")))
    pdop = _finite_float(_get_field(value, ("pdop", "PDOP", "GPS.PDOP")))
    hdop = _finite_float(_get_field(value, ("hdop", "HDOP", "GPS.HDOP")))
    vdop = _finite_float(_get_field(value, ("vdop", "VDOP", "GPS.VDOP")))
    total_messages = _int_value(
        _get_field(value, ("totalmessages", "TotalMessages", "GPS.TotalMessages"))
    )
    current_message = _int_value(
        _get_field(value, ("currentmessage", "CurrentMessage", "GPS.CurrentMessage"))
    )
    visible_satellites = _int_value(
        _get_field(value, ("visiblesatellites", "VisibleSatellites", "GPS.VisibleSatellites"))
    )

    fix_valid = (
        fix_quality == 1
        and _valid_latitude(latitude)
        and _valid_longitude(longitude)
    )
    return {
        "source_topic": source_topic,
        "received": True,
        "received_at": received_at,
        "latitude": latitude,
        "longitude": longitude,
        "altitude_m": altitude_m,
        "speed_kmh": speed_kmh,
        "course_deg": course_deg,
        "fix_quality": fix_quality,
        "num_satellites": num_satellites,
        "visible_satellites": visible_satellites,
        "pdop": pdop,
        "hdop": hdop,
        "vdop": vdop,
        "total_messages": total_messages,
        "current_message": current_message,
        "fix_valid": fix_valid,
    }


def gnss_quality_status(
    sample: Optional[Dict[str, Any]],
    *,
    enabled: bool = True,
    message_type_available: bool = True,
    age_s: Optional[float] = None,
    timeout_s: float = 3.0,
    max_hdop: float = 2.5,
    min_satellites: int = 6,
    source_topic: str = GNSS_SOURCE_TOPIC,
    fix_topic: str = GNSS_FIX_TOPIC,
) -> Dict[str, Any]:
    """Return a conservative GNSS readiness payload.

    ``ready`` means the GNSS sample is useful as a global map anchor.  It does
    not authorize motion and is intentionally separate from navigation backend
    admission.
    """

    base: Dict[str, Any] = {
        "component": "m20pro_gnss_adapter",
        "enabled": bool(enabled),
        "message_type_available": bool(message_type_available),
        "source_topic": source_topic,
        "fix_topic": fix_topic,
        "ready": False,
        "anchor_usable": False,
        "used_for_motion": False,
        "code": "gnss_waiting",
        "age_s": age_s,
        "timeout_s": float(timeout_s),
        "max_hdop": float(max_hdop),
        "min_satellites": int(min_satellites),
    }
    if not enabled:
        base["code"] = "gnss_adapter_disabled"
        return base
    if not message_type_available:
        base["code"] = "gnss_message_type_missing"
        return base
    if not sample:
        return base
    base.update(sample)
    if age_s is not None:
        base["age_s"] = age_s
        if age_s > timeout_s:
            base["code"] = "gnss_stale"
            return base
    if not bool(sample.get("fix_valid")):
        base["code"] = "gnss_no_fix"
        return base
    satellites = sample.get("num_satellites")
    if isinstance(satellites, int) and satellites < min_satellites:
        base["code"] = "gnss_satellites_low"
        return base
    hdop = sample.get("hdop")
    if isinstance(hdop, (int, float)) and math.isfinite(float(hdop)):
        if float(hdop) > max_hdop:
            base["code"] = "gnss_hdop_high"
            return base
    base["ready"] = True
    base["anchor_usable"] = True
    base["code"] = "gnss_anchor_ready"
    return base


def covariance_from_dop(
    *,
    hdop: Optional[float],
    vdop: Optional[float],
    uere_m: float = 4.0,
) -> Dict[str, Any]:
    """Approximate NavSatFix covariance from DOP values."""

    uere = max(0.1, float(uere_m))
    h = _finite_float(hdop)
    v = _finite_float(vdop)
    if h is None or h <= 0.0:
        return {"type": 0, "covariance": [0.0] * 9}
    horizontal_var = (h * uere) ** 2
    vertical_var = ((v if v is not None and v > 0.0 else h) * uere) ** 2
    return {
        "type": 1,
        "covariance": [
            horizontal_var,
            0.0,
            0.0,
            0.0,
            horizontal_var,
            0.0,
            0.0,
            0.0,
            vertical_var,
        ],
    }
