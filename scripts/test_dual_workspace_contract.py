#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    launch = read(
        "src_2d/m20pro_2d_bringup/launch/m20pro_2d_mapping.launch.py"
    )
    slam = read("src_2d/m20pro_2d_bringup/config/slam_toolbox_2d.yaml")
    odom = read(
        "src_2d/m20pro_2d_bringup/"
        "m20pro_2d_bringup/socket_odom_publisher.py"
    )
    entrypoint = read("scripts/104_workspace_entrypoint.sh")
    switcher = read("scripts/104_switch_workspace.sh")
    service = read("systemd/m20pro-real.service")
    cloud_source = read("systemd/m20pro-dddmr-socket-source.service")
    motion_2d_source = read("systemd/m20pro-2d-motion-source.service")
    prepare = read("scripts/104_prepare_2d_workspace.sh")
    nav_setup = read("src_2d/m20pro_2d_navigation/setup.py")
    cloud_setup = read("src_2d/m20pro_2d_cloud_bridge/setup.py")
    description_package = read("src_2d/m20pro_2d_description/package.xml")
    rviz = read("src_2d/m20pro_2d_bringup/rviz/m20pro_2d.rviz")

    assert 'package="slam_toolbox"' in launch
    assert 'executable="async_slam_toolbox_node"' in launch
    assert 'package="m20pro_2d_bringup"' in launch
    assert 'package="m20pro_2d_navigation"' in launch
    assert 'package="m20pro_2d_cloud_bridge"' in launch
    assert 'get_package_share_directory("m20pro_2d_description")' in launch
    assert 'executable="socket_odom_publisher"' in launch
    assert 'default_value="/run/m20pro/motion_info_2d.sock"' in launch
    assert '"backend_status_topic": "/m20pro/2d/navigation_backend/status"' in launch
    assert '"navigation_status_topic": "/m20pro/2d/navigation_status"' in launch
    for forbidden_node in (
        'package="mcl_3dl"',
        'package="lightning"',
        'package="p2p_move_base"',
        'package="perception_3d"',
    ):
        assert forbidden_node not in launch

    assert "map_frame: map" in slam
    assert "odom_frame: odom" in slam
    assert "base_frame: m20pro_base_link" in slam
    assert "scan_topic: /scan" in slam

    assert 'self.declare_parameter("odom_frame", "odom")' in odom
    assert "TransformBroadcaster" in odom
    assert "self.tf_broadcaster.sendTransform(transform)" in odom

    assert 'case "${MODE}" in' in entrypoint
    assert "ros2 launch m20pro_2d_bringup" in entrypoint
    assert "m20pro_2d_mapping.launch.py" in entrypoint
    assert "m20pro_real_full.sh" in entrypoint
    assert "M20PRO_WORKSPACE_MODE" in switcher
    assert "/home/user/m20pro_2d_ros2_ws" in switcher
    assert "/home/user/m20pro_real_ros2_ws_v4" in switcher
    assert "M20PRO_NAVIGATION_BACKEND" in switcher
    assert "m20pro-2d-motion-source.service" in switcher

    assert "104_workspace_entrypoint.sh" in service
    assert "M20PRO_CONTROL_WS" in service
    assert "m20pro_2d_fastdds_udp.xml" in entrypoint
    assert "M20PRO_WORKSPACE_MODE" in cloud_source
    assert "in 3d)" in cloud_source
    assert "in 2d)" in motion_2d_source
    assert "m20pro_2d_navigation" in nav_setup
    assert "m20pro_2d_cloud_bridge" in cloud_setup
    assert "m20pro_2d_description" in description_package
    assert "Fixed Frame: map" in rviz
    assert "ln -sfn" not in prepare
    assert "m20pro_navigation" not in launch
    assert "m20pro_cloud_bridge" not in launch
    assert "m20pro_description" not in launch
    assert "m20pro_bringup" not in launch
    print("dual workspace contract: PASS")


if __name__ == "__main__":
    main()
