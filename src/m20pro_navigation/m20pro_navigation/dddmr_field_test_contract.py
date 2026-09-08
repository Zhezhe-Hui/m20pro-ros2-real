"""Shared contracts for DDDMR readiness and acceptance."""

from __future__ import annotations

import math
import time
from typing import Any, Dict, Mapping, Optional


ACTIVE_TASK_RUNNING_STATUSES = {
    "running",
    "dispatching",
    "waiting",
    "paused",
    "canceling",
    "stopping",
}
COMMAND_MUX_STATUS_TIMEOUT_S = 3.0


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_finite_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def active_task_summary(active_task: Any) -> Dict[str, Any]:
    task = _as_dict(active_task)
    status = str(task.get("status") or "").strip().lower()
    running = bool(task) and (not status or status in ACTIVE_TASK_RUNNING_STATUSES)
    return {
        "seen": bool(task),
        "running": running,
        "task_id": str(task.get("task_id") or task.get("id") or ""),
        "status": str(task.get("status") or ""),
        "task_name": str(task.get("task_name") or task.get("name") or ""),
        "multi_floor": bool(task.get("multi_floor")),
    }


def command_mux_summary(
    command_mux_status: Any,
    *,
    now_s: Optional[float] = None,
    timeout_s: float = COMMAND_MUX_STATUS_TIMEOUT_S,
) -> Dict[str, Any]:
    sample = _as_dict(command_mux_status)
    parsed = _as_dict(sample.get("parsed"))
    status = _as_dict(parsed)
    updated_at = sample.get("last_update")
    if updated_at is None:
        updated_at = status.get("updated_at")
    updated_at_s = _as_finite_float(updated_at)
    now_value = _as_finite_float(now_s)
    age_s = None
    if updated_at_s is not None and now_value is not None:
        age_s = max(0.0, now_value - updated_at_s)
    stale = bool(sample) and (
        updated_at_s is None
        or (age_s is not None and age_s > float(timeout_s))
    )
    return {
        "seen": bool(sample),
        "mode": str(status.get("mode") or ""),
        "reason": str(status.get("reason") or ""),
        "output_nonzero": bool(status.get("output_nonzero")),
        "updated_at": updated_at_s,
        "age_s": age_s,
        "stale": stale,
    }


def evaluate_dddmr_field_test_acceptance(
    field_test: Optional[Mapping[str, Any]],
    *,
    active_task: Any = None,
    command_mux_status: Any = None,
    selected_map_status: Any = None,
    map_relocalization_required: Any = None,
    localization_status: Any = None,
    now_s: Optional[float] = None,
    command_mux_timeout_s: float = COMMAND_MUX_STATUS_TIMEOUT_S,
) -> Dict[str, Any]:
    field_test_payload = _as_dict(field_test)
    active = active_task_summary(active_task)
    mux = command_mux_summary(
        command_mux_status,
        now_s=time.time() if now_s is None else now_s,
        timeout_s=command_mux_timeout_s,
    )
    field_test_ready = bool(field_test_payload.get("ready"))
    field_test_reason = str(field_test_payload.get("reason") or "")
    field_test_mode = str(field_test_payload.get("mode") or "")
    field_test_runtime_backend = str(field_test_payload.get("runtime_backend") or "")
    selected_map = _as_dict(selected_map_status)
    localization = _as_dict(localization_status)
    relocalization_lock = _as_dict(map_relocalization_required)
    selected_map_ready = True
    localization_confirmed = True
    if selected_map:
        selected_map_ready = selected_map.get("ready") is True
    if localization:
        localization_confirmed = localization.get("confirmed") is True

    blocked_by = []
    if not field_test_ready:
        blocked_by.append("field_test")
    if not selected_map_ready:
        blocked_by.append("selected_map")
    if relocalization_lock:
        blocked_by.append("map_relocalization")
    if not localization_confirmed:
        blocked_by.append("localization")
    if active["running"]:
        blocked_by.append("active_task")
    if not mux["seen"] or mux["stale"] or mux["output_nonzero"]:
        blocked_by.append("command_mux")
    if not blocked_by:
        reason = "field_test_acceptance_ready"
    elif "field_test" in blocked_by:
        reason = field_test_reason or "field_test_not_ready"
    elif "selected_map" in blocked_by:
        reason = str(selected_map.get("code") or "field_test_selected_map_not_ready")
    elif "map_relocalization" in blocked_by:
        reason = "field_test_map_relocalization_required"
    elif "localization" in blocked_by:
        reason = str(localization.get("code") or "field_test_localization_not_confirmed")
    elif "active_task" in blocked_by:
        reason = "field_test_active_task_running"
    elif not mux["seen"]:
        reason = "field_test_command_mux_status_missing"
    elif mux["stale"]:
        reason = "field_test_command_mux_status_stale"
    else:
        reason = "field_test_command_mux_output_nonzero"

    ready = not blocked_by
    return {
        "ready": ready,
        "reason": reason,
        "blocked_by": blocked_by,
        "field_test_ready": field_test_ready,
        "field_test_reason": field_test_reason,
        "mode": field_test_mode,
        "runtime_backend": field_test_runtime_backend,
        "active_task": active,
        "command_mux": mux,
        "selected_map_status": selected_map or None,
        "map_relocalization_required": relocalization_lock or None,
        "localization_status": localization or None,
    }


def evaluate_dddmr_field_test_state(
    field_test: Optional[Mapping[str, Any]],
    *,
    active_task: Any = None,
    command_mux_status: Any = None,
    selected_map_status: Any = None,
    map_relocalization_required: Any = None,
    localization_status: Any = None,
    now_s: Optional[float] = None,
    command_mux_timeout_s: float = COMMAND_MUX_STATUS_TIMEOUT_S,
) -> Dict[str, Any]:
    field_test_payload = _as_dict(field_test)
    acceptance = evaluate_dddmr_field_test_acceptance(
        field_test_payload,
        active_task=active_task,
        command_mux_status=command_mux_status,
        selected_map_status=selected_map_status,
        map_relocalization_required=map_relocalization_required,
        localization_status=localization_status,
        now_s=now_s,
        command_mux_timeout_s=command_mux_timeout_s,
    )
    payload = dict(field_test_payload)
    payload["acceptance"] = acceptance
    return payload


__all__ = [
    "ACTIVE_TASK_RUNNING_STATUSES",
    "COMMAND_MUX_STATUS_TIMEOUT_S",
    "active_task_summary",
    "command_mux_summary",
    "evaluate_dddmr_field_test_acceptance",
    "evaluate_dddmr_field_test_state",
]
