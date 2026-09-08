"""Pure contracts for supervising the v3 DDDMR-only backend."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional


NAVIGATION_BACKENDS = {"dddmr_3d", "nav2_2d"}
DDDMR_RESULT_RUNNING = 0
DDDMR_RESULT_SUCCESS = 1


def normalize_navigation_backend(value: Any) -> str:
    backend = str(value or "dddmr_3d").strip().lower()
    if backend not in NAVIGATION_BACKENDS:
        raise ValueError("unsupported navigation backend: %s" % backend)
    return backend


def navigation_backend_policy(value: Any, *, axis_enabled: bool) -> Dict[str, Any]:
    backend = normalize_navigation_backend(value)
    if backend == "nav2_2d":
        return {
            "backend": backend,
            "uses_nav2": True,
            "uses_dddmr": False,
            "navigate_to_pose_action": "/navigate_to_pose",
            "motion_enabled": bool(axis_enabled),
        }
    return {
        "backend": backend,
        "uses_nav2": False,
        "uses_dddmr": True,
        "navigate_to_pose_action": "/navigate_to_pose_3d",
        "motion_enabled": bool(axis_enabled),
    }


def task_start_requires_nav2_alignment(value: Any) -> bool:
    """v3 never gates task start on Nav2 local-costmap alignment."""

    return normalize_navigation_backend(value) == "dddmr_3d"


def dddmr_goal_admission(
    *,
    enabled: bool,
    motion_enabled: bool,
    action_type_available: bool,
    action_server_ready: bool,
    goal_active: bool,
    perception_ready: bool = True,
    map_ready: bool = True,
) -> Dict[str, Any]:
    if not enabled:
        return {"ok": False, "code": "dddmr_bridge_disabled"}
    if not motion_enabled:
        return {"ok": False, "code": "dddmr_motion_disabled"}
    if not action_type_available:
        return {"ok": False, "code": "dddmr_action_type_missing"}
    if not action_server_ready:
        return {"ok": False, "code": "dddmr_action_unavailable"}
    if not perception_ready:
        return {"ok": False, "code": "dddmr_edge_cloud_unavailable"}
    if not map_ready:
        return {"ok": False, "code": "dddmr_map_unavailable"}
    if goal_active:
        return {"ok": False, "code": "dddmr_goal_active"}
    return {"ok": True, "code": "dddmr_goal_admitted"}


def _finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("velocity values must be finite")
    return number


def _nonnegative_limit(value: Any, name: str) -> float:
    limit = _finite(value)
    if limit < 0.0:
        raise ValueError("%s must be nonnegative" % name)
    return limit


def bounded_dddmr_velocity(
    command: Mapping[str, Any],
    *,
    max_forward_speed_mps: float,
    max_reverse_speed_mps: float,
    max_lateral_speed_mps: float,
    max_angular_speed_radps: float,
) -> Dict[str, Any]:
    linear_x = _finite(command.get("linear_x", 0.0))
    linear_y = _finite(command.get("linear_y", 0.0))
    angular_z = _finite(command.get("angular_z", 0.0))
    max_forward = _nonnegative_limit(max_forward_speed_mps, "max_forward_speed_mps")
    max_reverse = _nonnegative_limit(max_reverse_speed_mps, "max_reverse_speed_mps")
    max_lateral = _nonnegative_limit(max_lateral_speed_mps, "max_lateral_speed_mps")
    max_angular = _nonnegative_limit(max_angular_speed_radps, "max_angular_speed_radps")
    bounded = {
        "linear_x": min(max_forward, max(-max_reverse, linear_x)),
        "linear_y": min(max_lateral, max(-max_lateral, linear_y)),
        "angular_z": min(max_angular, max(-max_angular, angular_z)),
    }
    return {
        **bounded,
        "clamped": any(
            not math.isclose(bounded[key], value, rel_tol=0.0, abs_tol=1e-12)
            for key, value in {
                "linear_x": linear_x,
                "linear_y": linear_y,
                "angular_z": angular_z,
            }.items()
        ),
    }


def dddmr_velocity_watchdog(
    *,
    goal_active: bool,
    active_age_s: Optional[float],
    command_age_s: Optional[float],
    startup_grace_s: float,
    command_timeout_s: float,
) -> Dict[str, Any]:
    if not goal_active:
        return {"stop": False, "code": "dddmr_idle"}
    if command_age_s is None:
        if active_age_s is not None and float(active_age_s) > max(0.1, float(startup_grace_s)):
            return {"stop": True, "code": "dddmr_cmd_vel_start_timeout"}
        return {"stop": False, "code": "dddmr_waiting_first_cmd_vel"}
    if float(command_age_s) > max(0.05, float(command_timeout_s)):
        return {"stop": True, "code": "dddmr_cmd_vel_timeout"}
    return {"stop": False, "code": "dddmr_cmd_vel_fresh"}


def dddmr_result_decision(*, transport_status: int, result_status: int) -> Dict[str, Any]:
    # action_msgs/GoalStatus.STATUS_SUCCEEDED is stable across Foxy and Humble.
    transport = int(transport_status)
    result = int(result_status)
    if transport == 4:
        if result == DDDMR_RESULT_SUCCESS:
            return {"succeeded": True, "code": "dddmr_goal_succeeded"}
        if result == DDDMR_RESULT_RUNNING:
            # Upstream commit 1d03673 succeeds with a default-constructed result.
            # Accept its zero only when the action transport proves terminal success.
            return {
                "succeeded": True,
                "code": "dddmr_goal_succeeded_default_result",
            }
    return {
        "succeeded": False,
        "code": "dddmr_goal_failed",
        "transport_status": transport,
        "result_status": result,
    }


__all__ = [
    "DDDMR_RESULT_RUNNING",
    "DDDMR_RESULT_SUCCESS",
    "NAVIGATION_BACKENDS",
    "bounded_dddmr_velocity",
    "dddmr_goal_admission",
    "dddmr_result_decision",
    "dddmr_velocity_watchdog",
    "navigation_backend_policy",
    "normalize_navigation_backend",
    "task_start_requires_nav2_alignment",
]
