#!/usr/bin/env python3
"""Offline contract tests for the optional DDDMR navigation backend."""

from __future__ import annotations

import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_navigation"))

from m20pro_navigation.dddmr_navigation_contract import (  # noqa: E402
    bounded_dddmr_velocity,
    dddmr_goal_admission,
    dddmr_result_decision,
    dddmr_velocity_watchdog,
    navigation_backend_policy,
    normalize_navigation_backend,
    task_start_requires_nav2_alignment,
)
from m20pro_navigation.dddmr_edge_cloud_contract import (  # noqa: E402
    DDDMR_EDGE_CLOUD_TOPIC,
    EDGE_CLOUD_SOURCE_TOPIC,
    EXPECTED_EDGE_CLOUD_FRAME,
    edge_cloud_status,
    validate_edge_cloud,
)


def test_backend_policy_is_dddmr_only() -> None:
    assert normalize_navigation_backend(None) == "dddmr_3d"
    active = navigation_backend_policy("dddmr_3d", axis_enabled=True)
    assert active["uses_nav2"] is False
    assert active["uses_dddmr"] is True
    assert active["navigate_to_pose_action"] == "/navigate_to_pose_3d"
    assert active["motion_enabled"] is True
    assert navigation_backend_policy("dddmr_3d", axis_enabled=False)[
        "motion_enabled"
    ] is False

    try:
        normalize_navigation_backend("unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown backend was accepted")


def test_task_start_nav2_alignment_scope() -> None:
    assert task_start_requires_nav2_alignment(None) is False
    assert task_start_requires_nav2_alignment("dddmr_3d") is False
    for backend in ("nav2_2d", "legacy_dddmr_mode", "unknown"):
        try:
            task_start_requires_nav2_alignment(backend)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{backend} was accepted")


def test_goal_admission_fails_closed() -> None:
    ready = {
        "enabled": True,
        "motion_enabled": True,
        "action_type_available": True,
        "action_server_ready": True,
        "goal_active": False,
    }
    assert dddmr_goal_admission(**ready)["ok"] is True

    cases = {
        "enabled": "dddmr_bridge_disabled",
        "motion_enabled": "dddmr_motion_disabled",
        "action_type_available": "dddmr_action_type_missing",
        "action_server_ready": "dddmr_action_unavailable",
    }
    for field, code in cases.items():
        values = dict(ready)
        values[field] = False
        assert dddmr_goal_admission(**values) == {"ok": False, "code": code}
    busy = dict(ready)
    busy["goal_active"] = True
    assert dddmr_goal_admission(**busy) == {
        "ok": False,
        "code": "dddmr_goal_active",
    }
    no_cloud = dict(ready)
    no_cloud["perception_ready"] = False
    assert dddmr_goal_admission(**no_cloud) == {
        "ok": False,
        "code": "dddmr_edge_cloud_unavailable",
    }
    no_map = dict(ready)
    no_map["map_ready"] = False
    assert dddmr_goal_admission(**no_map) == {
        "ok": False,
        "code": "dddmr_map_unavailable",
    }


def test_edge_cloud_contract_preserves_z_and_rejects_bad_frames() -> None:
    points, details = validate_edge_cloud(
        [(1.0, 2.0, 0.4), (float("nan"), 0.0, 0.0), (40.0, 0.0, 0.1)],
        frame_id=EXPECTED_EDGE_CLOUD_FRAME,
        min_points=1,
        max_range_m=30.0,
    )
    assert points == [(1.0, 2.0, 0.4)]
    assert details["ready"] is True
    wrong_points, wrong = validate_edge_cloud(
        [(1.0, 2.0, 0.4)],
        frame_id="lidar_link",
        min_points=1,
    )
    assert wrong_points == []
    assert wrong["code"] == "edge_cloud_frame_mismatch"
    status = edge_cloud_status(
        ready=True,
        code="edge_cloud_ready",
        frame_id=EXPECTED_EDGE_CLOUD_FRAME,
        finite_points=1,
        age_s=0.1,
    )
    assert status["source_topic"] == EDGE_CLOUD_SOURCE_TOPIC
    assert status["output_topic"] == DDDMR_EDGE_CLOUD_TOPIC
    assert status["finite_points"] == 1


