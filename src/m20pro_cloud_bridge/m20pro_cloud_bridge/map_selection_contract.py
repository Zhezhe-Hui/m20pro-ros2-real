"""Pure selected-map status helpers.

The mature 2D line compares the selected fixed map against live Nav2 /map.
The v3 line is pure 3D, so its selected-map gate must be driven by the loaded
3D map assets instead of Nav2 occupancy-grid metadata.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, Optional

from .task_contract import map_metadata_mismatch_error, readiness_failure, readiness_success
from .map_identity_contract import map_content_match


NowText = Callable[[], str]


def default_now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _map_summary(map_payload: Dict[str, Any], *, include_map_id: bool) -> Dict[str, Any]:
    summary = {
        "available": bool(map_payload.get("available")),
        "width": map_payload.get("width"),
        "height": map_payload.get("height"),
        "resolution": map_payload.get("resolution"),
        "origin": map_payload.get("origin"),
    }
    if map_payload.get("content_digest"):
        summary["content_digest"] = map_payload.get("content_digest")
    if include_map_id:
        summary = {
            "map_id": map_payload.get("map_id"),
            "name": map_payload.get("name"),
            "floor": map_payload.get("floor"),
            **summary,
        }
    return summary


def selected_map_status_payload(
    *,
    selected_map_id: Optional[str],
    live_map: Dict[str, Any],
    selected_map: Dict[str, Any],
    min_update_time: Optional[float] = None,
    now_text: Optional[NowText] = None,
) -> Dict[str, Any]:
    selected_id = str(selected_map_id or "").strip()
    if not selected_id:
        return readiness_failure(
            "selected_map_missing",
            "当前没有选中固定地图；实时 /map 不能保存任务点或生成任务",
            {"selected_map_id": None},
            now_text=now_text or default_now_text,
        )

    live_payload = dict(live_map or {})
    selected_payload = dict(selected_map or {})
    detail = {
        "selected_map_id": selected_id,
        "selected_map": _map_summary(selected_payload, include_map_id=True),
        "live_map": _map_summary(live_payload, include_map_id=False),
    }
    metadata_error = map_metadata_mismatch_error(live_payload, selected_payload)
    if metadata_error:
        return readiness_failure(
            "selected_map_metadata_mismatch",
            str(metadata_error.get("message") or "网页选择地图与 Nav2 当前加载地图不一致"),
            {**detail, "detail": metadata_error},
            now_text=now_text or default_now_text,
        )
    # Full map snapshots carry a normalized occupancy digest.  Lightweight
    # summaries do not, so existing display-only callers keep metadata-only
    # behavior while map-switch postconditions become content-strict.
    if selected_payload.get("content_digest"):
        content = map_content_match(selected_payload, live_payload, require_digest=True)
        if not content.get("ok"):
            return readiness_failure(
                "selected_map_content_mismatch",
                str(content.get("message") or "网页选择地图与 Nav2 当前 /map 内容不一致"),
                {**detail, "content": content},
                now_text=now_text or default_now_text,
            )
    if min_update_time is not None:
        try:
            live_update = float(live_payload.get("last_update", 0.0) or 0.0)
            update_barrier = float(min_update_time)
        except (TypeError, ValueError):
            live_update = 0.0
            update_barrier = float("inf")
        if live_update < update_barrier:
            return readiness_failure(
                "selected_map_sample_before_transaction",
                "Nav2 /map 内容正确，但尚未收到本次切图后的新样本",
                {
                    **detail,
                    "map_update_time": live_update,
                    "map_min_update_time": update_barrier,
                },
                now_text=now_text or default_now_text,
            )
    return readiness_success(
        "网页选择地图与 Nav2 当前 /map 一致",
        {
            **detail,
            **(
                {
                    "map_update_time": float(live_payload.get("last_update", 0.0) or 0.0),
                    "map_min_update_time": float(min_update_time),
                }
                if min_update_time is not None
                else {}
            ),
        },
        now_text=now_text or default_now_text,
    )


def _dddmr_asset_summary(map_status: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(map_status or {})
    return {
        "ready": bool(payload.get("ready")),
        "floor": payload.get("floor"),
        "provisional": bool(payload.get("provisional")),
        "mapcloud_points": payload.get("mapcloud_points"),
        "mapground_points": payload.get("mapground_points"),
        "mapcloud_files": list(payload.get("mapcloud_files") or []),
        "mapground_files": list(payload.get("mapground_files") or []),
        "code": payload.get("code"),
        "source": payload.get("source"),
        "frame_id": payload.get("frame_id"),
        "error": payload.get("error"),
    }


def selected_dddmr_map_status_payload(
    *,
    selected_map_id: Optional[str],
    selected_map: Dict[str, Any],
    map_status: Dict[str, Any],
    now_text: Optional[NowText] = None,
) -> Dict[str, Any]:
    """Return selected-map readiness for the pure-3D backend.

    A v3 task should not fail just because Nav2 /map is absent.  The relevant
    map evidence is whether the 3D asset server has published non-empty
    mapcloud/mapground assets for the operational floor.
    """

    selected_id = str(selected_map_id or "").strip() or None
    selected_payload = dict(selected_map or {})
    status_payload = dict(map_status or {})
    detail = {
        "selected_map_id": selected_id,
        "selected_map": _map_summary(selected_payload, include_map_id=True),
        "map_3d": _dddmr_asset_summary(status_payload),
    }
    if not status_payload.get("ready"):
        return readiness_failure(
            "dddmr_map_assets_unavailable",
            str(status_payload.get("error") or status_payload.get("code") or "三维地图资产未就绪"),
            detail,
            now_text=now_text or default_now_text,
        )
    selected_floor = str(selected_payload.get("floor") or "").strip()
    asset_floor = str(status_payload.get("floor") or "").strip()
    if selected_floor and asset_floor and selected_floor != asset_floor:
        return readiness_failure(
            "selected_map_floor_mismatch",
            "当前选择地图楼层与三维地图资产楼层不一致",
            detail,
            now_text=now_text or default_now_text,
        )
    return readiness_success(
        "三维地图资产已就绪",
        detail,
        now_text=now_text or default_now_text,
    )


def matching_fixed_map_id_for_live_map(
    live_map: Dict[str, Any],
    candidates: Iterable[Dict[str, Any]],
) -> Optional[str]:
    if not isinstance(live_map, dict) or not live_map.get("available"):
        return None
    matches = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        map_id = str(candidate.get("id") or candidate.get("map_id") or "").strip()
        if not map_id:
            continue
        summary = candidate.get("summary") if isinstance(candidate.get("summary"), dict) else candidate
        if not summary.get("available") or map_metadata_mismatch_error(live_map, summary) is not None:
            continue
        if summary.get("content_digest"):
            content = map_content_match(summary, live_map, require_digest=True)
            if not content.get("ok"):
                continue
        matches.append(candidate)
    if not matches:
        return None
    preferred = next((item for item in matches if item.get("source") != "project_builtin"), matches[0])
    return str(preferred.get("id") or preferred.get("map_id") or "").strip() or None


def effective_map_id_for_display(
    *,
    selected_map_id: Optional[str],
    live_map: Dict[str, Any],
    candidates: Iterable[Dict[str, Any]],
    working_map_id: Optional[str] = None,
) -> Optional[str]:
    selected = str(selected_map_id or "").strip()
    if selected:
        return selected
    candidate_list = [item for item in candidates if isinstance(item, dict)]
    live_match = matching_fixed_map_id_for_live_map(live_map, candidate_list)
    if live_match:
        return live_match
    if isinstance(live_map, dict) and live_map.get("available"):
        return None
    working = str(working_map_id or "").strip()
    if not working:
        return None
    for candidate in candidate_list:
        candidate_id = str(candidate.get("id") or candidate.get("map_id") or "").strip()
        if candidate_id == working:
            return working
    return None


def map_relocalization_required_payload(
    *,
    map_id: Optional[str],
    map_name: Optional[str],
    yaml_path: Optional[str],
    reason: str,
    now_text: Optional[NowText] = None,
) -> Dict[str, Any]:
    reason_key = str(reason or "map_loaded").strip()
    if reason_key == "startup_sync":
        message = "启动后已把当前固定地图同步到 Nav2，必须重新按开发手册2101定位"
    else:
        message = "当前固定地图已选择并同步到 Nav2，必须重新按开发手册2101定位"
    return {
        "map_id": map_id,
        "map_name": map_name,
        "yaml_path": yaml_path,
        "loaded_at": (now_text or default_now_text)(),
        "reason": reason_key,
        "message": message,
    }


def selected_map_wait_timeout_payload(
    *,
    selected_map_id: Optional[str],
    now_text: Optional[NowText] = None,
) -> Dict[str, Any]:
    return readiness_failure(
        "selected_map_metadata_mismatch",
        "等待 Nav2 /map 更新超时",
        {"selected_map_id": selected_map_id},
        now_text=now_text or default_now_text,
    )


def apply_selected_map_choice_state(
    settings: Dict[str, Any],
    *,
    map_id: Optional[str],
    previous_map_id: Optional[str],
    record: Optional[Dict[str, Any]],
    nav2_load: Dict[str, Any],
    reason: str = "manual_select",
    now_text: Optional[NowText] = None,
) -> Dict[str, Any]:
    updated = dict(settings)
    selected_id = str(map_id or "").strip() or None
    selection_changed = str(previous_map_id or "") != str(selected_id or "")
    updated["selected_map_id"] = selected_id
    if selected_id:
        updated["working_map_id"] = selected_id
    relocalization_required = None
    if selected_id and (selection_changed or bool(nav2_load.get("loaded"))):
        relocalization_required = map_relocalization_required_payload(
            map_id=selected_id,
            map_name=record.get("name") if isinstance(record, dict) else None,
            yaml_path=nav2_load.get("yaml_path"),
            reason=str(reason or "manual_select"),
            now_text=now_text or default_now_text,
        )
        updated["map_relocalization_required"] = relocalization_required
    else:
        relocalization_required = updated.get("map_relocalization_required")
    return {
        "settings": updated,
        "selection_changed": selection_changed,
        "relocalization_required": relocalization_required,
        "clear_pose": bool(selected_id and (selection_changed or bool(nav2_load.get("loaded")))),
    }
