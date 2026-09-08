"""Start the isolated M20Pro URDF and the v4 3D RViz view.

This launch is intentionally visualization-only.  It attaches the URDF root
to the live ``base_link`` TF frame and never publishes map, odometry, or
chassis-control data.
"""

import os
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup_share = get_package_share_directory("m20pro_bringup")
    description_share = get_package_share_directory("m20pro_description")
    default_urdf = os.path.join(description_share, "urdf", "M20.urdf")
    default_rviz = os.path.join(bringup_share, "rviz", "m20pro_dddmr_3d.rviz")
    fastdds_profile = os.path.join(bringup_share, "config", "m20pro_fastdds_udp.xml")

    rviz_config = LaunchConfiguration("rviz_config")

    with open(default_urdf, "r", encoding="utf-8") as urdf_file:
        robot_description = urdf_file.read()
    urdf_root = ET.fromstring(robot_description)
    joint_names = [
        joint.attrib["name"]
        for joint in urdf_root.findall("joint")
        if joint.attrib.get("type") != "fixed"
    ]

    return LaunchDescription(
        [
            SetEnvironmentVariable(
                "FASTRTPS_DEFAULT_PROFILES_FILE", fastdds_profile
            ),
            DeclareLaunchArgument("rviz_config", default_value=default_rviz),
            Node(
                package="m20pro_bringup",
                executable="m20pro_visual_joint_state_publisher.py",
                name="m20pro_visual_joint_state_publisher",
                output="screen",
                parameters=[
                    {
                        "joint_names": joint_names,
                        "rate_hz": 20.0,
                        "robot_description": robot_description,
                    }
                ],
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="m20pro_visual_robot_state_publisher",
                output="screen",
                parameters=[
                    {
                        "robot_description": robot_description,
                        "frame_prefix": "m20pro_visual_",
                    }
                ],
                remappings=[("joint_states", "/m20pro/visualization/joint_states")],
            ),
            # Keep visualization frames separate from the official runtime's
            # leg frames. Mount the model at the real DDDMR base frame.
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="m20pro_visual_model_mount",
                output="screen",
                arguments=[
                    "0", "0", "0", "0", "0", "0",
                    "m20pro_base_link", "m20pro_visual_base_link",
                ],
            ),
            # Visualization-only map mounting.  The production asset server
            # publishes the Lightning map with frame "map", which only gets a
            # transform from the robot's own localization map frame (unrelated
            # to the Lightning map origin) until DDDMR MCL converges.  This
            # static identity TF pins the republished lightning_map frame to
            # the current base pose so the map renders around the robot in
            # RViz; it never affects the production "map" frame.
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="m20pro_visual_lightning_map_mount",
                output="screen",
                arguments=[
                    "0", "0", "0", "0", "0", "0",
                    "m20pro_base_link", "lightning_map",
                ],
            ),
            Node(
                package="m20pro_bringup",
                executable="m20pro_map_viz_republisher.py",
                name="m20pro_map_viz_republisher",
                output="screen",
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="m20pro_dddmr_3d_rviz",
                output="screen",
                arguments=["-d", rviz_config],
            ),
        ]
    )
