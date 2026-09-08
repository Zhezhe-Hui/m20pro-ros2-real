"""Start the v4 Lightning-LM mapping process for M20Pro.

This launch intentionally runs the official DeepRoboticsLab Lightning-LM
`run_slam_online` entrypoint.  Production defaults use the raw factory
`/LIDAR/POINTS + /IMU` mapping profile, while the old `/dddmr/edge_cloud`
adapter remains an explicit fallback only.  The launch keeps the Web/API
mapping contract in this repository while the algorithm runtime lives in the
separate Foxy/ARM Lightning workspace on 104.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_share = get_package_share_directory("m20pro_bringup")
    default_config = os.path.join(
        bringup_share, "config", "lightning_m20pro_raw_mapping.yaml"
    )
    config_file = LaunchConfiguration("config_file")
    run_dir = LaunchConfiguration("run_dir")
    rviz = LaunchConfiguration("rviz")
    enable_cloud_adapter = LaunchConfiguration("enable_cloud_adapter")
    cloud_adapter_input_topic = LaunchConfiguration("cloud_adapter_input_topic")
    lightning_points_topic = LaunchConfiguration("lightning_points_topic")
    cloud_adapter_expected_frame = LaunchConfiguration("cloud_adapter_expected_frame")
    cloud_adapter_output_frame = LaunchConfiguration("cloud_adapter_output_frame")

    return LaunchDescription(
        [
            DeclareLaunchArgument("config_file", default_value=default_config),
            DeclareLaunchArgument(
                "run_dir", default_value="/root/.m20pro_lightning_mapping/work"
            ),
            DeclareLaunchArgument("rviz", default_value="false"),
            DeclareLaunchArgument("enable_cloud_adapter", default_value="false"),
            DeclareLaunchArgument(
                "cloud_adapter_input_topic", default_value="/LIDAR/POINTS"
            ),
            DeclareLaunchArgument(
                "lightning_points_topic", default_value="/m20pro/lightning_points"
            ),
            DeclareLaunchArgument(
                "cloud_adapter_expected_frame", default_value="m20pro_base_link"
            ),
            DeclareLaunchArgument("cloud_adapter_output_frame", default_value="lidar_link"),
            Node(
                package="m20pro_bringup",
                executable="lightning_cloud_adapter",
                name="m20pro_lightning_cloud_adapter",
                output="screen",
                condition=IfCondition(enable_cloud_adapter),
                parameters=[
                    {
                        "input_topic": cloud_adapter_input_topic,
                        "output_topic": lightning_points_topic,
                        "expected_frame": cloud_adapter_expected_frame,
                        "output_frame": cloud_adapter_output_frame,
                        "scan_line": 96,
                        "max_points": 30000,
                    }
                ],
            ),
            ExecuteProcess(
                cmd=[
                    "ros2",
                    "run",
                    "m20pro_bringup",
                    "m20pro_lightning_slam_online.sh",
                    "--config",
                    config_file,
                    "--run-dir",
                    run_dir,
                ],
                output="screen",
            ),
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="m20pro_base_link_to_lidar_link_lightning",
                arguments=[
                    "0",
                    "0",
                    "0",
                    "0",
                    "0",
                    "0",
                    "m20pro_base_link",
                    "lidar_link",
                ],
                output="log",
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="lightning_mapping_rviz",
                arguments=[
                    "-d",
                    os.path.join(bringup_share, "rviz", "m20pro_navigation.rviz"),
                ],
                condition=IfCondition(rviz),
                output="screen",
            ),
        ]
    )
