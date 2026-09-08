"""Pure control contract for the first DDDMR action runtime.

This is deliberately small: it is not a 3D planner and it does not replace the
real DDDMR runtime. It only produces bounded short-distance point-to-point
commands so the M20Pro integration can be tested through the DDDMR action and
velocity gates before the real `/p2p_move_base` server is available.
"""

from __future__ import annotations

import math
from typing import Any, Dict


def normalize_angle(angle: float) -> float:
    """Return angle in [-pi, pi]."""
    value = float(angle)
    while value > math.pi:
        value -= 2.0 * math.pi
    while value < -math.pi:
        value += 2.0 * math.pi
    return value


def finite_number(value: float) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def clamp_abs(value: float, limit: float) -> float:
    bound = abs(float(limit))
    return max(-bound, min(bound, float(value)))


def field_proxy_step(
    *,
    current_x: float,
    current_y: float,
    current_yaw: float,
    goal_x: float,
    goal_y: float,
    goal_yaw: float,
    xy_tolerance_m: float,
    yaw_tolerance_rad: float,
    heading_tolerance_rad: float,
    max_linear_mps: float,
    min_linear_mps: float,
    max_angular_radps: float,
    linear_gain: float,
    angular_gain: float,
) -> Dict[str, Any]:
    """Compute one safe, bounded field-proxy command."""

    values = (
        current_x,
        current_y,
        current_yaw,
        goal_x,
        goal_y,
        goal_yaw,
        xy_tolerance_m,
        yaw_tolerance_rad,
        heading_tolerance_rad,
        max_linear_mps,
        min_linear_mps,
        max_angular_radps,
        linear_gain,
        angular_gain,
    )
    if not all(finite_number(value) for value in values):
        raise ValueError("field proxy inputs must be finite")

    dx = float(goal_x) - float(current_x)
    dy = float(goal_y) - float(current_y)
    distance = math.hypot(dx, dy)
    target_heading = math.atan2(dy, dx) if distance > 1e-9 else float(current_yaw)
    heading_error = normalize_angle(target_heading - float(current_yaw))
    goal_yaw_error = normalize_angle(float(goal_yaw) - float(current_yaw))
    xy_tolerance = max(0.01, float(xy_tolerance_m))
    yaw_tolerance = max(0.01, float(yaw_tolerance_rad))
    heading_tolerance = max(0.01, float(heading_tolerance_rad))
    max_linear = max(0.0, float(max_linear_mps))
    min_linear = min(max_linear, max(0.0, float(min_linear_mps)))
    max_angular = max(0.0, float(max_angular_radps))
    angular = clamp_abs(float(angular_gain) * heading_error, max_angular)

    if distance <= xy_tolerance:
        if abs(goal_yaw_error) <= yaw_tolerance:
            return {
                "done": True,
                "decision": "field_proxy_goal_reached",
                "distance_m": distance,
                "heading_error_rad": heading_error,
                "goal_yaw_error_rad": goal_yaw_error,
                "linear_x": 0.0,
                "linear_y": 0.0,
                "angular_z": 0.0,
            }
        return {
            "done": False,
            "decision": "field_proxy_align_goal",
            "distance_m": distance,
            "heading_error_rad": heading_error,
            "goal_yaw_error_rad": goal_yaw_error,
            "linear_x": 0.0,
            "linear_y": 0.0,
            "angular_z": clamp_abs(float(angular_gain) * goal_yaw_error, max_angular),
        }

    if abs(heading_error) > heading_tolerance:
        return {
            "done": False,
            "decision": "field_proxy_rotate_to_path",
            "distance_m": distance,
            "heading_error_rad": heading_error,
            "goal_yaw_error_rad": goal_yaw_error,
            "linear_x": 0.0,
            "linear_y": 0.0,
            "angular_z": angular,
        }

    linear = min(max_linear, max(min_linear, float(linear_gain) * distance))
    return {
        "done": False,
        "decision": "field_proxy_drive",
        "distance_m": distance,
        "heading_error_rad": heading_error,
        "goal_yaw_error_rad": goal_yaw_error,
        "linear_x": linear,
        "linear_y": 0.0,
        "angular_z": angular,
    }
