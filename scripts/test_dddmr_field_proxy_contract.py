#!/usr/bin/env python3
"""Contract tests for the low-speed DDDMR field-proxy runtime."""

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / "src/m20pro_navigation"
BRINGUP = ROOT / "src/m20pro_bringup"
CLOUD_BRIDGE = ROOT / "src/m20pro_cloud_bridge"

import sys

sys.path.insert(0, str(NAVIGATION))

from m20pro_navigation.dddmr_field_proxy_contract import field_proxy_step  # noqa: E402


def _step(**overrides):
    base = {
        "current_x": 0.0,
        "current_y": 0.0,
        "current_yaw": 0.0,
        "goal_x": 1.0,
        "goal_y": 0.0,
        "goal_yaw": 0.0,
        "xy_tolerance_m": 0.18,
        "yaw_tolerance_rad": 0.30,
        "heading_tolerance_rad": 0.35,
        "max_linear_mps": 0.18,
        "min_linear_mps": 0.04,
        "max_angular_radps": 0.45,
        "linear_gain": 0.45,
        "angular_gain": 1.2,
    }
    base.update(overrides)
    return field_proxy_step(**base)


def test_field_proxy_rotates_before_driving() -> None:
    step = _step(goal_x=0.0, goal_y=1.0)
    assert step["decision"] == "field_proxy_rotate_to_path"
    assert step["linear_x"] == 0.0
    assert math.isclose(step["angular_z"], 0.45)


def test_field_proxy_drives_when_heading_is_aligned() -> None:
    step = _step(goal_x=1.0, goal_y=0.1)
    assert step["decision"] == "field_proxy_drive"
    assert 0.04 <= float(step["linear_x"]) <= 0.18
    assert abs(float(step["angular_z"])) <= 0.45


def test_field_proxy_aligns_goal_yaw_after_xy_reached() -> None:
    step = _step(goal_x=0.05, goal_y=0.0, goal_yaw=1.0)
    assert step["decision"] == "field_proxy_align_goal"
    assert step["linear_x"] == 0.0
    assert math.isclose(step["angular_z"], 0.45)


def test_field_proxy_reports_done_inside_pose_tolerance() -> None:
    step = _step(goal_x=0.05, goal_y=0.0, goal_yaw=0.1)
    assert step["done"] is True
    assert step["decision"] == "field_proxy_goal_reached"
    assert step["linear_x"] == 0.0
    assert step["angular_z"] == 0.0


def test_field_proxy_runtime_is_wired_through_existing_dddmr_runtime_launch() -> None:
    runtime_launch = (
        BRINGUP / "launch/m20pro_dddmr_runtime.launch.py"
    ).read_text(encoding="utf-8")
    real_launch = (BRINGUP / "launch/m20pro_real.launch.py").read_text(
        encoding="utf-8"
    )
    setup = (NAVIGATION / "setup.py").read_text(encoding="utf-8")
    source = (
        NAVIGATION / "m20pro_navigation/dddmr_p2p_field_proxy_node.py"
    ).read_text(encoding="utf-8")

    assert 'default_value="official"' in runtime_launch
    assert 'choices=["official", "field_proxy"]' in runtime_launch
    assert 'executable="dddmr_p2p_field_proxy"' in runtime_launch
    assert 'condition=IfCondition(field_proxy_selected)' in runtime_launch
    assert 'runtime_backend": dddmr_runtime_backend' in real_launch
    assert 'dddmr_runtime_status_topic": "/m20pro/dddmr/runtime/status"' in real_launch
    assert (
        '"dddmr_p2p_field_proxy = m20pro_navigation.dddmr_p2p_field_proxy_node:main"'
        in setup
    )
    assert "if rclpy.ok():" in source
    assert "rclpy.shutdown()" in source


def test_field_proxy_runtime_is_visible_in_frontend_state() -> None:
    web_node = (
        CLOUD_BRIDGE / "m20pro_cloud_bridge/web_dashboard_node.py"
    ).read_text(encoding="utf-8")
    dashboard = (
        CLOUD_BRIDGE / "m20pro_cloud_bridge/static/dashboard.js"
    ).read_text(encoding="utf-8")

    assert '"dddmr_runtime_status": None' in web_node
    assert '"dddmr_runtime_status_topic", "/m20pro/dddmr/runtime/status"' in web_node
    assert 'def _on_dddmr_runtime_status(self, msg: String) -> None:' in web_node
    assert '"runtime": {' in web_node
    assert '"tf_ready": bool(runtime.get("tf_ready"))' in web_node
    assert '"tf_code": str(runtime.get("tf_code") or "")' in web_node
    assert 'field_test["acceptance"] = evaluate_dddmr_field_test_acceptance' in web_node
    assert '"field_test": field_test' in web_node
    assert 'def _dddmr_field_test_payload(self) -> Dict[str, Any]:' in web_node
    assert 'fieldTest.runtime_backend === "field_proxy" ? "现场低速代理"' in dashboard
    assert 'field_proxy_tf_unavailable' in dashboard
    assert 'runtime: {seen: false, backend: "", ready: false, state: "", code: "", tf_ready: false' in dashboard
    assert 'navigationBackendPayload(payload)' in dashboard
    assert 'field_proxy_goal_too_far' in dashboard


def test_field_proxy_runtime_ready_requires_tf() -> None:
    source = (
        NAVIGATION / "m20pro_navigation/dddmr_p2p_field_proxy_node.py"
    ).read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/smoke_dddmr_field_proxy_ros.py").read_text(
        encoding="utf-8"
    )

    assert '"tf_ready": tf_ready' in source
    assert '"tf_code": "field_proxy_tf_ready" if tf_ready else "field_proxy_tf_unavailable"' in source
    assert "and tf_ready" in source
    assert 'code = "field_proxy_tf_unavailable"' in source
    assert "field proxy runtime blocked by missing TF" in smoke
    assert 'missing_tf.get("code") == "field_proxy_tf_unavailable"' in smoke


if __name__ == "__main__":
    test_field_proxy_rotates_before_driving()
    test_field_proxy_drives_when_heading_is_aligned()
    test_field_proxy_aligns_goal_yaw_after_xy_reached()
    test_field_proxy_reports_done_inside_pose_tolerance()
    test_field_proxy_runtime_is_wired_through_existing_dddmr_runtime_launch()
    test_field_proxy_runtime_is_visible_in_frontend_state()
    test_field_proxy_runtime_ready_requires_tf()
    print("DDDMR field proxy contract tests passed")
