#!/usr/bin/env python3
"""Contract checks for the vendored DDDMR public interface package."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DDDMR_SYS_CORE = ROOT / "src/dddmr_sys_core"


def _semantic_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def test_package_identity_and_build_type() -> None:
    package_xml = (DDDMR_SYS_CORE / "package.xml").read_text(encoding="utf-8")
    cmake = (DDDMR_SYS_CORE / "CMakeLists.txt").read_text(encoding="utf-8")
    readme = (DDDMR_SYS_CORE / "README.md").read_text(encoding="utf-8")

    assert "<name>dddmr_sys_core</name>" in package_xml
    assert "<build_type>ament_cmake</build_type>" in package_xml
    assert "<member_of_group>rosidl_interface_packages</member_of_group>" in package_xml
    assert "rosidl_generate_interfaces(${PROJECT_NAME}" in cmake
    assert "add_library(dddmr_sys_core_enum SHARED" in cmake
    assert "ament_export_dependencies(rosidl_default_runtime)" in cmake
    assert "1d0367376380205a6a18c0ad7c7c16c9338c96bc" in readme


def test_p_to_p_move_base_action_matches_bridge_contract() -> None:
    action = _semantic_lines(DDDMR_SYS_CORE / "action/PToPMoveBase.action")
    assert action == [
        "geometry_msgs/PoseStamped target_pose",
        "float32 target_value",
        "---",
        "int32 status",
        "string result",
        "---",
        "geometry_msgs/TransformStamped base_position",
        "string last_decision",
        "string current_decision",
    ]


def test_dddmr_runtime_supporting_interfaces_are_present() -> None:
    expected_files = {
        "action/GetPlan.action",
        "action/RecoveryBehaviors.action",
        "action/TagDocking.action",
        "srv/GetKeyFrameCloud.srv",
        "include/dddmr_sys_core/dddmr_enum_states.h",
        "src/dddmr_enum_states.cpp",
        "LICENSE",
    }
    for relative in expected_files:
        assert (DDDMR_SYS_CORE / relative).exists(), relative

    enum_header = (
        DDDMR_SYS_CORE / "include/dddmr_sys_core/dddmr_enum_states.h"
    ).read_text(encoding="utf-8")
    assert "typedef rclcpp_action::Server<dddmr_sys_core::action::PToPMoveBase>" in enum_header
    for state in (
        "TF_FAIL",
        "PRUNE_PLAN_FAIL",
        "ALL_TRAJECTORIES_FAIL",
        "PERCEPTION_MALFUNCTION",
        "TRAJECTORY_FOUND",
        "PATH_BLOCKED_WAIT",
        "PATH_BLOCKED_REPLANNING",
        "CONFIGURATION_ERROR",
    ):
        assert state in enum_header


def test_m20pro_navigation_declares_runtime_dependency() -> None:
    package_xml = (
        ROOT / "src/m20pro_navigation/package.xml"
    ).read_text(encoding="utf-8")
    assert "<exec_depend>dddmr_sys_core</exec_depend>" in package_xml


if __name__ == "__main__":
    test_package_identity_and_build_type()
    test_p_to_p_move_base_action_matches_bridge_contract()
    test_dddmr_runtime_supporting_interfaces_are_present()
    test_m20pro_navigation_declares_runtime_dependency()
    print("DDDMR sys core contract tests passed")
