"""Run the isolated M20Pro 2D mapping workspace."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    bringup_share = get_package_share_directory("m20pro_2d_bringup")
    description_share = get_package_share_directory("m20pro_2d_description")
    default_slam_params = os.path.join(
        bringup_share, "config", "slam_toolbox_2d.yaml"
    )
    default_rviz = os.path.join(bringup_share, "rviz", "m20pro_2d.rviz")
    default_urdf = os.path.join(description_share, "urdf", "M20.urdf")
    default_manifest = os.path.join(
        bringup_share, "config", "m20pro_2d_map_manifest.yaml"
    )
    default_floor_config = os.path.join(
        bringup_share, "config", "m20pro_2d_runtime_navigation.yaml"
    )
    nav2_launch = os.path.join(bringup_share, "launch", "nav2_2d.launch.py")

    slam_params = LaunchConfiguration("slam_params_file")
    motion_socket = LaunchConfiguration("motion_socket_path")
    use_rviz = LaunchConfiguration("rviz")
    rviz_config = LaunchConfiguration("rviz_config")
    use_nav2 = LaunchConfiguration("nav2")
    use_web = LaunchConfiguration("web")
    enable_axis_command = LaunchConfiguration("enable_axis_command")
    camera_proxy = LaunchConfiguration("camera_proxy")
    camera_fps = LaunchConfiguration("camera_fps")

    with open(default_urdf, "r", encoding="utf-8") as urdf_file:
        robot_description = urdf_file.read()

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "slam_params_file", default_value=default_slam_params
            ),
            DeclareLaunchArgument(
                "motion_socket_path",
                default_value="/run/m20pro/motion_info_2d.sock",
            ),
            DeclareLaunchArgument("rviz", default_value="false"),
            DeclareLaunchArgument("rviz_config", default_value=default_rviz),
            DeclareLaunchArgument("nav2", default_value="true"),
            DeclareLaunchArgument("web", default_value="true"),
            DeclareLaunchArgument(
                "enable_axis_command",
                default_value=os.environ.get("M20PRO_2D_ENABLE_AXIS_COMMAND", "false"),
            ),
            DeclareLaunchArgument("camera_proxy", default_value="true"),
            DeclareLaunchArgument("camera_fps", default_value="5.0"),
            Node(
                package="m20pro_2d_bringup",
                executable="socket_odom_publisher",
                name="m20pro_2d_motion_odom",
                output="screen",
                parameters=[
                    {
                        "socket_path": motion_socket,
                        "odom_frame": "odom",
                        "base_frame": "m20pro_base_link",
                        "output_topic": "/odom",
                    }
                ],
            ),
            Node(
                package="m20pro_2d_bringup",
                executable="odom_pose_adapter",
                name="m20pro_2d_odom_pose",
                output="screen",
            ),
            Node(
                package="slam_toolbox",
                executable="async_slam_toolbox_node",
                name="slam_toolbox_2d",
                output="screen",
                parameters=[slam_params],
            ),
            Node(
                package="m20pro_2d_navigation",
                executable="command_mux",
                name="m20pro_2d_command_mux",
                output="screen",
                parameters=[
                    {
                        "navigation_cmd_vel_topic": "/cmd_vel_nav",
                        "teleop_cmd_vel_topic": "/cmd_vel_teleop",
                        "output_cmd_vel_topic": "/cmd_vel",
                        "status_topic": "/m20pro/cmd_vel_mux/status",
                        "initial_mode": "navigation",
                        "teleop_max_forward_speed_mps": 0.18,
                        "teleop_max_reverse_speed_mps": 0.12,
                        "teleop_max_lateral_speed_mps": 0.30,
                        "teleop_max_angular_speed_radps": 0.45,
                    }
                ],
            ),
            Node(
                package="m20pro_2d_navigation",
                executable="tcp_bridge",
                name="m20pro_2d_tcp_bridge",
                output="screen",
                parameters=[
                    {
                        "robot_ip": "10.21.31.103",
                        "tcp_port": 30001,
                        "poll_rate_hz": 5.0,
                        "cmd_vel_rate_hz": 20.0,
                        "cmd_vel_timeout_s": 0.5,
                        "publish_tf": False,
                        "publish_odom_to_base_tf": False,
                        "publish_pose_topic": False,
                        "publish_odom_topic": False,
                        "enable_tf_pose_fallback": False,
                        "map_frame": "map",
                        "odom_frame": "odom",
                        "base_frame": "m20pro_base_link",
                        "enable_axis_command": ParameterValue(
                            enable_axis_command, value_type=bool
                        ),
                        "enable_native_goal_bridge": False,
                        "enable_initialpose_relocalization": False,
                        "enable_initialpose_3d_relocalization": False,
                        "enable_gait_command": True,
                        "enable_motion_state_command": True,
                        "enable_usage_mode_command": False,
                        "enable_charge_command": True,
                    }
                ],
            ),
            Node(
                package="m20pro_2d_bringup",
                executable="nav2_goal_bridge",
                name="m20pro_2d_nav2_goal_bridge",
                output="screen",
                parameters=[
                    {
                        "motion_enabled": ParameterValue(
                            enable_axis_command, value_type=bool
                        ),
                        "status_topic": "/m20pro/2d/navigation_status",
                        "backend_status_topic": "/m20pro/2d/navigation_backend/status",
                    }
                ],
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(nav2_launch),
                launch_arguments={"autostart": "true"}.items(),
                condition=IfCondition(use_nav2),
            ),
            Node(
                package="m20pro_2d_cloud_bridge",
                executable="web_dashboard",
                name="m20pro_web_dashboard_2d",
                output="screen",
                parameters=[
                    {
                        "host": "0.0.0.0",
                        "port": 8080,
                        "data_dir": "/home/user/.m20pro_2d_web",
                        "floor_config": default_floor_config,
                        "map_archive_dir": "/home/user/m20pro_2d_maps",
                        "map_manifest": default_manifest,
                        "dddmr_map_asset_manifest": "",
                        "navigation_backend": "nav2_2d",
                        "navigation_backend_status_topic": "/m20pro/2d/navigation_backend/status",
                        "dddmr_runtime_status_topic": "/m20pro/dddmr/runtime/status",
                        "enable_gnss_adapter": False,
                        "enable_stair_zone_postprocess": False,
                        "enable_camera_proxy": ParameterValue(
                            camera_proxy, value_type=bool
                        ),
                        "camera_proxy_fps": ParameterValue(
                            camera_fps, value_type=float
                        ),
                        "camera_proxy_jpeg_quality": 45,
                        "camera_proxy_max_width": 480,
                        "map_select_load_nav2_map": False,
                        "startup_sync_selected_map_to_nav2": False,
                        "scan_topic": "/scan",
                        "odom_topic": "/odom",
                        "pose_topic": "/m20pro/2d/map_pose",
                        "localization_ok_topic": "/m20pro_2d_tcp_bridge/localization_ok",
                        "motion_state_topic": "/m20pro_2d_tcp_bridge/motion_state",
                        "map_topic": "/map",
                        "plan_topic": "/plan",
                        "local_plan_topic": "/local_plan",
                        "live_cloud_topic": "/m20pro/edge_cloud",
                        "navigation_status_topic": "/m20pro/2d/navigation_status",
                        "cmd_vel_topic": "/cmd_vel_nav",
                        "teleop_cmd_vel_topic": "/cmd_vel_teleop",
                    }
                ],
                condition=IfCondition(use_web),
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="m20pro_2d_robot_state_publisher",
                output="screen",
                parameters=[
                    {
                        "robot_description": robot_description,
                        "frame_prefix": "",
                    }
                ],
                condition=IfCondition(use_rviz),
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="m20pro_2d_rviz",
                output="screen",
                arguments=["-d", rviz_config],
                condition=IfCondition(use_rviz),
            ),
        ]
    )
