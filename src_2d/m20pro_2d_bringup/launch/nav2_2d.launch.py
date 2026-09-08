"""Nav2 action/navigation layer for the isolated 2D workspace."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory("m20pro_2d_bringup")
    params = os.path.join(share, "config", "nav2_params_2d.yaml")
    tree = os.path.join(share, "behavior_trees", "m20pro_navigate_to_pose_foxy.xml")
    use_sim_time = LaunchConfiguration("use_sim_time")
    autostart = LaunchConfiguration("autostart")

    lifecycle_nodes = [
        "controller_server",
        "planner_server",
        "recoveries_server",
        "bt_navigator",
    ]
    remappings = [("cmd_vel", "/cmd_vel_nav"), ("/tf", "tf"), ("/tf_static", "tf_static")]
    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument("autostart", default_value="true"),
            Node(
                package="nav2_controller",
                executable="controller_server",
                name="controller_server",
                output="screen",
                parameters=[params],
                remappings=remappings,
            ),
            Node(
                package="nav2_planner",
                executable="planner_server",
                name="planner_server",
                output="screen",
                parameters=[params],
                remappings=remappings,
            ),
            Node(
                package="nav2_recoveries",
                executable="recoveries_server",
                name="recoveries_server",
                output="screen",
                parameters=[params],
                remappings=remappings,
            ),
            Node(
                package="nav2_bt_navigator",
                executable="bt_navigator",
                name="bt_navigator",
                output="screen",
                parameters=[params, {"default_bt_xml_filename": tree}],
                remappings=remappings,
            ),
            Node(
                package="nav2_lifecycle_manager",
                executable="lifecycle_manager",
                name="lifecycle_manager_navigation_2d",
                output="screen",
                parameters=[
                    {
                        "use_sim_time": use_sim_time,
                        "autostart": autostart,
                        "node_names": lifecycle_nodes,
                    }
                ],
            ),
        ]
    )