def test_velocity_is_finite_and_bounded() -> None:
    limits = {
        "max_forward_speed_mps": 0.18,
        "max_reverse_speed_mps": 0.12,
        "max_lateral_speed_mps": 0.30,
        "max_angular_speed_radps": 0.45,
    }
    bounded = bounded_dddmr_velocity(
        {"linear_x": 0.8, "linear_y": -0.8, "angular_z": 1.0},
        **limits,
    )
    assert bounded == {
        "linear_x": 0.18,
        "linear_y": -0.30,
        "angular_z": 0.45,
        "clamped": True,
    }
    reverse = bounded_dddmr_velocity(
        {"linear_x": -0.8, "linear_y": 0.0, "angular_z": 0.0},
        **limits,
    )
    assert reverse["linear_x"] == -0.12

    invalid_commands = [
        {"linear_x": math.nan},
        {"linear_y": math.inf},
        {"angular_z": -math.inf},
    ]
    for command in invalid_commands:
        try:
            bounded_dddmr_velocity(command, **limits)
        except ValueError:
            pass
        else:
            raise AssertionError("non-finite velocity was accepted")

    invalid_limits = dict(limits)
    invalid_limits["max_forward_speed_mps"] = -0.1
    try:
        bounded_dddmr_velocity({"linear_x": 0.0}, **invalid_limits)
    except ValueError:
        pass
    else:
        raise AssertionError("negative speed limit was accepted")


def test_velocity_watchdog_and_result_translation() -> None:
    assert dddmr_velocity_watchdog(
        goal_active=False,
        active_age_s=None,
        command_age_s=None,
        startup_grace_s=3.0,
        command_timeout_s=0.75,
    )["code"] == "dddmr_idle"
    assert dddmr_velocity_watchdog(
        goal_active=True,
        active_age_s=2.9,
        command_age_s=None,
        startup_grace_s=3.0,
        command_timeout_s=0.75,
    )["stop"] is False
    assert dddmr_velocity_watchdog(
        goal_active=True,
        active_age_s=3.1,
        command_age_s=None,
        startup_grace_s=3.0,
        command_timeout_s=0.75,
    ) == {"stop": True, "code": "dddmr_cmd_vel_start_timeout"}
    assert dddmr_velocity_watchdog(
        goal_active=True,
        active_age_s=5.0,
        command_age_s=0.8,
        startup_grace_s=3.0,
        command_timeout_s=0.75,
    ) == {"stop": True, "code": "dddmr_cmd_vel_timeout"}

    assert dddmr_result_decision(transport_status=4, result_status=1) == {
        "succeeded": True,
        "code": "dddmr_goal_succeeded",
    }
    assert dddmr_result_decision(transport_status=4, result_status=0) == {
        "succeeded": True,
        "code": "dddmr_goal_succeeded_default_result",
    }
    assert dddmr_result_decision(transport_status=4, result_status=2)[
        "succeeded"
    ] is False
    assert dddmr_result_decision(transport_status=5, result_status=0)[
        "succeeded"
    ] is False
    assert dddmr_result_decision(transport_status=6, result_status=0)[
        "succeeded"
    ] is False
    assert dddmr_result_decision(transport_status=6, result_status=1)[
        "succeeded"
    ] is False


def test_unified_navigation_doc_mentions_gnss_as_auxiliary_anchor() -> None:
    doc = (ROOT / "docs" / "unified_navigation_dddmr.md").read_text(encoding="utf-8")
    assert "/GPS" in doc
    assert "/m20pro/gnss/fix" in doc
    assert "source_topic=/GPS" in doc
    assert "fix_topic=/m20pro/gnss/fix" in doc
    assert "辅助锚点" in doc


if __name__ == "__main__":
    test_backend_policy_is_dddmr_only()
    test_task_start_nav2_alignment_scope()
    test_goal_admission_fails_closed()
    test_edge_cloud_contract_preserves_z_and_rejects_bad_frames()
    test_velocity_is_finite_and_bounded()
    test_velocity_watchdog_and_result_translation()
    test_unified_navigation_doc_mentions_gnss_as_auxiliary_anchor()
    print("DDDMR navigation contract tests passed")
