#!/usr/bin/env python3
"""Summarize /api/state navigation_backend for shell status scripts.

This is the shared source of truth for DDDMR and preview CLI summaries.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_navigation"))

from m20pro_navigation.dddmr_field_test_contract import (  # noqa: E402
    evaluate_dddmr_field_test_acceptance,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _navigation_backend_mode(*values: Any) -> str:
    aliases = {
        "move": "dddmr_3d",
        "dddmr": "dddmr_3d",
        "nav2": "nav2_2d",
        "nav2_2d": "nav2_2d",
        "dddmr_3d": "dddmr_3d",
    }
    for value in values:
        text = str(value or "").strip()
        if text in aliases:
            return aliases[text]
    return str(next((value for value in values if value), "unknown"))


def summarize_navigation_state(payload: Dict[str, Any], *, now_s: Any = None) -> Dict[str, Any]:
    now_value = time.time() if now_s is None else now_s
    backend = _as_dict(payload.get("navigation_backend"))
    field_test = _as_dict(backend.get("field_test"))
    field_test_mode = _as_dict(
        payload.get("field_test_mode")
        or payload.get("dddmr_field_test_mode")
        or backend.get("field_test_mode")
    )
    field_test_mode_current = _as_dict(field_test_mode.get("current"))
    runtime = _as_dict(backend.get("runtime"))
    gnss = _as_dict(backend.get("gnss"))
    edge_cloud = _as_dict(backend.get("edge_cloud"))
    map_3d = _as_dict(backend.get("map_3d"))
    assets = _as_dict(payload.get("dddmr_map_assets"))
    active_task = _as_dict(payload.get("active_task"))
    command_mux_status = _as_dict(payload.get("command_mux_status"))
    selected_map_status = _as_dict(payload.get("selected_map_status"))
    map_relocalization_required = _as_dict(payload.get("map_relocalization_required"))
    localization_status = _as_dict(payload.get("localization_status"))
    workspace = _as_dict(assets.get("workspace"))
    status_sample = _as_dict(assets.get("status"))
    parsed_status = _as_dict(status_sample.get("parsed"))
    status = parsed_status or status_sample
    notes = field_test.get("notes")
    if not isinstance(notes, list):
        notes = []
    ready_count = sum(1 for item in notes if isinstance(item, dict) and item.get("ready"))
    total_count = len(notes)
    existing_acceptance = _as_dict(field_test.get("acceptance"))
    if existing_acceptance:
        acceptance = existing_acceptance
    else:
        acceptance = evaluate_dddmr_field_test_acceptance(
            field_test,
            active_task=active_task,
            command_mux_status=command_mux_status,
            selected_map_status=selected_map_status,
            map_relocalization_required=map_relocalization_required,
            localization_status=localization_status,
            now_s=now_value,
        )
    return {
        "backend": str(backend.get("backend") or ""),
        "bridge_seen": bool(backend.get("bridge_seen")),
        "ready": bool(field_test.get("ready")),
        "reason": str(field_test.get("reason") or ""),
        "mode": str(field_test.get("mode") or backend.get("backend") or "unknown"),
        "runtime_backend": str(field_test.get("runtime_backend") or runtime.get("backend") or ""),
        "notes_ready": ready_count,
        "notes_total": total_count,
        "runtime": {
            "seen": bool(runtime),
            "backend": str(runtime.get("backend") or ""),
            "ready": bool(runtime.get("ready")),
            "state": str(runtime.get("state") or ""),
            "code": str(runtime.get("code") or ""),
            "tf_ready": bool(runtime.get("tf_ready")),
            "tf_code": str(runtime.get("tf_code") or ""),
            "max_goal_distance_m": runtime.get("max_goal_distance_m"),
        },
        "field_test": {
            "ready": bool(field_test.get("ready")),
            "reason": str(field_test.get("reason") or ""),
            "mode": str(field_test.get("mode") or backend.get("backend") or "unknown"),
            "runtime_backend": str(field_test.get("runtime_backend") or runtime.get("backend") or ""),
            "notes_ready": ready_count,
            "notes_total": total_count,
            "acceptance": acceptance,
        },
        "field_test_mode": {
            "available": bool(field_test_mode.get("available")),
            "script": str(field_test_mode.get("script") or ""),
            "current_mode": _navigation_backend_mode(
                field_test_mode_current.get("navigation_backend"),
                backend.get("backend"),
                field_test_mode_current.get("mode"),
                field_test.get("mode"),
            ),
            "current_label": str(field_test_mode_current.get("label") or ""),
            "current_navigation_backend": str(field_test_mode_current.get("navigation_backend") or backend.get("backend") or ""),
            "current_motion_enabled": bool(field_test_mode_current.get("motion_enabled")),
            "current_field_test_ready": bool(field_test_mode_current.get("field_test_ready")),
        },
        "gnss": {
            "ready": bool(gnss.get("ready")),
            "code": str(gnss.get("code") or ""),
            "anchor_usable": bool(gnss.get("anchor_usable")),
            "source_topic": str(gnss.get("source_topic") or ""),
            "fix_topic": str(gnss.get("fix_topic") or ""),
            "latitude": gnss.get("latitude"),
            "longitude": gnss.get("longitude"),
            "altitude_m": gnss.get("altitude_m"),
            "speed_kmh": gnss.get("speed_kmh"),
            "course_deg": gnss.get("course_deg"),
            "num_satellites": gnss.get("num_satellites"),
            "visible_satellites": gnss.get("visible_satellites"),
            "pdop": gnss.get("pdop"),
            "hdop": gnss.get("hdop"),
            "vdop": gnss.get("vdop"),
        },
        "edge_cloud": {
            "ready": bool(edge_cloud.get("ready")),
            "code": str(edge_cloud.get("code") or ""),
            "finite_points": _as_int(edge_cloud.get("finite_points")),
            "frame_id": str(edge_cloud.get("frame_id") or ""),
        },
        "map_3d": {
            "ready": bool(map_3d.get("ready")),
            "mapcloud_ready": bool(map_3d.get("mapcloud_ready")),
            "mapground_ready": bool(map_3d.get("mapground_ready")),
            "mapcloud_points": _as_int(map_3d.get("mapcloud_points")),
            "mapground_points": _as_int(map_3d.get("mapground_points")),
        },
        "assets": {
            "ready_floor_count": _as_int(workspace.get("ready_floor_count")),
            "floor_count": _as_int(workspace.get("floor_count")),
            "manifest_path": str(assets.get("manifest_path") or ""),
            "status": {
                "ready": bool(status.get("ready")),
                "provisional": bool(status.get("provisional")),
                "code": str(status.get("code") or ""),
                "source": str(status.get("source") or ""),
                "floor": str(status.get("floor") or ""),
                "frame_id": str(status.get("frame_id") or ""),
                "mapcloud_points": _as_int(status.get("mapcloud_points")),
                "mapground_points": _as_int(status.get("mapground_points")),
                "last_update": status_sample.get("last_update"),
            },
        },
    }


def main() -> None:
    text = sys.stdin.read()
    if not text.strip():
        print("unavailable")
        return
    try:
        payload = json.loads(text)
    except Exception:
        print("unavailable")
        return
    print(json.dumps(summarize_navigation_state(payload), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
